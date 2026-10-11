"""Build a Freya phone agent from a bank's brief and its tool API file, with no manual step.

    python3 builder/build.py <input files...> <tool_api.json> [--slot NAME] [--votes 1|3] [--skip-smoke] [--out DIR]
    python3 builder/build.py --spec <spec.json> <tool_api.json> [--slot NAME]      # skip extraction, use a spec

Inputs are any text files (md, txt, eml, csv), concatenated in order with their file names as labels. The last
argument ending in .json/.yaml is the tool API. Steps (DEV_PLAN §2.1): extract → resolve → spec → verify → generate →
static tests → save (publish) → smoke → export → trace. Exit code is non-zero only if no agent was saved.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from builder.generate import generate  # noqa: E402
from builder.openapi_tools import parse_api  # noqa: E402
from builder.schema import Spec  # noqa: E402
from builder.trace import Trace  # noqa: E402

TIME_GUARD_S = 20 * 60


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*")
    ap.add_argument("--spec", help="use this spec.json instead of extracting")
    ap.add_argument("--slot", default="")
    ap.add_argument("--votes", type=int, default=1)
    ap.add_argument("--effort", default="high")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--submission", default=str(ROOT / "submission"))
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--skip-smoke", action="store_true")
    ap.add_argument("--skip-static", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--mode", choices=["spec", "agent"], default="spec",
                    help="spec: extraction + code generator (collections calls); agent: the workflow is written by Claude from the documents and validated by code")
    a = ap.parse_args(argv)
    api_path, inputs, mock_url = None, [], ""
    for i, x in enumerate(a.inputs):
        if x.lower().startswith(("http://", "https://")):
            mock_url = x                      # final form: build.py <case_folder> <mock_url>
        elif i == len(a.inputs) - 1 and x.lower().endswith((".json", ".yaml", ".yml")) and not os.path.isdir(x):
            api_path = x
        else:
            inputs.append(x)
    if not inputs and not a.spec:
        sys.exit("give at least one brief file or folder, or --spec")
    slot = a.slot or (pathlib.Path(inputs[0].rstrip("/")).stem if inputs else pathlib.Path(a.spec).stem.replace(".spec", ""))
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sub = pathlib.Path(a.submission)
    sub.mkdir(parents=True, exist_ok=True)
    tr = Trace(str(sub / f"{slot}.trace.txt"), echo=True)
    tr.start("python3 builder/build.py " + " ".join(sys.argv[1:] if argv is None else argv), inputs + ([api_path] if api_path else []) + ([mock_url] if mock_url else []))
    tr.kv("slot", slot)
    if mock_url and api_path is None:
        from builder.inputs import fetch_api
        try:
            api_path = fetch_api(mock_url, str(out / f"{slot}.tool_api.json"))
            tr.kv("tool API fetched from", mock_url.rstrip("/") + "/openapi.json")
        except Exception as e:
            tr.end("no-agent")
            sys.exit(f"the mock at {mock_url} does not serve /openapi.json: {e}")
    if api_path is None:
        sys.exit("give the tool API: a .json/.yaml file as the last argument, or the mock URL (it must serve /openapi.json)")
    t0 = time.time()
    saved = None
    status = "ok"
    try:
        tr.section("1 inputs and tool API")
        api = parse_api(api_path)
        tr.kv("tool API", f"{api.title!r} base={api.base_url} operations={sorted(api.ops)}")
        spec = None
        if a.mode == "agent":
            tr.section("2-6 agent build (Claude Agent SDK writes the workflow; code validates)")
            from builder.agent_build import agent_build
            from builder.inputs import expand_inputs
            files = expand_inputs(inputs)
            tr.kv("input files", ", ".join(os.path.basename(f) for f in files)[:600])
            wf = agent_build(files, api_path, slot, out, tr)
        elif a.spec:
            tr.section("2-5 extraction skipped: spec given")
            spec = Spec.model_validate(json.load(open(a.spec, encoding="utf-8")))
            tr.kv("spec loaded from", a.spec)
        else:
            tr.section("2-5 extract, resolve, fill, verify")
            from builder.extract import extract
            from builder.inputs import api_summary, load_api, load_text_inputs
            from builder.inputs import expand_inputs
            files = expand_inputs(inputs)
            tr.kv("input files", ", ".join(os.path.basename(f) for f in files)[:600])
            brief = load_text_inputs(inputs)
            tr.kv("input characters", len(brief))
            api_sum = api_summary(load_api(api_path))
            votes = a.votes if time.time() - t0 < TIME_GUARD_S else 1
            ex, res, spec, issues = extract(brief, api_sum, tr, a.effort, out_prefix=str(out / slot), votes=votes,
                                            verify_inputs_text="" if a.no_verify else brief)
        if spec is not None:
            (out / f"{slot}.spec.json").write_text(json.dumps(spec.model_dump(), indent=1, ensure_ascii=False))
            tr.kv("spec written", str(out / (slot + ".spec.json")))
            for u in spec.unresolved:
                tr.line(f"UNRESOLVED {u.topic}: default applied {u.default_applied!r}")
            tr.section("6 generate (code only)")
            wf = generate(spec, api)
        wf_path = out / f"{slot}.workflow.json"
        wf_path.write_text(json.dumps(wf, indent=1, ensure_ascii=False))
        kinds = {k: sum(1 for n in wf["nodes"].values() if n["node_type"] == k) for k in ("conversation", "code", "api_request", "end_call")}
        n_tools = sum(len(nd.get("tools", [])) + len([p for p in nd.get("pre_actions", []) if p["function"]["handler"] == "__function__:api_call"]) for nd in wf["nodes"].values())
        tr.kv("workflow", f"{len(wf['nodes'])} nodes {kinds}, {n_tools} api_call tools, {len(wf['system_prompt'])} chars system prompt")
        if spec is None:
            tr.section("7 static checks (generic)")
            from builder.validate import check
            verrs = check(wf, json.load(open(api_path, encoding="utf-8")))
            for e in verrs:
                tr.test("validate: " + e, False)
            tr.kv("static checks", f"{len(verrs)} error(s)")
        elif not a.skip_static:
            tr.section("7 static tests (local)")
            from builder.static_tests import T, invariants, lint
            t = T()
            try:
                lint(t, wf, spec, api)
                invariants(t, wf, spec, api)
            except Exception as e:  # a crash in the tests must not stop the build
                t.fails.append(f"static tests crashed: {e!r}")
            for f in t.fails:
                tr.test(f, False)
            tr.kv("static tests", f"{t.passes} passed, {len(t.fails)} failed")
        if a.no_save:
            tr.line("save skipped (--no-save)")
        else:
            tr.section("8 save and publish on Freya")
            from builder import freya_io
            try:
                tr.kv("dry run", freya_io.dry_run(slot + "-dry", wf))
            except Exception as e:
                tr.warn(f"dry run error: {str(e)[:500]}")
            saved = freya_io.save(slot, wf, log=tr.warn)
            tr.created("workflow", workflow_id=saved["workflow_id"], agent_id=saved["agent_id"], version=saved.get("version"), slot=slot,
                       nodes=len(wf["nodes"]), api_call_tools=n_tools)
            if a.skip_smoke or time.time() - t0 > TIME_GUARD_S:
                tr.line("smoke skipped" + (" (time guard)" if not a.skip_smoke else " (--skip-smoke)"))
            else:
                tr.section("9 smoke test (chat/message, 2 turns, no bank writes)")
                try:
                    from builder.smoke import run_smoke, run_smoke_generic
                    res_lines = run_smoke(saved["workflow_id"], spec) if spec is not None else run_smoke_generic(saved["workflow_id"], wf)
                    warns = [w for w in res_lines if not w.startswith("smoke reply")]
                    for w in res_lines:
                        tr.line(w)
                    tr.test("smoke", not warns, f"{len(warns)} warning(s)")
                except Exception as e:
                    tr.warn(f"smoke error: {str(e)[:300]}")
            tr.section("10 export")
            path = sub / f"{slot}.workflow.json"
            freya_io.export(saved["workflow_id"], str(path), log=tr.warn)
            tr.kv("exported", str(path))
    except Exception as e:
        status = "error"
        tr.line("ERROR " + "".join(traceback.format_exception(e))[-2000:])
        wf_local = locals().get("wf")
        if wf_local is not None and not saved and not a.no_save:
            # the platform refused every save attempt: keep the generated agent in the export format so there is
            # still a file to submit (no workflow id: it was never on the platform)
            path = sub / f"{slot}.workflow.json"
            path.write_text(json.dumps({"workflow_id": "", "agent_id": "", "updated_at": "", "workflow": wf_local, "note": "platform save failed; local build output"}, indent=1, ensure_ascii=False))
            tr.line(f"FALLBACK export of the local build written to {path} (not saved on the platform)")
    tr.end(status if saved or a.no_save else "no-agent")
    if not saved and not a.no_save:
        sys.exit(2)


if __name__ == "__main__":
    main()
