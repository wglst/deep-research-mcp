"""Log MCP research requests and results into the stations Directus 'research' collection.

Best effort: if Directus is down or the token is missing, research still runs and returns.
"""
import asyncio
import json
import logging
import os
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
BASE = os.environ.get("DIRECTUS_URL", "http://100.69.92.42:8055").rstrip("/")
TOKEN_FILE = Path(
    os.environ.get("DIRECTUS_TOKEN_FILE", Path.home() / ".stations-directus-token")
)
REQUESTED_BY = "mcp:public" if os.environ.get("RESEARCH_PIN_PUBLIC_URL") else "mcp:tailnet"


def _call(method: str, path: str, body: dict):
    try:
        token = TOKEN_FILE.read_text().strip()
    except OSError:
        return None
    if not token:
        return None
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def start(query: str, system_prompt: str, backend: str, title: str, project: str):
    """Create a 'running' record for this call; return its id or None."""
    title = (title or "").strip() or (query.strip().splitlines() or ["Research"])[0]
    body = {
        "status": "running",
        "backend": backend or "default",
        "title": title[:200],
        "query": query,
        "system_prompt": system_prompt or None,
        "project": project or None,
        "requested_by": REQUESTED_BY,
        "started_at": _now(),
    }
    try:
        data = await asyncio.to_thread(_call, "POST", "/items/research", body)
        return data["data"]["id"] if data else None
    except Exception as error:  # never let logging break research
        logger.warning(f"Directus log start failed: {error}")
        return None


async def finish(record_id, result) -> None:
    """Write the outcome of a call back to its record."""
    if record_id is None:
        return
    done = result.status == "completed"
    body = {
        "status": "completed" if done else "failed",
        "report": result.final_report or None,
        "citations": [asdict(c) for c in result.citations] or None,
        "task_id": result.task_id,
        "execution_seconds": result.execution_time,
        "error": None if done else (result.message or "research failed"),
        "completed_at": _now(),
    }
    try:
        await asyncio.to_thread(_call, "PATCH", f"/items/research/{record_id}", body)
    except Exception as error:
        logger.warning(f"Directus log finish failed for record {record_id}: {error}")
