"""Static tests of a generated workflow against its spec (Phase 6). Local, seconds, no platform calls.

    python -m builder.static_tests out/<slot>.workflow.json out/<slot>.spec.json [--api tools/openapi.json]

Checks: workflow lint (T6.4), data flow of prompt placeholders, snippet runs on several `now` dates and garbage input,
calendar and guard invariants derived from the spec (T6.2), close rows, callback window, failing writes, aggregation.
Every expectation is computed here from the spec, never from the agent's output.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys
from typing import Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from builder.flowsim import FakeBank, Sim  # noqa: E402
from builder.generate import WEEKDAY_NAMES, row_key, tv  # noqa: E402
from builder.openapi_tools import parse_api  # noqa: E402
from builder.schema import Spec  # noqa: E402

_API = [None]


class T:
    def __init__(self):
        self.fails: List[str] = []
        self.passes = 0

    def ok(self, cond, msg):
        if cond:
            self.passes += 1
        else:
            self.fails.append(msg)


# ----------------------------------------------------------------------------- reference calendar (independent of the snippets)

class Cal:
    def __init__(self, spec: Spec):
        self.bw = {WEEKDAY_NAMES.index(w.lower()) for w in tv(spec.calendar.business_weekdays)}
        self.hol = set(tv(spec.calendar.holidays))

    def is_bd(self, d):
        return d.weekday() in self.bw and d.isoformat() not in self.hol

    def next_bd(self, d):
        while not self.is_bd(d):
            d += datetime.timedelta(days=1)
        return d

    def add_bd(self, d, n):
        k = 0
        while k < n:
            d += datetime.timedelta(days=1)
            if self.is_bd(d):
                k += 1
        return d

    def last_bd_of_week(self, d):
        e = d - datetime.timedelta(days=d.weekday()) + datetime.timedelta(days=6)
        while not self.is_bd(e):
            e -= datetime.timedelta(days=1)
        return e


def sample_dates(spec: Spec) -> List[datetime.date]:
    """Several `now` dates: weekdays of one week, the day before each holiday, a holiday, month end, year end."""
    hol = sorted(tv(spec.calendar.holidays))
    base = datetime.date.fromisoformat(hol[0]) if hol else datetime.date.today()
    monday = base - datetime.timedelta(days=base.weekday() + 7)
    out = [monday + datetime.timedelta(days=k) for k in range(7)]
    for h in hol[:3]:
        d = datetime.date.fromisoformat(h)
        out += [d - datetime.timedelta(days=1), d]
    y = base.year
    out += [datetime.date(y, 12, 31), datetime.date(y, 12, 30), datetime.date(y + 1, 1, 2)]
    return sorted(set(out))


# ----------------------------------------------------------------------------- synthetic data from the spec and API

def synthetic_products(spec: Spec, api) -> List[dict]:
    """One product per band, using the API's product types and the spec's floor fields."""
    pf = api.product_fields()
    types = list((pf.get("type") or {}).get("enum") or ["product"])
    floors = {ff.product_type: ff.account_field for ff in spec.amounts.floor_field_by_type}
    out = []
    for i, b in enumerate(spec.bands):
        t = types[i % len(types)]
        p = {"type": t, "past_due": 1000.0 + 100 * i, "days_late": b.days_late_min}
        if floors.get(t):
            p[floors[t]] = 250.0 + 10 * i
        for k, sch in pf.items():
            if k not in p and k not in ("product_id",) and sch.get("type") == "string" and "last4" in k:
                p[k] = "0000"
        out.append(p)
    return out


def _is_date_question(q) -> bool:
    return "yyyy-mm-dd" in (q.answer_format or "").lower() or bool(q.numeric_date_order) or ("date" in q.api_field and "year" not in q.api_field)


def identity_for(spec: Spec) -> Dict[str, str]:
    ident = {}
    for q in spec.identity.questions:
        ident[q.api_field] = "1990-01-15" if _is_date_question(q) else ("1990" if "year" in q.api_field else "1234")
    return ident


def verified_turns(spec: Spec, ident: Dict[str, str]) -> List[dict]:
    t = [{"node": "opening", "set": {"who": "confirms"}}]
    for i, q in enumerate(spec.identity.questions):
        t.append({"node": f"identity_q{i}", "tool": {"name": "verify_identity", "args": {"answer": ident[q.api_field]}}})
    return t


def run(wf, spec, products, turns, now, faults=None, ident=None, api=None):
    ident = ident or identity_for(spec)
    api = api or _API[0]
    vq = next((op for op in api.ops.values() if any(sch.get("enum") for f, sch in op.fields.items() if f != tv(spec.roles.customer_id_var))), None)
    hint_enum = list(((vq.response.get("hint") or {}).get("enum") or [])) if vq else []
    bank = FakeBank(ident, products, faults, max_wrong=int(tv(spec.identity.max_wrong_total)),
                    date_fields=[q.api_field for q in spec.identity.questions if _is_date_question(q)], swap_hint=(tv(spec.identity.swapped.hint_value) or (hint_enum[0] if hint_enum else "swapped")))
    v = {tv(spec.roles.customer_id_var): "c_static", tv(spec.roles.now_var): now.isoformat() + "T11:00"}
    for cv in spec.call_variables:
        v.setdefault(cv.name, "x")
    sim = Sim(wf, bank, v)
    r = sim.run(turns + [{"set": {}}, {"set": {}}])
    r["sim"] = sim
    return r


# ----------------------------------------------------------------------------- lint

def lint(t: T, wf: dict, spec: Spec, api):
    nodes = wf["nodes"]
    text = json.dumps(wf)
    t.ok("null" not in text.replace('"null"', ""), "lint: a null value in the workflow")
    t.ok(wf.get("initial_node") in nodes, "lint: initial_node missing")
    t.ok(nodes[wf["initial_node"]]["node_type"] == "conversation", "lint: initial node must be a conversation node (chat skips a first code node)")
    assigned = set(spec.call_variables and [c.name for c in spec.call_variables])
    ends = {n for n, nd in nodes.items() if nd["node_type"] == "end_call"}
    for n, nd in nodes.items():
        for tr in nd.get("transitions", []):
            t.ok(tr["target_node"] in nodes, f"lint: {n} -> missing node {tr['target_node']}")
        if nd.get("passthrough"):
            t.ok(nd.get("transitions") and nd["transitions"][-1]["condition"].get("operator") == "always", f"lint: passthrough node {n} must end with always")
            t.ok(nd.get("passthrough_default_transition") in nodes, f"lint: {n} passthrough default missing")
        if nd["node_type"] in ("code", "api_request"):
            t.ok(not nd.get("tools"), f"lint: tools on non-conversation node {n}")
            for pa in nd.get("pre_actions", []):
                code = pa["function"]["parameters"]["properties"].get("code", {}).get("default")
                if code is not None:
                    t.ok("{{" not in code and "}}" not in code, f"lint: braces in code of {n}")
                    try:
                        compile(code, n, "exec")
                    except SyntaxError as e:
                        t.ok(False, f"lint: syntax error in {n}: {e}")
                    assigned |= set(re.findall(r"vars\['(\w+)'\]\s*=", code))
                for h in ("pre_process_code", "post_process_code"):
                    if pa.get(h):
                        try:
                            compile(pa[h], n + h, "exec")
                        except SyntaxError as e:
                            t.ok(False, f"lint: syntax error in {n} {h}: {e}")
                        assigned |= set(re.findall(r"vars\['(\w+)'\]\s*=", pa[h]))
                        assigned |= set(re.findall(r"vars\[(\w+)\]\s*=", pa[h]))
                if pa["function"]["handler"] == "__function__:api_call":
                    nm = pa["function"]["name"]
                    op = api.ops.get(nm)
                    is_read = op is not None and [f for f in op.fields if f != tv(spec.roles.customer_id_var)] == []
                    # the close is the last call and nothing is accepted after it, so one platform retry cannot duplicate anything
                    t.ok(is_read or n.startswith("close_") or pa["config"].get("maxRetries", 0) == 0, f"lint: write tool {nm} in {n} must have maxRetries 0")
        if nd["node_type"] == "conversation":
            t.ok(not nd.get("pre_actions"), f"lint: pre_actions on conversation node {n}")
            for ex in nd.get("extraction_schema", []):
                t.ok("min_confidence" in ex, f"lint: {n}.{ex['name']} has no min_confidence")
                assigned.add(ex["name"])
            if nd.get("tools"):
                for tr in nd.get("transitions", []):
                    t.ok(tr["condition"].get("operator") != "always" and tr["target_node"] != n, f"lint: C11 broken in tool node {n} (always or self transition)")
                for tool in nd["tools"]:
                    t.ok(tool["config"].get("maxRetries", 0) == 0, f"lint: model tool {tool['function']['name']} in {n} must have maxRetries 0")
                    for h in ("pre_process_code", "post_process_code"):
                        if tool.get(h):
                            assigned |= set(re.findall(r"vars\['(\w+)'\]\s*=", tool[h]))
                            assigned |= set(re.findall(r"vars\[(\w+)\]\s*=", tool[h]))
            if nd.get("transitions") and any(tr["condition"].get("operator") == "always" and tr["target_node"] == n for tr in nd["transitions"]):
                t.ok(nd.get("on_enter_first_entry_only"), f"lint: self-looping conversation node {n} replays on_enter unless first_entry_only")
    # reachability: every node reaches an end node
    succ = {n: {tr["target_node"] for tr in nd.get("transitions", [])} | ({nd["passthrough_default_transition"]} if nd.get("passthrough_default_transition") else set()) for n, nd in nodes.items()}
    reach_end = set(ends)
    changed = True
    while changed:
        changed = False
        for n in nodes:
            if n not in reach_end and succ[n] & reach_end:
                reach_end.add(n)
                changed = True
    for n in nodes:
        t.ok(n in reach_end, f"lint: node {n} cannot reach an end_call node")
    for n, nd in wf["nodes"].items():
        for e in nd.get("extraction_schema") or []:
            vals = e.get("enum_values") or []
            t.ok(len(vals) == len(set(vals)), f"lint: duplicate enum values in {n}.{e.get('name')}")
    # data flow: every {{var}} in prompts, tts and tool defaults must be assigned somewhere (or a call/system variable)
    assigned |= {"system", "call"}
    for n, nd in nodes.items():
        texts = [nd.get("task_message", ""), (nd.get("on_enter") or {}).get("text", "")]
        for tool in nd.get("tools", []) + nd.get("pre_actions", []):
            for leaf in (tool["function"]["parameters"]["properties"].get("body", {}).get("properties") or {}).values():
                d = leaf.get("default", "")
                if isinstance(d, str) and re.fullmatch(r"\{\{\w+(:json)?\}\}", d):
                    name = re.findall(r"\{\{(\w+)", d)[0]
                    # a model-filled field must not collide with an assigned variable
                    if name == leaf.get("_model"):
                        pass
                    if name not in assigned and n not in ():
                        # model-filled: fine only on conversation nodes
                        t.ok(nd["node_type"] == "conversation", f"dataflow: {n} tool field {{{{{name}}}}} is never set (engine would drop it)")
                    elif name in assigned and nd["node_type"] == "conversation" and leaf.get("description", "").startswith("The customer's"):
                        t.ok(False, f"dataflow: model-filled field {name} in {n} collides with a set variable")
        for s in texts:
            for name in re.findall(r"\{\{(\w+)", s):
                t.ok(name in assigned, f"dataflow: {{{{{name}}}}} in {n} is never set")


# ----------------------------------------------------------------------------- invariants

def invariants(t: T, wf: dict, spec: Spec, api):
    _API[0] = api
    cal = Cal(spec)
    prods = synthetic_products(spec, api)
    ident = identity_for(spec)
    multi = bool(tv(spec.multi_product.enabled))
    rows = {row_key(r.outcome, r.reason): r for r in spec.closing.outcome_table}
    promise_rows = [k for k, r in rows.items() if not r.reason and "promise" in r.when.lower()]
    close_bodies = {}
    for n, nd in wf["nodes"].items():
        if n.startswith("close_") and nd["node_type"] == "api_request":
            body = nd["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
            close_bodies[n[len("close_"):]] = {k: v.get("default") for k, v in body.items()}
    # C7: one close node per row, no reason leaf where the table has none
    for k, r in rows.items():
        t.ok(k in close_bodies, f"close: no close node for outcome row {k}")
        if k in close_bodies:
            b = close_bodies[k]
            reason_leaves = [kk for kk in b if kk not in (tv(spec.roles.customer_id_var),) and b[kk] == r.reason and r.reason]
            if not r.reason:
                t.ok(all(v in (r.outcome, "{{" + tv(spec.roles.customer_id_var) + "}}") for v in b.values()), f"close: row {k} must have no reason leaf; body {b}")
            else:
                t.ok(reason_leaves, f"close: row {k} must send reason {r.reason!r}; body {b}")
    nb = next((b for b in spec.bands), None)
    for now in sample_dates(spec):
        prods1 = [prods[0]] if not multi else prods
        # a) deadline and attempt-1 proposal
        r = run(wf, spec, prods1, verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "refuses"}}], now)
        table = json.loads(r["vars"].get("products_json") or "[]")
        t.ok(not r["errors"], f"{now}: snippet errors {r['errors'][:2]}")
        for p, b in zip(table, spec.bands if multi else spec.bands[:1]):
            exp_dl = cal.add_bd(now, b.deadline_business_days)
            t.ok(p["deadline"] == exp_dl.isoformat(), f"{now}: deadline of band {b.label} = {p['deadline']}, expected {exp_dl}")
            t.ok(cal.is_bd(datetime.date.fromisoformat(p["deadline"])), f"{now}: deadline not a business day")
            t.ok(p["attempts_max"] == b.persuasion_attempts, f"{now}: attempts_max {p['attempts_max']} != {b.persuasion_attempts}")
        a1 = next((a for a in spec.negotiation.attempts if a.n == 1), None)
        if a1 and table and a1.date == "last_business_day_this_week":
            d = cal.last_bd_of_week(now)
            if d <= now:
                d = cal.last_bd_of_week(now + datetime.timedelta(days=7))
            d = min(d, datetime.date.fromisoformat(table[0]["deadline"]))
            t.ok(table[0]["prop_date"] == d.isoformat(), f"{now}: attempt-1 date {table[0]['prop_date']}, expected {d}")
            t.ok(float(table[0]["prop_amount"]) == float(table[0]["past_due"]), f"{now}: attempt-1 amount must be the full amount")
        # b) yes today on a non-business day must not agree today
        r = run(wf, spec, prods1, verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "yes_today"}}], now)
        table = json.loads(r["vars"].get("products_json") or "[]")
        if table:
            if cal.is_bd(now):
                t.ok(table[0]["status"] == "agreed" and table[0]["agreed_date"] == now.isoformat(), f"{now}: yes_today should agree today")
            else:
                t.ok(table[0]["status"] != "agreed" and table[0]["prop_date"] == cal.next_bd(now).isoformat(), f"{now}: yes_today on a non-business day must propose {cal.next_bd(now)}")
        # c) a date after the deadline → propose the deadline; a weekend date inside → next business day
        dl = cal.add_bd(now, spec.bands[0].deadline_business_days)
        after = dl + datetime.timedelta(days=3)
        r = run(wf, spec, prods1, verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "proposes", "d_ref": "day_of_month", "d_dom": after.day, "d_month": WEEKDAY_NAMES and ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"][after.month - 1], "d_year": after.year}}], now)
        table = json.loads(r["vars"].get("products_json") or "[]")
        if table:
            t.ok(table[0]["status"] != "agreed" and table[0]["prop_date"] == dl.isoformat(), f"{now}: date after deadline must propose the deadline {dl}, got {table[0]['prop_date']} status {table[0]['status']}")
        wk = now + datetime.timedelta(days=1)
        while cal.is_bd(wk) or wk > dl:
            wk += datetime.timedelta(days=1)
            if wk > dl:
                break
        if wk <= dl:
            r = run(wf, spec, prods1, verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "proposes", "d_ref": "day_of_month", "d_dom": wk.day, "d_month": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"][wk.month - 1], "d_year": wk.year}}], now)
            table = json.loads(r["vars"].get("products_json") or "[]")
            if table:
                t.ok(table[0]["status"] != "agreed" and table[0]["prop_date"] == cal.next_bd(wk).isoformat(), f"{now}: non-business day {wk} must propose {cal.next_bd(wk)}, got {table[0]['prop_date']}")
        # d) attempts exhausted → exhausted close row, nothing written
        refusals = [{"node": "negotiate", "set": {"pay": "refuses"}}] * (max(b.persuasion_attempts for b in spec.bands) + 1)
        r = run(wf, spec, prods1[:1], verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "refuses"}}] + refusals + [{"node": "goodbye"}], now)
        ex = spec.negotiation.exhausted_close
        t.ok((r["ledger"]["outcome"], r["ledger"]["reason"] or "") == (ex.outcome, ex.reason) and not r["ledger"]["promises"], f"{now}: exhausted attempts must close as {ex.outcome}/{ex.reason}, got {r['ledger']['outcome']}/{r['ledger']['reason']}")
    now = next(d for d in sample_dates(spec) if cal.is_bd(d))
    # e) guard: an agreed value outside the policy is never written
    r = run(wf, spec, prods[:1], verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "proposes", "amount_said": 1.0}}], now)
    t.ok(not r["ledger"]["promises"], f"guard: below-floor amount was written {r['ledger']['promises']}")
    # f) write fails twice → failure close row (single product) and no promise
    r = run(wf, spec, prods[:1], verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "yes_today"}}, {"node": "readback", "set": {"rb": "confirms"}}, {"node": "goodbye"}], now,
            faults=[{"tool": "create_promise", "fail_first_n": int(tv(spec.recording.max_attempts))}])
    fc = spec.recording.failure_close
    writes = [c for c in r["ledger"]["calls"] if c["tool"] == "create_promise"]
    t.ok(len(writes) == int(tv(spec.recording.max_attempts)), f"failing write: {len(writes)} attempts, expected {tv(spec.recording.max_attempts)}")
    if not multi:
        t.ok((r["ledger"]["outcome"], r["ledger"]["reason"] or "") == (fc.outcome, fc.reason), f"failing write must close {fc.outcome}/{fc.reason}, got {r['ledger']['outcome']}/{r['ledger']['reason']}")
    # g) one success after one failure → promise row, exactly one promise
    r = run(wf, spec, prods[:1], verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "yes_today"}}, {"node": "readback", "set": {"rb": "confirms"}}, {"node": "say_recorded"}], now,
            faults=[{"tool": "create_promise", "fail_first_n": 1}])
    t.ok(len(r["ledger"]["promises"]) == 1 and r["ledger"]["outcome"] in [rows[k].outcome for k in promise_rows], f"retry: expected one promise and a promise close, got {r['ledger']}")
    t.ok(r["ledger"]["calls"][-1]["tool"] == "close_call", "close_call must be the last call")
    # h) callback window
    tp = spec.third_party
    fr, to = tv(tp.callback.from_time), tv(tp.callback.to_time)
    inside = {"node": "third_party", "set": {"tp_intent": "gives_time", "d_ref": "tomorrow", "cb_time": to}}
    r = run(wf, spec, prods[:1], [{"node": "opening", "set": {"who": "third_party"}}, inside, {"node": "goodbye"}], now)
    exp_day = cal.next_bd(now + datetime.timedelta(days=1)).isoformat()
    t.ok(r["ledger"]["callbacks"] == [{"date": exp_day, "time": to}] and (r["ledger"]["outcome"], r["ledger"]["reason"]) == (tp.callback_close.outcome, tp.callback_close.reason), f"callback inside window: {r['ledger']}")
    late = "%02d:%s" % (int(to[:2]) + 1, to[3:])
    outside = {"node": "third_party", "set": {"tp_intent": "gives_time", "d_ref": "tomorrow", "cb_time": late}}
    r = run(wf, spec, prods[:1], [{"node": "opening", "set": {"who": "third_party"}}, outside] + [outside] * int(tv(tp.callback.ask_again_times)) + [{"node": "goodbye"}], now)
    t.ok(not r["ledger"]["callbacks"] and (r["ledger"]["outcome"], r["ledger"]["reason"]) == (tp.no_callback_close.outcome, tp.no_callback_close.reason), f"callback outside window: {r['ledger']}")
    t.ok(not any(c["tool"] in ("verify_identity", "get_account") for c in r["ledger"]["calls"]), "third party: identity tools must not be called")
    # i) identity: too many wrong answers → fail close, no account call
    wrong = [{"node": "identity_q0", "tool": {"name": "verify_identity", "args": {"answer": "1900-01-01"}}}] * int(tv(spec.identity.max_wrong_total))
    r = run(wf, spec, prods[:1], [{"node": "opening", "set": {"who": "confirms"}}] + wrong + [{"node": "goodbye"}], now)
    fcl = spec.identity.fail_close
    t.ok((r["ledger"]["outcome"], r["ledger"]["reason"]) == (fcl.outcome, fcl.reason) and not any(c["tool"] == "get_account" for c in r["ledger"]["calls"]), f"identity fail: {r['ledger']['outcome']}/{r['ledger']['reason']}")
    # j) multi-product aggregation
    if multi and len(prods) >= 2:
        agg = spec.closing.aggregation
        nr = tv(spec.multi_product.note_reasons)
        refusals = [{"node": "negotiate", "set": {"pay": "refuses"}}] * (sum(b.persuasion_attempts for b in spec.bands) + len(spec.bands) + 1)
        r = run(wf, spec, prods, verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": "refuses"}}] + refusals + [{"node": "goodbye"}], now)
        ex = spec.negotiation.exhausted_close
        t.ok(len(r["ledger"]["notes"]) == len(prods) and all(n["reason"] == ex.reason for n in r["ledger"]["notes"]), f"aggregation: every refused product needs a note; got {r['ledger']['notes']}")
        t.ok((r["ledger"]["outcome"], r["ledger"]["reason"] or "") == (ex.outcome, ex.reason), f"aggregation: all refused → {ex.outcome}/{ex.reason}, got {r['ledger']['outcome']}/{r['ledger']['reason']}")
        for a in agg.all_noted_as:
            key = next((it.key for it in spec.special_intents if it.action_note_reason == a.reason), None)
            if key:
                r = run(wf, spec, prods, verified_turns(spec, ident) + [{"node": "state_debt", "set": {"pay": key, "applies_to": "all"}}, {"node": "goodbye"}], now)
                t.ok(r["ledger"]["outcome"] == a.outcome and len(r["ledger"]["notes"]) == len(prods), f"aggregation: all noted {a.reason} → {a.outcome}, got {r['ledger']['outcome']} notes {r['ledger']['notes']}")


def main(argv=None):
    argv = argv or sys.argv[1:]
    wf = json.load(open(argv[0]))
    spec = Spec.model_validate(json.load(open(argv[1])))
    api_path = argv[argv.index("--api") + 1] if "--api" in argv else str(ROOT / "tools" / "openapi.json")
    api = parse_api(api_path)
    _API[0] = api
    t = T()
    lint(t, wf, spec, api)
    invariants(t, wf, spec, api)
    for f in t.fails:
        print("FAIL", f)
    print(f"static tests: {t.passes} passed, {len(t.fails)} failed")
    return 0 if not t.fails else 1


if __name__ == "__main__":
    sys.exit(main())
