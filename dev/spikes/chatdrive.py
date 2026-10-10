"""Drive a workflow turn by turn through POST /api/v2/chat/message against a real PUB practice session (dev only).

    python dev/spikes/chatdrive.py <slot> <PUB-id> <messages.json> [--vars k=v ...] [--out file.json]

messages.json: a JSON list of customer messages. Placeholders {dob} and {phone} are filled from the case's identity.
Prints every agent reply, then the call's events, the final variable table (filtered) and the bank ledger.
"""
import argparse, json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
from score import http


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slot"); ap.add_argument("case"); ap.add_argument("messages")
    ap.add_argument("--vars", nargs="*", default=[]); ap.add_argument("--out"); ap.add_argument("--prefixes", default="")
    a = ap.parse_args()
    state = json.load(open(ROOT / ".freya-agents.json"))
    wf_id = state[a.slot]["workflow_id"]
    cases = {c["id"]: c for c in json.load(open(ROOT / "public-test-set.json"))}
    case = cases[a.case]
    sess = http("/v1/practice/sessions", {"case": a.case})["variables"]
    ident = case["identity"]
    variables = dict(sess)
    variables.update({"id_field1": "date_of_birth", "id_answer1": ident.get("date_of_birth", ""), "id_field2": "phone_last4", "id_answer2": ident.get("phone_last4", "")})
    for kv in a.vars:
        k, v = kv.split("=", 1); variables[k] = v
    msgs = json.load(open(a.messages))
    print("session vars:", {k: v for k, v in sess.items()}, flush=True)
    call_id, log = None, []
    for i, m in enumerate(msgs):
        m = m.format(dob=ident.get("date_of_birth", ""), phone=ident.get("phone_last4", ""))
        body = {"workflowId": wf_id, "message": m, "customerVariables": variables}
        if call_id: body["callId"] = call_id
        t0 = time.time()
        try:
            r = freya.api("POST", "/api/v2/chat/message", body)
        except RuntimeError as e:
            print(f"[{i}] USER: {m}\n    ERROR {str(e)[:600]}", flush=True); log.append({"user": m, "error": str(e)[:600]}); continue
        call_id = r.get("callId") or call_id
        resp = r.get("response")
        print(f"[{i}] USER: {m}\n    AGENT ({time.time()-t0:.1f}s): {resp}", flush=True)
        if len(r) > 2: print("    extra keys:", {k: v for k, v in r.items() if k not in ("response",)})
        log.append({"user": m, "agent": resp, "raw": r})
    try:
        freya.api("POST", "/api/v2/chat/end", {"callId": call_id}); print("chat ended")
    except RuntimeError as e:
        print("chat/end:", str(e)[:200])
    time.sleep(3)
    call = freya.get_call(call_id)
    print("\n=== endedReason:", call.get("endedReason"), "duration", call.get("duration"))
    last_vt = {}
    print("=== events / transcript")
    for m in call.get("messages", []):
        if m["role"] == "system":
            try: ev = json.loads(m["message"])
            except Exception: print("  SYS", m["message"][:200]); continue
            e = ev.get("event")
            if e == "route_evaluated":
                if ev.get("variable_table"): last_vt = ev["variable_table"]
                print(f"  ROUTE {ev.get('from_node')} -> {ev.get('target')} matched={ev.get('matched')} reason={str(ev.get('reason'))[:120]}")
                for b in ev.get("branches", [])[:8]:
                    print("        branch:", json.dumps(b)[:200])
            elif e in ("function_call_start",):
                print(f"  CALL {ev.get('function')} body={json.dumps((ev.get('args') or {}).get('body'))}")
            elif e in ("function_call_complete", "function_call_error"):
                r = ev.get("result");
                if isinstance(r, dict): r.pop("header", None)
                print(f"  {e.upper()} {ev.get('function')} {json.dumps(r if r is not None else ev.get('error'))[:400]}")
            else:
                print(f"  {e} {json.dumps({k: v for k, v in ev.items() if k != 'event'})[:300]}")
        else:
            print(f"  {m['role'].upper():9} [{m.get('nodeId')}] {m['message'][:300]}")
    print("\n=== final variable table (filtered)")
    pref = tuple(p for p in a.prefixes.split(",") if p) or ("s1_", "s2_", "s4_", "s7_", "s9_", "p_", "pr_", "v_", "v1_", "v2_", "ga_", "attempts", "retry", "intent", "d_test", "amt", "anchor", "dob_said", "products", "bye", "close_", "do_promise", "create_promise_", "load_account", "get_account_", "account_facts", "reset_intent", "do_verify")
    for k in sorted(last_vt):
        if k.startswith(pref):
            v = last_vt[k]
            val = v.get("value") if isinstance(v, dict) else v
            src = (v.get("source"), v.get("source_node")) if isinstance(v, dict) else ""
            print(f"  {k} = {json.dumps(val)[:300]}  {src}")
    led = http("/v1/practice/ledger/" + sess["customer_id"])
    print("\n=== ledger:", json.dumps({k: led.get(k) for k in ("outcome", "reason", "promises", "notes", "callbacks", "transfers")}))
    print("    calls:", [(c["tool"], (c.get("result") or {}).get("ok"), (c.get("result") or {}).get("error")) for c in led.get("calls", [])])
    if a.out:
        json.dump({"call_id": call_id, "customer_id": sess["customer_id"], "log": log, "variable_table": last_vt, "ledger": led, "messages": call.get("messages")}, open(a.out, "w"), indent=1)
        print("saved", a.out)


if __name__ == "__main__":
    main()
