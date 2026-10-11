"""Agent build mode: the workflow is written by Claude (Agent SDK) from the documents and the tool API, then validated
by code and the platform's dry run. Used when the case is not the collections flow the spec/generator path knows.

    build.py <case_folder> <mock_url> --mode agent

The whole SDK conversation is logged to traces/<slot>.agent.jsonl (the session log the organisers ask for) and every
model result is also written as a line in the builder's trace.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import pathlib
import shutil
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "builder" / "templates" / "agent_skill.md"
MAX_SECONDS = 20 * 60


def prepare_docs(files: list[str], api_path: str, out_dir: pathlib.Path) -> pathlib.Path:
    """Every input document as a text file the agent can Read (Word/PDF/Excel converted)."""
    from builder.inputs import read_document

    docs = out_dir / "docs"
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir(parents=True)
    for i, p in enumerate(files):
        name = os.path.basename(p)
        try:
            text = read_document(p)
        except Exception as e:  # noqa: BLE001
            text = f"[could not read this file: {type(e).__name__}: {e}]"
        (docs / f"{i + 1:02d}_{name}.txt").write_text(text, encoding="utf-8")
    shutil.copy(api_path, out_dir / "tool_api.json")
    return docs


async def _run(prompt: str, system: str, log_path: pathlib.Path, tr, model: str) -> dict[str, Any]:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query

    options = ClaudeAgentOptions(
        cwd=str(ROOT), model=model, system_prompt=system,
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
        permission_mode="dontAsk", setting_sources=[], max_turns=120,
        env={"CLAUDECODE": "", "CLAUDE_CODE_ENTRYPOINT": "", "BASH_DEFAULT_TIMEOUT_MS": "300000", "BASH_MAX_TIMEOUT_MS": "600000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"},
    )
    summary: dict[str, Any] = {"turns": 0, "cost": None, "usage": {}, "text": []}
    t0 = time.monotonic()
    with log_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model": model, "prompt": prompt}) + "\n")
        async for message in query(prompt=prompt, options=options):
            out.write(json.dumps({"type": type(message).__name__, **dataclasses.asdict(message)}, default=str) + "\n")
            out.flush()
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tr.line(f"AGENT TOOL {block.name}: {str(block.input)[:160]}")
                    elif isinstance(block, TextBlock) and block.text.strip():
                        summary["text"].append(block.text)
                        tr.line("AGENT: " + " ".join(block.text.split())[:300])
            elif isinstance(message, ResultMessage):
                summary["turns"] = message.num_turns
                summary["cost"] = message.total_cost_usd
                summary["usage"] = message.usage or {}
                u = message.usage or {}
                tr.model_call(model, "agent build (claude agent sdk session)", time.monotonic() - t0,
                              int(u.get("input_tokens", 0) or 0), int(u.get("output_tokens", 0) or 0),
                              message.session_id, message.stop_reason or message.subtype, "high", ok=not message.is_error)
    return summary


def agent_build(files: list[str], api_path: str, slot: str, out: pathlib.Path, tr, model: str = "claude-opus-5-5") -> dict:
    work = out / f"{slot}.agent"
    work.mkdir(parents=True, exist_ok=True)
    docs = prepare_docs(files, api_path, work)
    tr.kv("agent docs", f"{len(list(docs.iterdir()))} files in {docs}")
    out_file = work / "workflow.json"
    if out_file.exists():
        out_file.unlink()
    log_path = ROOT / "traces" / f"{slot}.agent.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    system = SKILL.read_text(encoding="utf-8")
    prompt = (
        f"Build the phone agent.\n"
        f"DOCS_DIR: {docs}\nAPI_FILE: {work / 'tool_api.json'}\n"
        f"PLATFORM_DOCS: {ROOT / 'docs' / 'workflow-format.md'} and {ROOT / 'docs' / 'tools-and-code.md'}\n"
        f"EXAMPLE_FILE: {ROOT / 'examples' / 'base-agent.json'}\n"
        f"OUT_FILE: {out_file}\n"
        f"VALIDATE_CMD: cd {ROOT} && python3 -m builder.validate {out_file} {work / 'tool_api.json'}\n"
        f"You have about {MAX_SECONDS // 60} minutes. Begin."
    )
    tr.kv("agent session log", str(log_path))
    try:
        summary = asyncio.run(asyncio.wait_for(_run(prompt, system, log_path, tr, model), timeout=MAX_SECONDS))
        tr.kv("agent result", f"{summary['turns']} turns, cost {summary['cost']}, usage {json.dumps(summary['usage'])[:200]}")
    except asyncio.TimeoutError:
        tr.warn(f"agent build stopped at the {MAX_SECONDS // 60} min guard; using the last workflow written")
    if not out_file.exists():
        raise RuntimeError("the agent wrote no workflow file")
    wf = json.loads(out_file.read_text(encoding="utf-8"))
    from builder.validate import check
    api = json.load(open(api_path, encoding="utf-8"))
    errs = check(wf, api)
    for e in errs:
        tr.test("validate: " + e, False)
    tr.kv("validate", f"{len(errs)} error(s)")
    return wf
