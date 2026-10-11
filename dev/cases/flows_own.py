"""Local flows for the own cases (dev/cases/own_a.json) through builder.flowsim."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "dev" / "cases"))
from flows_a import verified, dob, phone, BYE
from builder.flowsim import FakeBank, Sim
from score import score_ledger

OWN = {c["own_id"]: c for c in json.load(open(ROOT / "dev/cases/own_a.json"))}
FLOWS = {
    "OWN-A40-dispute": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "dispute"}}, {"node": "goodbye*"}],
    "OWN-A42-human": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "wants_human"}}, {"node": "offer", "set": {"offer_reply": "accepts"}}, {"node": "goodbye*"}],
    "OWN-A13-swapped": lambda c: [{"node": "opening", "set": {"who": "confirms"}},
                                  {"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": "1986-17-05"}}},
                                  {"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": "1986-05-17"}}},
                                  {"node": "identity_q1", "tool": phone(c)},
                                  {"node": "state_debt", "set": {"pay": "yes_today"}}, {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "OWN-A27-below-floor": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "proposes", "amount_said": 50.0, "d_ref": "weekday", "d_weekday": "friday", "d_week": "this"}},
                                                    {"node": "negotiate", "set": {"pay": "proposes", "d_ref": "weekday", "d_weekday": "friday", "d_week": "this"}},
                                                    {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}],
    "OWN-A32-support": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "hardship"}}, {"node": "offer", "set": {"offer_reply": "accepts"}}, {"node": "goodbye*"}],
    "OWN-A45-not-talk": lambda c: verified(c) + [{"node": "state_debt", "set": {"pay": "not_talk"}}, {"node": "negotiate_llm", "set": {"pay": "not_talk"}}, {"node": "goodbye*"}],
}

if __name__ == "__main__":
    wf = json.load(open(sys.argv[1]))
    n = 0
    for oid, c in OWN.items():
        faults = c.get("faults")
        bank = FakeBank(c["identity"], c["products"], faults, swap_hint="day_month_swapped")
        # the swapped hint in the fake bank needs the real DOB: 1986-17-05 is unreadable there, so model the swap by hand
        sim = Sim(wf, bank, dict(c["variables"], customer_id="c_test"))
        r = sim.run(FLOWS[oid](c) + [BYE, BYE])
        sc = score_ledger(c, r["ledger"])
        ok = sc["pass"] and not r["errors"]
        n += ok
        print(("PASS" if ok else "FAIL"), oid, "ended", r["ended"], "|", " > ".join(x["tool"] for x in r["ledger"]["calls"]))
        for f in sc["failed"]: print("     -", f)
        for e in r["errors"]: print("     !", e)
        if not ok or "--verbose" in sys.argv:
            for l in sim.log: print("      ", l[:160])
    print(f"\n{n} / {len(OWN)} own flows pass")
