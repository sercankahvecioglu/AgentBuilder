"""Generic checks of a workflow JSON against the tool API, plus the platform's dry run.

    python3 -m builder.validate <workflow.json> <tool_api.json>

Exit code 0 when no error. Used by the agent build mode (the model runs it and fixes what it reports) and by build.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NODE_TYPES = {"conversation", "api_request", "code", "end_call"}


def _walk(obj, path, errs):
    if obj is None:
        errs.append(f"null value at {path} (the platform rejects null; omit the key or use \"\")")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, f"{path}.{k}", errs)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]", errs)


def check(wf: dict, api: dict | None) -> list[str]:
    errs: list[str] = []
    nodes = wf.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return ["workflow.nodes must be a non-empty object keyed by node name"]
    if wf.get("initial_node") not in nodes:
        errs.append(f"initial_node {wf.get('initial_node')!r} is not a node")
    if "agent_config" in wf:
        errs.append("remove agent_config (the platform sets the model)")
    _walk(wf, "workflow", errs)
    base = ((api or {}).get("servers") or [{}])[0].get("url", "") if api else ""
    ops = set()
    for p, methods in ((api or {}).get("paths") or {}).items():
        for m, op in methods.items():
            ops.add(op.get("operationId") or p.strip("/"))
    for name, nd in nodes.items():
        if nd.get("name") not in (None, name):
            errs.append(f"{name}: 'name' field differs from the key")
        nt = nd.get("node_type")
        if nt not in NODE_TYPES:
            errs.append(f"{name}: node_type {nt!r} is not one of {sorted(NODE_TYPES)}")
        trans = nd.get("transitions") or []
        for t in trans:
            if t.get("target_node") not in nodes:
                errs.append(f"{name}: transition to unknown node {t.get('target_node')!r}")
            if not isinstance(t.get("condition"), dict):
                errs.append(f"{name}: transition without a condition object")
        if nt in ("api_request", "code"):
            if not nd.get("passthrough"):
                errs.append(f"{name}: {nt} nodes must have passthrough: true")
            if not nd.get("passthrough_default_transition") or nd.get("passthrough_default_transition") not in nodes:
                errs.append(f"{name}: passthrough_default_transition must name an existing node")
            if not trans or (trans[-1].get("condition") or {}).get("operator") != "always":
                errs.append(f"{name}: a passthrough node must end with an 'always' transition (else it deadlocks)")
            if not nd.get("pre_actions"):
                errs.append(f"{name}: {nt} node without pre_actions")
            if nd.get("tools"):
                errs.append(f"{name}: tools are stripped from {nt} nodes; use pre_actions")
        if nt == "conversation":
            if nd.get("pre_actions"):
                errs.append(f"{name}: pre_actions are stripped from conversation nodes")
            if not nd.get("task_message") and not (nd.get("on_enter") or {}).get("text"):
                errs.append(f"{name}: conversation node needs a task_message")
            for e in nd.get("extraction_schema") or []:
                if "min_confidence" not in e:
                    errs.append(f"{name}: extraction variable {e.get('name')} without min_confidence (default 0.95 is too strict)")
        if nt == "end_call" and not nd.get("terminal"):
            errs.append(f"{name}: end_call node needs a terminal")
        for pa in (nd.get("pre_actions") or []) + (nd.get("tools") or []):
            fn = (pa.get("function") or {})
            handler = fn.get("handler", "")
            props = ((fn.get("parameters") or {}).get("properties") or {})
            if handler == "__function__:code_exec":
                code = (props.get("code") or {}).get("default", "")
                if "{{" in code or "}}" in code:
                    errs.append(f"{name}: code contains '{{{{' or '}}}}' (crashes the sandbox)")
                try:
                    compile(code, name, "exec")
                except SyntaxError as e:
                    errs.append(f"{name}: code syntax error: {e}")
            if handler == "__function__:api_call":
                url = (props.get("url") or {}).get("default", "")
                if base and not url.startswith(base):
                    errs.append(f"{name}: tool {fn.get('name')} calls {url!r}, not the mock ({base})")
                if api and fn.get("name") not in ops and not any(url.endswith("/" + o) for o in ops):
                    errs.append(f"{name}: tool {fn.get('name')} is not an operation of the tool API {sorted(ops)}")
                for h in ("pre_process_code", "post_process_code"):
                    c = pa.get(h) or fn.get(h) or ""
                    if c:
                        try:
                            compile(c, h, "exec")
                        except SyntaxError as e:
                            errs.append(f"{name}: {h} syntax error: {e}")
    reach = set()
    stack = [wf.get("initial_node")]
    while stack:
        n = stack.pop()
        if n in reach or n not in nodes:
            continue
        reach.add(n)
        nd = nodes[n]
        for t in nd.get("transitions") or []:
            stack.append(t.get("target_node"))
        if nd.get("passthrough_default_transition"):
            stack.append(nd["passthrough_default_transition"])
        if nd.get("max_turn_transition"):
            stack.append(nd["max_turn_transition"])
    for g in (wf.get("global_nodes") or {}).values():
        if isinstance(g, dict) and g.get("target_node"):
            reach.add(g["target_node"])
    unreachable = sorted(set(nodes) - reach)
    if unreachable:
        errs.append(f"unreachable nodes: {unreachable}")
    if not any(nd.get("node_type") == "end_call" for nd in nodes.values()):
        errs.append("no end_call node")
    return errs


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 1:
        print(__doc__)
        return 2
    wf = json.load(open(argv[0], encoding="utf-8"))
    api = json.load(open(argv[1], encoding="utf-8")) if len(argv) > 1 else None
    errs = check(wf, api)
    for e in errs:
        print("ERROR", e)
    if not errs and os.environ.get("FREYA_API_KEY") and "--no-dry-run" not in argv:
        try:
            import freya

            r = freya.validate_workflow("validate-dry", wf)
            print("dry run:", r)
            if isinstance(r, dict) and r.get("valid") is False:
                errs.append(f"dry run rejected: {r}")
        except Exception as e:  # noqa: BLE001
            print("dry run error:", str(e)[:800])
            errs.append("dry run error")
    print(f"{len(errs)} error(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
