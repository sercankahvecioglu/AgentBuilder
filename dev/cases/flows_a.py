"""Scripted flows for the PUB-A cases through builder.flowsim (dev material: Brief A values live here).

    python dev/cases/flows_a.py out/brief-a.workflow.json [--verbose] [--only PUB-04]
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from builder.flowsim import FakeBank, Sim
from score import score_ledger

CASES = {c["id"]: c for c in json.load(open(ROOT / "public-test-set.json"))}


def dob(c): return {"name": "verify_identity", "args": {"answer": c["identity"]["date_of_birth"]}}
def phone(c): return {"name": "verify_identity", "args": {"answer": c["identity"]["phone_last4"]}}
def verified(c): return [{"node": "opening", "set": {"who": "confirms"}}, {"node": "identity_q0", "tool": dob(c)}, {"node": "identity_q1", "tool": phone(c)}]
BYE = {"set": {}}

FLOWS = {
    "PUB-01": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "yes_today"}}, {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "PUB-02": lambda c: [{"node": "opening", "set": {"who": "third_party"}},
                         {"node": "third_party", "set": {"tp_intent": "gives_time", "d_ref": "tomorrow", "cb_time": "11:00"}},
                         {"node": "goodbye*"}],
    "PUB-03": lambda c: [{"node": "opening", "set": {"who": "confirms"}},
                         {"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": "1991-07-12"}}},
                         {"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": "1992-08-21"}}},
                         {"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": "1990-07-21"}}},
                         {"node": "goodbye*"}],
    "PUB-04": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "proposes", "d_ref": "day_of_month", "d_dom": 6, "d_month": "november"}},
                                        {"node": "negotiate", "set": {"pay": "asks_question"}},
                                        {"node": "negotiate_llm", "set": {"pay": "accepts_offer"}},
                                        {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "PUB-05": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "hardship"}},
                                        {"node": "offer", "set": {"offer_reply": "declines"}}, {"node": "goodbye*"}],
    "PUB-06": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "too_much"}},
                                        {"node": "negotiate", "set": {"pay": "proposes", "d_ref": "weekday", "d_weekday": "friday", "d_week": "this"}},
                                        {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "PUB-07": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "refuses"}},
                                        {"node": "negotiate", "set": {"pay": "vague", "d_ref": "vague"}},
                                        {"node": "negotiate", "set": {"pay": "proposes", "d_ref": "day_of_month", "d_dom": 26, "d_weekday": "monday"}},
                                        {"node": "negotiate", "set": {"pay": "accepts_offer"}},
                                        {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "PUB-08": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "already_paid"}}, {"node": "goodbye*"}],
    "PUB-09": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "wants_plan"}}, {"node": "goodbye*"}],
    "PUB-10": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "refuses"}},
                                        {"node": "negotiate", "set": {"pay": "accepts_offer"}},
                                        {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
}


def run_case(wf, cid, verbose=False):
    c = CASES[cid]
    bank = FakeBank(c["identity"], c["products"], c.get("faults"))
    variables = dict(c["variables"], customer_id="c_test")
    sim = Sim(wf, bank, variables)
    r = sim.run(FLOWS[cid](c) + [BYE, BYE])
    sc = score_ledger(c, r["ledger"])
    ok = sc["pass"] and not r["errors"]
    print(("PASS" if ok else "FAIL"), cid, "ended", r["ended"], "|", " > ".join(x["tool"] for x in r["ledger"]["calls"]))
    for f in sc["failed"]: print("     -", f)
    for e in r["errors"]: print("     ! ", e)
    if verbose or not ok:
        for l in sim.log: print("      ", l)
    return ok


if __name__ == "__main__":
    wf = json.load(open(sys.argv[1]))
    only = [a.split("=")[1] for a in sys.argv if a.startswith("--only=")]
    verbose = "--verbose" in sys.argv
    ids = only or sorted(FLOWS)
    n = sum(run_case(wf, i, verbose) for i in ids)
    print(f"\n{n} / {len(ids)} local flows pass")
