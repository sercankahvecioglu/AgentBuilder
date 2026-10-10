"""Build a Freya phone agent.

    python3 builder/build.py <brief files...> <tool_api.json> [--slot NAME] [--skip-smoke] [--out DIR]
    python3 builder/build.py --spec out/spec.json <tool_api.json> [--slot NAME]      # generate from an existing spec

The last positional argument ending in .json/.yaml is the tool API. Extraction (Track B) fills the spec; with --spec
the extraction is skipped and the given spec file is used.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from builder.generate import generate  # noqa: E402
from builder.openapi_tools import parse_api  # noqa: E402
from builder.schema import Spec  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="*")
    ap.add_argument("--spec", help="use this spec.json instead of extracting")
    ap.add_argument("--slot", default="")
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--skip-smoke", action="store_true")
    a = ap.parse_args(argv)
    api_path = None
    inputs = []
    for x in a.inputs:
        if x.lower().endswith((".json", ".yaml", ".yml")) and api_path is None and x == a.inputs[-1]:
            api_path = x
        else:
            inputs.append(x)
    if api_path is None:
        sys.exit("the last argument must be the tool API file (.json)")
    t0 = time.time()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    slot = a.slot or (pathlib.Path(inputs[0]).stem if inputs else pathlib.Path(a.spec).stem.replace(".spec", ""))
    api = parse_api(api_path)
    if a.spec:
        spec = Spec.model_validate(json.load(open(a.spec, encoding="utf-8")))
    else:
        from builder.extract import extract_spec  # Track B
        spec = extract_spec(inputs, api, out / f"{slot}.facts.json")
    (out / f"{slot}.spec.json").write_text(json.dumps(spec.model_dump(), indent=1, ensure_ascii=False))
    wf = generate(spec, api)
    wf_path = out / f"{slot}.workflow.json"
    wf_path.write_text(json.dumps(wf, indent=1, ensure_ascii=False))
    print(f"generated {wf_path} with {len(wf['nodes'])} nodes in {time.time() - t0:.1f}s")
    if a.no_save:
        return
    from builder import freya_io
    r = freya_io.save(slot, wf)
    print("saved:", json.dumps(r))


if __name__ == "__main__":
    main()
