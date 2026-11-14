"""Research queue watcher: Directus 'research' records -> research station -> back."""
import asyncio, json, logging, os, sys, time, urllib.request, urllib.error
from dataclasses import asdict
from datetime import datetime, timezone
from deep_research_mcp.config import ResearchConfig
from deep_research_mcp.backends import build_research_backend

BASE = os.environ.get("DIRECTUS_URL", "http://100.69.92.42:8055")
TOKEN = open(os.path.expanduser("~/.stations-directus-token")).read().strip()
POLL = int(os.environ.get("POLL_SECONDS", "15"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("research-watcher")

def api(method, path, body=None):
    r = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")

def now(): return datetime.now(timezone.utc).isoformat()

def requeue_stuck():
    stuck = api("GET", "/items/research?filter[status][_eq]=running&fields=id&limit=-1")["data"]
    for rec in stuck:
        api("PATCH", f"/items/research/{rec['id']}", {"status": "pending", "started_at": None})
        log.info(f"requeued interrupted record {rec['id']}")

async def run_one(rec):
    rid = rec["id"]; name = (rec.get("backend") or "default").strip()
    api("PATCH", f"/items/research/{rid}", {"status": "running", "started_at": now(), "error": None})
    log.info(f"record {rid} running on backend '{name}': {rec['title']}")
    try:
        config = ResearchConfig.load(backend=None if name == "default" else name)
        backend = build_research_backend(config, log)
        result = await backend.research(rec["query"], rec.get("system_prompt") or None)
        done = result.status == "completed"
        api("PATCH", f"/items/research/{rid}", {
            "status": "completed" if done else "failed",
            "report": result.final_report or None,
            "citations": [asdict(c) for c in result.citations] or None,
            "task_id": result.task_id, "execution_seconds": result.execution_time,
            "error": None if done else (result.message or "research failed"),
            "completed_at": now()})
        log.info(f"record {rid} {'completed' if done else 'failed'}")
    except Exception as e:
        api("PATCH", f"/items/research/{rid}", {"status": "failed", "error": f"{type(e).__name__}: {e}"[:4000], "completed_at": now()})
        log.exception(f"record {rid} failed")

async def main():
    requeue_stuck(); log.info(f"watching {BASE}/items/research every {POLL}s")
    while True:
        try:
            pend = api("GET", "/items/research?filter[status][_eq]=pending&sort=date_created&limit=1")["data"]
            if pend: await run_one(pend[0]); continue
        except urllib.error.URLError as e:
            log.warning(f"Directus unreachable: {e}")
        await asyncio.sleep(POLL)

if __name__ == "__main__": asyncio.run(main())
