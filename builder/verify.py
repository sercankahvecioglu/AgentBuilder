"""Verify stage, code checks (DEV_PLAN T4.1, T4.2a).

verify(spec, facts, resolution, api_summary, inputs_text) -> list[Issue]
- enum and field checks against the tool API (identity fields, queues, note reasons, outcomes, product types, account fields)
- close (outcome, reason) pairs are rows of the spec's outcome table
- formats: ISO dates, HH:MM times, contiguous bands, attempt vocabulary
- provenance: every leaf cites existing, governing (non-discussion, non-overridden) facts
- numbers and times re-parsed from the cited facts' source quotes (digits and number words)
- required phrases are verbatim substrings of the inputs
- T4.2a: every governing decision fact is used by some leaf (warning)
Errors feed one re-extract (T4.3); warnings go to the trace.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterator

from pydantic import BaseModel

from builder.resolve import Resolution, numbers_in
from builder.schema import Fact, Spec

WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
DATE_ORDERS = {"day_month_year", "month_day_year", "year_month_day", ""}
ATTEMPT_AMOUNTS = {"full", "floor", "floor_if_full_refused"}
ATTEMPT_DATE_RE = re.compile(r"^(today|last_business_day_this_week|next_business_day|deadline|nth_business_day:\d+)$")
ACTION_KINDS = {"none", "transfer", "note", "callback"}

# tool names are fixed by the challenge; fields and enums come from the file
T_VERIFY, T_ACCOUNT, T_PROMISE, T_NOTE, T_CALLBACK, T_TRANSFER, T_CLOSE = (
    "verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call")


class Issue(BaseModel):
    severity: str  # error | warn
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"


# ---------------------------------------------------------------------------
# spec walking
# ---------------------------------------------------------------------------


def leaves(obj: Any, path: str = "") -> Iterator[tuple[str, dict]]:
    """Yield (path, node) for every node that carries fact_ids."""
    if isinstance(obj, dict):
        if "fact_ids" in obj:
            yield path, obj
        for k, v in obj.items():
            if k != "fact_ids":
                yield from leaves(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for n, v in enumerate(obj):
            yield from leaves(v, f"{path}[{n}]")


def _enum_fields(op: dict | None) -> dict[str, list[str]]:
    return {f: fs["enum"] for f, fs in (op or {}).get("fields", {}).items() if fs.get("enum")}


def _pick_enum(op: dict | None, *preferred: str) -> tuple[str, list[str]] | None:
    """The enum field named like one of `preferred`, else the only enum body field (ignoring customer id)."""
    enums = _enum_fields(op)
    for p in preferred:
        for f, e in enums.items():
            if p in f:
                return f, e
    enums = {f: e for f, e in enums.items() if "customer" not in f}
    if len(enums) == 1:
        return next(iter(enums.items()))
    return None


def _product_props(api: dict) -> dict[str, dict]:
    """Properties of the product item in get_account's 200 response, keyed without the array prefix."""
    op = api["operations"].get(T_ACCOUNT) or {}
    props = ((op.get("responses") or {}).get("200") or {}).get("properties") or {}
    out = {}
    for k, v in props.items():
        if "[]." in k:
            out[k.split("[].", 1)[1]] = v
    return out


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------


def verify(spec: Spec, facts: list[Fact], res: Resolution, api: dict, inputs_text: str = "") -> list[Issue]:
    d = spec.model_dump()
    issues: list[Issue] = []
    err = lambda p, m: issues.append(Issue(severity="error", path=p, message=m))  # noqa: E731
    warn = lambda p, m: issues.append(Issue(severity="warn", path=p, message=m))  # noqa: E731
    ops = api["operations"]
    by_id = {f.id: f for f in facts}
    governing = set(res.governing_ids)

    # --- tool API enums ---------------------------------------------------
    id_enum = _pick_enum(ops.get(T_VERIFY), "field", "question", "type")
    if id_enum:
        for n, q in enumerate(d["identity"]["questions"]):
            if q["api_field"] not in id_enum[1]:
                err(f"identity.questions[{n}].api_field", f"'{q['api_field']}' not in {T_VERIFY}.{id_enum[0]} enum {id_enum[1]}")
    else:
        warn("identity.questions", f"{T_VERIFY} has no enum field; api_field values not checked")
    if not d["identity"]["questions"]:
        err("identity.questions", "no identity questions")

    queue_enum = _pick_enum(ops.get(T_TRANSFER), "queue", "department", "team")
    note_enum = _pick_enum(ops.get(T_NOTE), "reason", "code", "type")
    close_op = ops.get(T_CLOSE) or {}
    outcome_enum = _pick_enum(close_op, "outcome", "result", "status")
    outcomes = set(outcome_enum[1]) if outcome_enum else set()
    table_pairs = {(r["outcome"], r["reason"]) for r in d["closing"]["outcome_table"]}
    table_reasons = {r["reason"] for r in d["closing"]["outcome_table"] if r["reason"]}

    for n, r in enumerate(d["closing"]["outcome_table"]):
        if outcomes and r["outcome"] not in outcomes:
            err(f"closing.outcome_table[{n}].outcome", f"'{r['outcome']}' not in {T_CLOSE} enum {sorted(outcomes)}")
    if not d["closing"]["outcome_table"]:
        err("closing.outcome_table", "empty outcome table")

    for path, node in leaves(d):
        if set(node) == {"outcome", "reason", "fact_ids"} and not path.startswith("closing.aggregation.all_noted_as"):  # a Close leaf
            if outcomes and node["outcome"] not in outcomes:
                err(path, f"outcome '{node['outcome']}' not in {T_CLOSE} enum")
            if (node["outcome"], node["reason"]) not in table_pairs:
                err(path, f"({node['outcome']}, {node['reason'] or '-'}) is not a row of closing.outcome_table")

    for n, it in enumerate(d["special_intents"]):
        p = f"special_intents[{n}]({it['key']})"
        if it["action_kind"] not in ACTION_KINDS:
            err(p + ".action_kind", f"'{it['action_kind']}' not in {sorted(ACTION_KINDS)}")
        if it["action_kind"] == "transfer":
            if not it["action_queue"]:
                err(p + ".action_queue", "transfer without a queue")
            elif queue_enum and it["action_queue"] not in queue_enum[1]:
                err(p + ".action_queue", f"'{it['action_queue']}' not in {T_TRANSFER}.{queue_enum[0]} enum {queue_enum[1]}")
        if it["action_kind"] == "note":
            if not it["action_note_reason"]:
                err(p + ".action_note_reason", "note without a reason")
            elif note_enum and it["action_note_reason"] not in note_enum[1]:
                err(p + ".action_note_reason", f"'{it['action_note_reason']}' not in {T_NOTE}.{note_enum[0]} enum")
        for o, r in (("close_outcome", "close_reason"), ("declined_close_outcome", "declined_close_reason"),
                     ("before_identity_close_outcome", "before_identity_close_reason")):
            if it[o]:
                if outcomes and it[o] not in outcomes:
                    err(f"{p}.{o}", f"'{it[o]}' not in {T_CLOSE} enum")
                if (it[o], it[r]) not in table_pairs:
                    err(f"{p}.{o}", f"({it[o]}, {it[r] or '-'}) is not a row of closing.outcome_table")
            elif it[r]:
                err(f"{p}.{r}", "reason without outcome")
        if not it["close_outcome"] and not it["continue_call"] and not it["continue_other_products"] and it["action_kind"] != "transfer":
            warn(p, "no close, no continue flag: the call has nowhere to go")

    note_reasons = list(d["multi_product"]["note_reasons"]["values"])
    if d["recording"]["failure_note_reason"]["value"]:
        note_reasons.append(d["recording"]["failure_note_reason"]["value"])
    for nr in note_reasons:
        if note_enum and nr not in note_enum[1]:
            err("multi_product.note_reasons", f"'{nr}' not in {T_NOTE}.{note_enum[0]} enum {note_enum[1]}")
        elif not note_enum and nr not in table_reasons:
            warn("multi_product.note_reasons", f"'{nr}' is neither an API enum value nor an outcome-table reason")
    for n, ro in enumerate(d["closing"]["aggregation"]["all_noted_as"]):
        if outcomes and ro["outcome"] not in outcomes:
            err(f"closing.aggregation.all_noted_as[{n}]", f"outcome '{ro['outcome']}' not in {T_CLOSE} enum")

    # --- product types and account fields ----------------------------------
    pprops = _product_props(api)
    ptype_enum = next((v["enum"] for k, v in pprops.items() if v.get("enum") and ("type" in k or "product" in k)), None)
    if ptype_enum:
        for section, rows in (("debt_statement.product_labels", d["debt_statement"]["product_labels"]),
                              ("amounts.floor_field_by_type", d["amounts"]["floor_field_by_type"])):
            seen = {r["product_type"] for r in rows}
            for n, r in enumerate(rows):
                if r["product_type"] not in ptype_enum:
                    err(f"{section}[{n}].product_type", f"'{r['product_type']}' not in product type enum {ptype_enum}")
            for t in ptype_enum:
                if t not in seen:
                    warn(section, f"product type '{t}' has no row")
    if pprops:
        for n, r in enumerate(d["amounts"]["floor_field_by_type"]):
            if r["account_field"] not in pprops:
                err(f"amounts.floor_field_by_type[{n}].account_field", f"'{r['account_field']}' is not a product field {sorted(pprops)}")
        for inc in d["debt_statement"]["include"]["values"]:
            if inc not in pprops:
                warn("debt_statement.include", f"'{inc}' is not a product field")

    # --- formats ----------------------------------------------------------
    for hd in d["calendar"]["holidays"]["values"]:
        if not _iso(hd):
            err("calendar.holidays", f"'{hd}' is not an ISO date")
    for wd in d["calendar"]["business_weekdays"]["values"]:
        if wd.lower() not in WEEKDAYS:
            err("calendar.business_weekdays", f"'{wd}' is not a weekday name")
    if not d["calendar"]["business_weekdays"]["values"]:
        err("calendar.business_weekdays", "empty")
    for k in ("numeric_date_order",):
        if d["calendar"][k]["value"] not in DATE_ORDERS:
            err(f"calendar.{k}", f"'{d['calendar'][k]['value']}' not in {sorted(DATE_ORDERS)}")
    cb = d["third_party"]["callback"]
    ft, tt = cb["from_time"]["value"], cb["to_time"]["value"]
    for k, v in (("from_time", ft), ("to_time", tt)):
        if v and not re.fullmatch(r"\d{2}:\d{2}", v):
            err(f"third_party.callback.{k}", f"'{v}' is not HH:MM")
    if re.fullmatch(r"\d{2}:\d{2}", ft or "") and re.fullmatch(r"\d{2}:\d{2}", tt or "") and ft >= tt:
        err("third_party.callback", f"from_time {ft} is not before to_time {tt}")
    bands = sorted(d["bands"], key=lambda b: b["days_late_min"])
    if not bands:
        err("bands", "no bands")
    for n, bd in enumerate(bands):
        if bd["days_late_min"] > bd["days_late_max"]:
            err(f"bands[{n}]", "days_late_min > days_late_max")
        if bd["deadline_business_days"] < 1 or bd["persuasion_attempts"] < 0:
            err(f"bands[{n}]", "deadline_business_days < 1 or negative attempts")
        if n and bd["days_late_min"] != bands[n - 1]["days_late_max"] + 1:
            err(f"bands[{n}]", f"bands are not contiguous ({bands[n-1]['days_late_max']} then {bd['days_late_min']})")
    labels = {bd["label"] for bd in bands}
    ns = [a["n"] for a in d["negotiation"]["attempts"]]
    if ns != list(range(1, len(ns) + 1)):
        err("negotiation.attempts", f"attempt numbers {ns} are not 1..k")
    for n, a in enumerate(d["negotiation"]["attempts"]):
        if a["amount"] not in ATTEMPT_AMOUNTS:
            err(f"negotiation.attempts[{n}].amount", f"'{a['amount']}' not in {sorted(ATTEMPT_AMOUNTS)}")
        if not ATTEMPT_DATE_RE.match(a["date"]):
            err(f"negotiation.attempts[{n}].date", f"'{a['date']}' not a known date token")
        for lb in a["bands_allowed"]:
            if lb not in labels:
                err(f"negotiation.attempts[{n}].bands_allowed", f"'{lb}' is not a band label {sorted(labels)}")
    max_att = max((bd["persuasion_attempts"] for bd in bands), default=0)
    if bands and len(ns) < max_att:
        err("negotiation.attempts", f"{len(ns)} attempts defined but a band allows {max_att}")
    for n, q in enumerate(d["identity"]["questions"]):
        if q["numeric_date_order"] not in DATE_ORDERS:
            err(f"identity.questions[{n}].numeric_date_order", f"'{q['numeric_date_order']}'")

    # --- provenance -------------------------------------------------------
    used: set[str] = set()
    for path, node in leaves(d):
        ids = node.get("fact_ids") or []
        if not ids:
            err(path, "no fact_ids")
        for i in ids:
            used.add(i)
            f = by_id.get(i)
            if f is None:
                err(path, f"unknown fact id {i}")
            elif f.kind == "discussion":
                err(path, f"cites discussion fact {i}")
            elif i not in governing:
                err(path, f"cites overridden fact {i}")

    # --- numbers, times and dates re-parsed from quotes ---------------------
    def quotes(ids: list[str]) -> str:
        return " ".join(by_id[i].source_quote + " " + by_id[i].text for i in ids if i in by_id)

    RETRY_RE = re.compile(r"\b(once more|one more time|try again|tried again|retry|retried)\b", re.I)

    def check_num(path: str, value: float, ids: list[str], what: str = "number") -> None:
        q = quotes(ids)
        if not q:
            return
        nums = numbers_in(q)
        if float(value) in nums:
            return
        if value == 2 and RETRY_RE.search(q):
            return  # "try once more" = 2 attempts in total: a derived count
        if not nums:
            warn(path, f"{what} {value}: the cited quotes carry no number to check against")
            return
        err(path, f"{what} {value} does not appear in the cited quotes: {q[:120]!r}")

    for path, node in leaves(d):
        if set(node) == {"value", "fact_ids"} and isinstance(node["value"], int) and not isinstance(node["value"], bool):
            if path.startswith("multi_product.") and not d["multi_product"]["enabled"]["value"]:
                continue
            check_num(path, node["value"], node["fact_ids"])
        if set(node) == {"value", "fact_ids"} and isinstance(node["value"], str) and re.fullmatch(r"\d{2}:\d{2}", node["value"]):
            q = quotes(node["fact_ids"])
            if q and node["value"] not in q and node["value"].lstrip("0") not in q:
                err(path, f"time {node['value']} does not appear in the cited quotes")
    for n, bd in enumerate(d["bands"]):
        for k in ("days_late_min", "days_late_max", "deadline_business_days", "persuasion_attempts"):
            check_num(f"bands[{n}].{k}", bd[k], bd["fact_ids"], k)
    hq = quotes(d["calendar"]["holidays"]["fact_ids"])
    if hq:
        for hd in d["calendar"]["holidays"]["values"]:
            if hd not in hq:
                err("calendar.holidays", f"{hd} does not appear in the cited quotes")
    for n, it in enumerate(d["special_intents"]):
        if it["count_before_action"] > 1:
            check_num(f"special_intents[{n}].count_before_action", it["count_before_action"], it["fact_ids"], "count")

    # --- required phrases verbatim in the inputs ------------------------------
    if inputs_text:
        norm_inputs = _norm_text(inputs_text)
        for n, ph in enumerate(d["required_phrases"]):
            pat = re.escape(_norm_text(ph["text"]))
            pat = re.sub(r"\\\{\w+\\\}", r".{1,40}?", pat)
            if not re.search(pat, norm_inputs):
                err(f"required_phrases[{n}]", f"not a verbatim substring of the inputs: {ph['text']!r}")

    # --- T4.2a: every governing decision fact is used ------------------------
    for f in facts:
        if f.id in governing and f.kind == "decision" and f.id not in used:
            warn("facts", f"governing decision fact {f.id} is not cited by any leaf: {f.text[:90]!r}")
    return issues


def _iso(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


def _norm_text(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]


def feedback(issues: list[Issue]) -> str:
    return "\n".join(f"- {i.path}: {i.message}" for i in errors(issues))


if __name__ == "__main__":
    import json
    import sys

    from builder.inputs import api_summary, load_api, load_text_inputs
    from builder.schema import Extraction, load_spec

    spec_p, facts_p, res_p, api_p, *texts = sys.argv[1:]
    spec = load_spec(spec_p)
    ex = Extraction.model_validate(json.load(open(facts_p)))
    res = Resolution.model_validate(json.load(open(res_p)))
    api = api_summary(load_api(api_p))
    text = load_text_inputs(texts) if texts else ""
    out = verify(spec, ex.facts, res, api, text)
    for i in out:
        print(i)
    print(f"{len(errors(out))} error(s), {len(out) - len(errors(out))} warning(s)")
    sys.exit(1 if errors(out) else 0)
