"""Scripted flows for the PUB-B cases through builder.flowsim (dev material).

    python dev/cases/flows_b.py out/brief-ab.workflow.json [--verbose]
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "dev" / "cases"))
from flows_a import CASES, verified, run_case, FLOWS, BYE

FLOWS.clear()
FLOWS.update({
    "PUB-11": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "refuses"}},
                                        {"node": "negotiate", "set": {"pay": "proposes", "applies_to": "all", "d_ref": "weekday", "d_weekday": "friday", "d_week": "this"}},
                                        {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "PUB-12": lambda c: [{"node": "opening", "set": {"who": "confirms"}},
                         {"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": c["identity"]["date_of_birth"]}}},
                         {"node": "identity_q1", "tool": {"name": "verify_identity", "args": {"answer": "4401"}}},
                         {"node": "identity_q1", "tool": {"name": "verify_identity", "args": {"answer": "4410"}}},
                         {"node": "state_debt", "set": {"pay": "proposes", "applies_to": "current", "product_hint": "credit card", "d_ref": "tomorrow"}},
                         {"node": "negotiate", "set": {"pay": "refuses"}},
                         {"node": "negotiate", "set": {"pay": "refuses"}},
                         {"node": "negotiate", "set": {"pay": "refuses"}},
                         {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "PUB-13": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "refuses"}},
                                        {"node": "negotiate", "set": {"pay": "proposes", "applies_to": "all", "d_ref": "day_of_month", "d_dom": 30, "d_month": "october"}},
                                        {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
})

if __name__ == "__main__":
    wf = json.load(open(sys.argv[1]))
    verbose = "--verbose" in sys.argv
    n = sum(run_case(wf, i, verbose) for i in sorted(FLOWS))
    print(f"\n{n} / {len(FLOWS)} local flows pass")
