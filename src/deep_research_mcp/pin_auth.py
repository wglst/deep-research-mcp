"""Single-user OAuth 2.1 provider for remote (tunnel) access.

The MCP SDK serves discovery, /register (DCR), /authorize, /token with PKCE; this file stores clients
and tokens and adds a PIN page. Ported from wglst/air-mcp. The PIN lives in a 0600 file (RESEARCH_PIN_FILE, default ~/.config/research-mcp/pin). Only token
hashes are written to disk, so the state file holds no usable secret.
"""
import hashlib
import hmac
import html
import json
import re
import secrets
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
                                      RefreshToken, RegistrationError, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

PIN_FILE = Path(os.environ.get("RESEARCH_PIN_FILE", Path.home() / ".config/research-mcp/pin"))
STATE_FILE = Path.home() / ".local/state/research-mcp/oauth.json"
ACCESS_TTL, REFRESH_TTL, CODE_TTL, LOGIN_TTL = 3600, 30 * 86400, 300, 600
MAX_FAILS, LOCK_SECONDS = 5, 900
MAX_CLIENTS, MAX_PENDING = 200, 50  # bound what unauthenticated callers can make us store


def h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fails_file() -> Path:
    return Path.home() / ".local/state/research-mcp/pin-fails.json"


def keychain_pin() -> str | None:
    try:
        pin = PIN_FILE.read_text().strip()
    except OSError:
        return None
    return pin or None


class PinOAuthProvider:
    def __init__(self, public_url: str):
        self.public_url = public_url.rstrip("/")
        self.codes: dict[str, AuthorizationCode] = {}
        self.pending: dict[str, tuple[float, str, AuthorizationParams]] = {}
        self.state = {"clients": {}, "tokens": {}}
        if STATE_FILE.exists():
            self.state = json.loads(STATE_FILE.read_text())

    # Wrong-PIN times live in a file per PIN service: every process that shares a PIN shares one lockout,
    # and a restart does not reset it.
    @property
    def fails(self) -> list[float]:
        try:
            return json.loads(_fails_file().read_text())
        except (OSError, ValueError):
            return []

    @fails.setter
    def fails(self, value: list[float]):
        f = _fails_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(json.dumps(value))
        tmp.chmod(0o600)
        tmp.replace(f)

    def _save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        self.state["tokens"] = {k: v for k, v in self.state["tokens"].items() if v["expires_at"] > now}
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.chmod(0o600)
        tmp.replace(STATE_FILE)

    # --- clients (DCR) ---
    async def get_client(self, client_id: str):
        c = self.state["clients"].get(client_id)
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def register_client(self, client_info: OAuthClientInformationFull):
        for u in client_info.redirect_uris or []:
            p = urlparse(str(u))
            # ChatGPT web uses either its legacy callback or a callback-specific ID.
            # Keep this limited to the exact HTTPS origin and documented paths.
            chatgpt = (p.scheme == "https" and p.netloc == "chatgpt.com" and
                       not p.params and not p.query and not p.fragment and
                       (p.path == "/connector_platform_oauth_redirect" or
                        re.fullmatch(r"/connector/oauth/[A-Za-z0-9_-]+", p.path) is not None))
            ok = (p.scheme == "https" and p.hostname in ("claude.ai", "claude.com")) or \
                 (p.scheme == "http" and p.hostname in ("localhost", "127.0.0.1")) or chatgpt
            if not ok:
                raise RegistrationError("invalid_redirect_uri", f"redirect not allowed: {u}")
        clients = self.state["clients"]
        while len(clients) >= MAX_CLIENTS:  # drop the oldest registration (dicts keep insertion order)
            clients.pop(next(iter(clients)))
        clients[client_info.client_id] = client_info.model_dump(mode="json")
        self._save()

    # --- authorize: park the request, send the browser to the PIN page ---
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if not keychain_pin():
            raise AuthorizeError("server_error", "no PIN set; write it to the PIN file")
        rid = secrets.token_urlsafe(32)
        self.pending = {k: v for k, v in self.pending.items() if v[0] > time.time()}
        if len(self.pending) >= MAX_PENDING:
            raise AuthorizeError("temporarily_unavailable", "too many sign-ins in progress")
        self.pending[rid] = (time.time() + LOGIN_TTL, client.client_id, params)
        return f"{self.public_url}/oauth/login?req={rid}"

    def _page(self, rid: str, msg: str = "", status: int = 200):
        item = self.pending.get(rid)
        if not item:
            return HTMLResponse("<p>This sign-in request expired. Start again from Claude.</p>", 400)
        _, client_id, params = item
        client = self.state["clients"].get(client_id, {})
        host = urlparse(str(params.redirect_uri)).hostname
        e = html.escape
        return HTMLResponse(f"""<!doctype html><meta name=viewport content="width=device-width">
<title>Research Station sign-in</title><body style="font:16px system-ui;max-width:28em;margin:3em auto;padding:0 1em">
<h2>Research Station</h2>
<p><b>{e(client.get('client_name') or 'A client')}</b> wants to use the Research Station (deep_research, research_status, list_backends).<br>
After approval you will be sent to <b>{e(host or '?')}</b>.</p>
{f'<p style="color:#b00">{e(msg)}</p>' if msg else ''}
<form method=post action="/oauth/login"><input type=hidden name=req value="{e(rid)}">
<label>PIN <input name=pin type=password autocomplete=current-password autofocus required></label>
<button>Approve</button></form></body>""", status)

    async def login_get(self, request: Request):
        return self._page(request.query_params.get("req", ""))

    async def login_post(self, request: Request):
        form = await request.form()
        rid, pin = str(form.get("req", "")), str(form.get("pin", ""))
        now = time.time()
        self.fails = [t for t in self.fails if t > now - LOCK_SECONDS]
        if len(self.fails) >= MAX_FAILS:
            return self._page(rid, "Too many wrong PINs. Try again in 15 minutes.", 429)
        item = self.pending.get(rid)
        if not item or item[0] < now:
            return self._page("")
        expected = keychain_pin()
        if not expected or not hmac.compare_digest(pin.encode(), expected.encode()):
            self.fails = self.fails + [now]
            return self._page(rid, "Wrong PIN.", 401)
        del self.pending[rid]
        _, client_id, params = item
        code = secrets.token_urlsafe(32)
        self.codes[code] = AuthorizationCode(
            code=code, scopes=params.scopes or [], expires_at=now + CODE_TTL, client_id=client_id,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject="owner")
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state), 302)

    # --- tokens ---
    async def load_authorization_code(self, client, authorization_code: str):
        c = self.codes.get(authorization_code)
        return c if c and c.client_id == client.client_id and c.expires_at > time.time() else None

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        now = int(time.time())
        at, rt = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        base = {"client_id": client_id, "scopes": scopes, "resource": resource}
        self.state["tokens"][h(at)] = {**base, "kind": "access", "expires_at": now + ACCESS_TTL}
        self.state["tokens"][h(rt)] = {**base, "kind": "refresh", "expires_at": now + REFRESH_TTL}
        self._save()
        return OAuthToken(access_token=at, token_type="Bearer", expires_in=ACCESS_TTL, refresh_token=rt,
                          scope=" ".join(scopes) or None)

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        if self.codes.pop(authorization_code.code, None) is None:
            raise TokenError("invalid_grant", "code already used")
        return self._issue(client.client_id, authorization_code.scopes, authorization_code.resource)

    def _load(self, token: str, kind: str):
        t = self.state["tokens"].get(h(token))
        return t if t and t["kind"] == kind and t["expires_at"] > time.time() else None

    async def load_refresh_token(self, client, refresh_token: str):
        t = self._load(refresh_token, "refresh")
        if not t or t["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=t["client_id"], scopes=t["scopes"],
                            expires_at=t["expires_at"], resource=t["resource"], subject="owner")

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        if self.state["tokens"].pop(h(refresh_token.token), None) is None:  # rotate: old one dies here
            raise TokenError("invalid_grant", "refresh token already used")
        return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token: str):
        t = self._load(token, "access")
        if not t:
            return None
        return AccessToken(token=token, client_id=t["client_id"], scopes=t["scopes"],
                           expires_at=t["expires_at"], resource=t["resource"], subject="owner")

    async def revoke_token(self, token):
        self.state["tokens"].pop(h(token.token), None)
        self._save()


def build_pin_auth(public_url: str):
    """Return (provider, AuthSettings) for FastMCP's built-in OAuth endpoints."""
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
    url = public_url.rstrip("/")
    settings = AuthSettings(issuer_url=url, resource_server_url=f"{url}/mcp",
                            client_registration_options=ClientRegistrationOptions(enabled=True),
                            revocation_options=RevocationOptions(enabled=True))
    return PinOAuthProvider(url), settings
