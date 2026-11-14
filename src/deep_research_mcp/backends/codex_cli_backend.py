# -*- coding: utf-8 -*-

"""Codex CLI subscription provider backend.

Runs headless ``codex exec`` signed in with the user's ChatGPT plan (official
CLI route), with live web search on and a read-only sandbox. API-key variables
are removed from the child environment so a run never falls back to API billing.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from deep_research_mcp.results import ResearchResult, ResearchTaskStatus

from .base import ResearchBackend, TaskStartedCallback
from .claude_code_backend import ClaudeCodeResearchBackend, _RESEARCH_INSTRUCTIONS

CODEX_CLI_STORE = Path(
    os.environ.get("CODEX_RESEARCH_STORE", "~/.deep_research_codex_cli")
).expanduser()
CODEX_AUTH_PATH = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "auth.json"
_API_KEY_VARS = ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")


def _find_codex() -> str:
    found = shutil.which("codex")
    if found:
        return found
    for candidate in ("~/.local/bin/codex", "/usr/local/bin/codex", "/usr/bin/codex"):
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    raise FileNotFoundError("codex CLI not found on PATH")


class CodexCliResearchBackend(ResearchBackend):
    """Run research through headless Codex CLI on the user's ChatGPT plan."""

    async def research(
        self,
        query: str,
        system_prompt: str | None = None,
        include_code_interpreter: bool = True,
        on_task_started: TaskStartedCallback | None = None,
    ) -> ResearchResult:
        del include_code_interpreter
        task_id = f"cx-{uuid.uuid4().hex[:16]}"
        started = time.monotonic()
        created_at = time.time()
        self._save(task_id, {"status": "running", "created_at": created_at})
        self.logger.info(f"Research task started: {task_id}")
        if on_task_started:
            await on_task_started(task_id)

        try:
            codex_bin = _find_codex()
        except FileNotFoundError as error:
            return self._fail(task_id, created_at, str(error))

        workdir = tempfile.mkdtemp(prefix="codex-research-")
        out_file = Path(workdir) / "last-message.md"
        cmd = [
            codex_bin, "--search", "exec",
            "--skip-git-repo-check", "--ephemeral",
            "-s", "read-only", "--color", "never", "--json",
            "-o", str(out_file),
        ]
        if self.config.model and self.config.model != "auto":
            cmd += ["-m", self.config.model]
        if self.config.reasoning_effort:
            cmd += ["-c", f'model_reasoning_effort="{self.config.reasoning_effort}"']
        cmd.append("-")  # prompt from stdin
        env = {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}
        prompt = _RESEARCH_INSTRUCTIONS + self._combine_system_prompt(query, system_prompt)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=workdir, env=env,
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
                return self._fail(task_id, created_at,
                                  f"Codex CLI did not finish within {self.config.timeout} seconds")
            report = out_file.read_text() if out_file.is_file() else ""
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        searches, queries, turns, errors = 0, [], 0, []
        for line in stdout.decode(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item") or {}
            if event.get("type") == "item.completed" and item.get("type") == "web_search":
                searches += 1
                if item.get("query"):
                    queries.append(str(item["query"]))
            elif event.get("type") == "turn.completed":
                turns += 1
            elif event.get("type") in ("error", "turn.failed"):
                errors.append(str(event.get("message") or event.get("error") or event))

        if proc.returncode != 0 or not report.strip():
            message = "; ".join(errors) or stderr.decode(errors="replace")[-2000:] \
                or f"Codex CLI exited with code {proc.returncode}"
            return self._fail(task_id, created_at, message)

        result = ResearchResult.completed(
            task_id=task_id,
            final_report=report,
            citations=ClaudeCodeResearchBackend._citations(report),
            search_queries=queries,
            total_steps=turns,
            message=f"Codex CLI subscription; web searches: {searches}",
            execution_time=time.monotonic() - started,
        )
        self._save(task_id, {"status": "completed", "created_at": created_at,
                             "completed_at": time.time(), "result": asdict(result)})
        return result

    async def get_task_status(self, task_id: str) -> ResearchTaskStatus:
        record = self._load(task_id)
        if record is None:
            return ResearchTaskStatus.unknown(task_id=task_id, message="No Codex CLI task with this ID here")
        return ResearchTaskStatus(task_id=task_id, status=record.get("status", "unknown"),
                                  created_at=record.get("created_at"),
                                  completed_at=record.get("completed_at"),
                                  message=record.get("message"))

    async def get_task_result(self, task_id: str) -> ResearchResult | None:
        record = self._load(task_id)
        if not record or record.get("status") != "completed":
            return None
        from deep_research_mcp.results import ResearchCitation
        data = dict(record["result"])
        data["citations"] = [ResearchCitation(**c) for c in data.get("citations") or []]
        return ResearchResult(**data)

    def _fail(self, task_id: str, created_at: float, message: str) -> ResearchResult:
        self._save(task_id, {"status": "failed", "created_at": created_at,
                             "completed_at": time.time(), "message": message})
        return ResearchResult.failed(task_id=task_id, message=message)

    @staticmethod
    def _save(task_id: str, record: dict[str, Any]) -> None:
        CODEX_CLI_STORE.mkdir(mode=0o700, parents=True, exist_ok=True)
        (CODEX_CLI_STORE / f"{task_id}.json").write_text(json.dumps(record))

    @staticmethod
    def _load(task_id: str) -> dict[str, Any] | None:
        path = CODEX_CLI_STORE / f"{Path(task_id).name}.json"
        return json.loads(path.read_text()) if path.is_file() else None
