# -*- coding: utf-8 -*-

"""Claude Code subscription provider backend.

Runs headless ``claude -p`` signed in with the user's Claude plan, so research
draws on plan usage limits instead of API credit. API-key variables are removed
from the child environment so a run can never fall back to API billing.
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from deep_research_mcp.results import (
    ResearchCitation,
    ResearchResult,
    ResearchTaskStatus,
)

from .base import ResearchBackend, TaskStartedCallback

CLAUDE_CODE_STORE = Path(
    os.environ.get("CLAUDE_RESEARCH_STORE", "~/.deep_research_claude")
).expanduser()
CLAUDE_CREDENTIALS_PATH = Path("~/.claude/.credentials.json").expanduser()

_RESEARCH_INSTRUCTIONS = (
    "You are a research agent. Use web search and web fetch to investigate the "
    "request below thoroughly, cross-check facts across sources, and write a "
    "well-structured Markdown report. Cite sources inline as Markdown links and "
    "end with a 'Sources' section listing every URL you relied on. Do not create "
    "or edit files.\n\n"
)
_URL_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^\s)]+)\)|(?<![\(\w])(https?://[^\s)\]>]+)"
)
_API_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
)


def _find_claude() -> str:
    found = shutil.which("claude")
    if found:
        return found
    for candidate in (
        "~/.local/bin/claude",
        "~/.claude/local/claude",
        "/usr/local/bin/claude",
        "/usr/bin/claude",
    ):
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    raise FileNotFoundError("claude CLI not found on PATH")


class ClaudeCodeResearchBackend(ResearchBackend):
    """Run research through headless Claude Code on the user's Claude plan."""

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        del include_code_interpreter
        task_id = f"cc-{uuid.uuid4().hex[:16]}"
        started = time.monotonic()
        created_at = time.time()
        self._save(task_id, {"status": "running", "created_at": created_at})
        self.logger.info(f"Research task started: {task_id}")
        if on_task_started:
            await on_task_started(task_id)

        try:
            claude_bin = _find_claude()
        except FileNotFoundError as error:
            return self._fail(task_id, created_at, str(error))

        cmd = [
            claude_bin,
            "-p",
            "--output-format",
            "json",
            "--allowedTools",
            "WebSearch,WebFetch",
        ]
        if self.config.model and self.config.model != "auto":
            cmd += ["--model", self.config.model]
        env = {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}
        prompt = _RESEARCH_INSTRUCTIONS + self._combine_system_prompt(
            query, system_prompt
        )
        workdir = tempfile.mkdtemp(prefix="claude-research-")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workdir,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode()), timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return self._fail(
                    task_id,
                    created_at,
                    f"Claude Code did not finish within {self.config.timeout} seconds",
                )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        out_text = stdout.decode(errors="replace")
        err_text = stderr.decode(errors="replace")
        try:
            data: dict[str, Any] = json.loads(out_text or "{}")
        except json.JSONDecodeError:
            return self._fail(
                task_id,
                created_at,
                (err_text or out_text or "Claude Code returned no JSON")[-2000:],
            )
        if proc.returncode != 0 or data.get("is_error"):
            message = (
                data.get("result")
                or err_text[-2000:]
                or f"Claude Code exited with code {proc.returncode}"
            )
            return self._fail(task_id, created_at, str(message))

        report = data.get("result") or ""
        usage = data.get("usage") or {}
        searches = (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
        models = ", ".join((data.get("modelUsage") or {}).keys()) or "claude"
        result = ResearchResult.completed(
            task_id=task_id,
            final_report=report,
            citations=self._citations(report),
            total_steps=int(data.get("num_turns") or 0),
            message=f"Claude Code subscription ({models}); web searches: {searches}",
            execution_time=time.monotonic() - started,
        )
        self._save(
            task_id,
            {
                "status": "completed",
                "created_at": created_at,
                "completed_at": time.time(),
                "result": asdict(result),
            },
        )
        return result

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        record = self._load(task_id)
        if record is None:
            return ResearchTaskStatus.unknown(
                task_id=task_id, message="No Claude Code task with this ID here"
            )
        return ResearchTaskStatus(
            task_id=task_id,
            status=record.get("status", "unknown"),
            created_at=record.get("created_at"),
            completed_at=record.get("completed_at"),
            message=record.get("message"),
        )

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        record = self._load(task_id)
        if not record or record.get("status") != "completed":
            return None
        data = dict(record["result"])
        data["citations"] = [
            ResearchCitation(**c) for c in data.get("citations") or []
        ]
        return ResearchResult(**data)

    def _fail(self, task_id: str, created_at: float, message: str) -> ResearchResult:
        self._save(
            task_id,
            {
                "status": "failed",
                "created_at": created_at,
                "completed_at": time.time(),
                "message": message,
            },
        )
        return ResearchResult.failed(task_id=task_id, message=message)

    @staticmethod
    def _save(task_id: str, record: dict[str, Any]) -> None:
        CLAUDE_CODE_STORE.mkdir(mode=0o700, parents=True, exist_ok=True)
        (CLAUDE_CODE_STORE / f"{task_id}.json").write_text(json.dumps(record))

    @staticmethod
    def _load(task_id: str) -> dict[str, Any] | None:
        path = CLAUDE_CODE_STORE / f"{Path(task_id).name}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text())

    @staticmethod
    def _citations(report: str) -> list[ResearchCitation]:
        citations: list[ResearchCitation] = []
        seen: set[str] = set()
        for match in _URL_RE.finditer(report):
            if match.group(2):
                title, url = match.group(1), match.group(2)
            else:
                title, url = None, match.group(3)
            url = url.rstrip(".,;:")
            if url in seen:
                continue
            seen.add(url)
            citations.append(
                ResearchCitation(index=len(citations) + 1, title=title or url, url=url)
            )
        return citations
