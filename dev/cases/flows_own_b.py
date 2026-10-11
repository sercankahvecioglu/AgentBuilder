"""Local flows for dev/cases/own_b.json through builder.flowsim."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "dev" / "cases"))
from flows_a import verified, BYE
from builder.flowsim import FakeBank, Sim
from score import score_ledger
OWN = {c["own_id"]: c for c in json.load(open(ROOT / "dev/cases/own_b.json"))}
R = {"set": {"pay": "refuses"}}
FLOWS = {
    "OWN-B8-no-promise": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "refuses"}}] + [R] * 6 + [{"node": "goodbye*"}],
    "OWN-B9-dispute-one": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "dispute", "applies_to": "current", "product_hint": "personal loan"}},
                                                   {"set": {"pay": "yes_today", "d_ref": "today", "applies_to": "current", "product_hint": "credit card"}},
                                                   {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "OWN-B10-restructure-after-promise": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "yes_today", "d_ref": "today", "applies_to": "current", "product_hint": "credit card"}},
                                                                  {"node": "negotiate", "set": {"pay": "wants_plan"}}, {"node": "goodbye*"}],
    "OWN-B10b-plan-after-recorded": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "yes_today", "d_ref": "today", "applies_to": "current", "product_hint": "credit card"}},
                                                             R, R, R, {"node": "readback", "set": {"rb": "confirms"}},
                                                             {"node": "say_recorded", "set": {"pay": "wants_plan"}}, {"node": "goodbye*"}],
}
if __name__ == "__main__":
    wf = json.load(open(sys.argv[1])); n = 0
    for oid, c in OWN.items():
        sim = Sim(wf, FakeBank(c["identity"], c["products"], c.get("faults"), swap_hint="day_month_swapped"), dict(c["variables"], customer_id="c_test"))
        r = sim.run(FLOWS[oid](c) + [BYE, BYE]); sc = score_ledger(c, r["ledger"]); ok = sc["pass"] and not r["errors"]; n += ok
        print(("PASS" if ok else "FAIL"), oid, "|", " > ".join(x["tool"] for x in r["ledger"]["calls"]))
        for f in sc["failed"]: print("     -", f)
        for e in r["errors"]: print("     !", e)
        if not ok or "--verbose" in sys.argv:
            for l in sim.log: print("      ", l[:150])
    print(f"\n{n} / {len(OWN)} B own flows pass")
