"""Generate the Freya workflow from a Spec and the tool API (code only, no LLM; DEV_PLAN §2.4, T5.4).

Everything spoken or decided comes from the spec or the OpenAPI file. Node keys and variable names are the generator's
own vocabulary; no value of any particular brief appears in this file.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Dict, List

from .openapi_tools import Api, api_tool, numeric_fields
from .schema import Spec

HERE = pathlib.Path(__file__).resolve().parent
SNIP = HERE / "templates" / "snippets"

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MIN_CONF = 0.6


# ----------------------------------------------------------------------------- small helpers

def inject(name: str, obj) -> str:
    """C14: a constant as `name = json.loads(<python repr of json text>)`; never a raw JSON literal."""
    text = json.dumps(obj, indent=1, ensure_ascii=False)
    assert "{{" not in text and "}}" not in text, "double braces in injected constant"
    return f"import json\n{name} = json.loads({text!r})\n"


def always(target: str) -> dict:
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def eq(target: str, var: str, value, desc: str = "") -> dict:
    return {"target_node": target, "description": desc or f"{var} is {value}",
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": value}]}}


def anyof(target: str, var: str, values: List[str], desc: str = "") -> dict:
    return {"target_node": target, "description": desc or f"{var} in {values}",
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": v} for v in values]}}


def gte(target: str, var: str, value, desc: str = "") -> dict:
    return {"target_node": target, "description": desc or f"{var} >= {value}",
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "greater_than", "operand": value - 1}]}}


def code_node(name: str, code: str, default: str, transitions: List[dict]) -> dict:
    assert "{{" not in code and "}}" not in code, f"double braces in code of {name}"
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": default,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                        "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                                        "timeout_ms": {"type": "number", "default": 15000}}}}}],
        "transitions": transitions + [always(default)],
    }


def api_node(name: str, tool: dict, default: str, transitions: List[dict]) -> dict:
    return {
        "name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": default,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "suppress_tool_results": True,
        "pre_actions": [tool], "response_mapping": [],
        "transitions": transitions + [always(default)],
    }


def end_node(name: str, fn: str) -> dict:
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": fn, "handler": "__function__:end_call",
                         "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}


def conv_node(name: str, task: str, transitions: List[dict], extraction: List[dict] = None, tools: List[dict] = None,
              on_enter: dict = None, first_only: bool = False, max_turns: int = 40) -> dict:
    n = {"name": name, "node_type": "conversation", "task_message": task, "transitions": transitions,
         "extraction_schema": extraction or [], "tools": tools or [], "max_node_turns": max_turns,
         "on_enter": on_enter or {"type": "llm"}, "truncation_strategy": "keep_all"}
    if first_only:
        n["on_enter_first_entry_only"] = True
    return n


def ev(name: str, values: List[str], desc: str) -> dict:
    return {"name": name, "type": "string", "enum_values": values, "description": desc, "min_confidence": MIN_CONF}


def row_key(outcome: str, reason: str) -> str:
    return outcome + ("__" + reason if reason else "")


IMPERATIVE = re.compile(r"^(say|state|tell|mention|announce|introduce|explain|inform|greet|open|start|begin|ask|make|give|confirm)\b", re.I)
LANG_NAMES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch", "pt": "Portuguese", "tr": "Turkish", "sv": "Swedish", "da": "Danish", "no": "Norwegian", "fi": "Finnish", "pl": "Polish"}


def is_instruction(text: str) -> bool:
    """True when an extracted 'sentence' is an instruction to the agent rather than words to speak."""
    s = (text or "").strip()
    return bool(IMPERATIVE.match(s)) and (" you " in f" {s.lower()} " or " that " in f" {s.lower()} " or s.lower().startswith(("say ", "tell ", "explain ", "mention ", "state ")))


def lang_name(x: str) -> str:
    x = (x or "").strip()
    return LANG_NAMES.get(x.lower(), x) if len(x) <= 3 else x


def tv(x):
    """Value of a spec leaf wrapper (S/I/B) or the raw value."""
    if hasattr(x, "value"):
        return x.value
    if hasattr(x, "values"):
        return list(x.values)
    return x


# ----------------------------------------------------------------------------- generator

class Generator:
    def __init__(self, spec: Spec, api: Api):
        self.spec = spec
        self.api = api
        self.cid = tv(spec.roles.customer_id_var)
        self.now = tv(spec.roles.now_var)
        self.multi = bool(tv(spec.multi_product.enabled))
        self.intents = {it.key: it for it in spec.special_intents}
        self.rows = [(r.outcome, r.reason) for r in spec.closing.outcome_table]
        self.row_keys = [row_key(o, r) for o, r in self.rows]
        self.prelude = (SNIP / "prelude.py").read_text()
        self.snips = {p.stem: p.read_text() for p in SNIP.glob("*.py") if p.stem != "prelude"}
        self.const = self.build_const()
        self.const_text = inject("CONST", self.const)
        self.notes: List[str] = []

    # ---- constants for the snippets
    def build_const(self) -> dict:
        s = self.spec
        cal = s.calendar
        bw = [WEEKDAY_NAMES.index(w.lower()) for w in tv(cal.business_weekdays) if w.lower() in WEEKDAY_NAMES] or [0, 1, 2, 3, 4]
        tp = s.third_party
        idn = s.identity
        neg = s.negotiation
        exhausted_note = neg.exhausted_close.reason if tv(s.multi_product.note_unpromised_products) else ""
        prod_fields = list(self.api.product_fields().keys())
        promise_rows = [k for (o, r), k in zip(self.rows, self.row_keys) if r == "" and o == self._promise_outcome()]
        fallback = row_key(neg.exhausted_close.outcome, neg.exhausted_close.reason)
        if fallback not in self.row_keys:
            fallback = self.row_keys[0] if self.row_keys else ""
        agg = s.closing.aggregation
        skip = []
        else_out = ""
        er = tv(agg.else_rule) or ""
        # else_rule of the form first_non_<reason>_note_reason_in_order → skip that reason; outcome = the one whose reasons include note reasons
        if er.startswith("first_non_"):
            skip = [er[len("first_non_"):].split("_note")[0]]
        for o, r in self.rows:
            if r and r in tv(s.multi_product.note_reasons):
                else_out = o
                break
        return {
            "now_var": self.now, "customer_id_var": self.cid,
            "cal": {"business_weekdays": bw, "holidays": list(tv(cal.holidays)), "next_weekday": tv(cal.next_weekday), "this_weekday": tv(cal.this_weekday)},
            "max_confirm_asks": int(tv(s.opening.max_confirm_asks)),
            "opening": {"unclear_outcome": s.opening.unclear_close.outcome, "unclear_reason": s.opening.unclear_close.reason},
            "third_party": {
                "allowed_days": list(tv(tp.callback.allowed_days)), "from_time": tv(tp.callback.from_time), "to_time": tv(tp.callback.to_time),
                "inclusive": bool(tv(tp.callback.inclusive)), "after_now": bool(tv(tp.callback.after_now)), "ask_again_times": int(tv(tp.callback.ask_again_times)),
                "callback_outcome": tp.callback_close.outcome, "callback_reason": tp.callback_close.reason,
                "no_callback_outcome": tp.no_callback_close.outcome, "no_callback_reason": tp.no_callback_close.reason,
                "wrong_number_outcome": tp.wrong_number_close.outcome, "wrong_number_reason": tp.wrong_number_close.reason,
                "deceased_outcome": tp.deceased_close.outcome, "deceased_reason": tp.deceased_close.reason,
                "deceased_sentence": tv(tp.deceased_sentence),
            },
            "identity": {
                "max_wrong_total": int(tv(idn.max_wrong_total)), "max_declines": int(tv(idn.decline.max_declines)),
                "purpose_question_counts": bool(tv(idn.decline.purpose_question_counts)), "explain_once_text": tv(idn.decline.explain_once_text),
                "fail_message": tv(idn.fail_message), "fail_outcome": idn.fail_close.outcome, "fail_reason": idn.fail_close.reason,
                "decline_outcome": idn.decline_close.outcome, "decline_reason": idn.decline_close.reason,
                "swapped_hint": tv(idn.swapped.hint_value), "swapped_counts": bool(tv(idn.swapped.counts_as_wrong)),
                "swapped_instruction": tv(idn.swapped.instruction),
            },
            "ga_node": "load_account", "products_field": self.api.product_list_field(), "product_fields": prod_fields,
            "product_labels": {pl.product_type: pl.template for pl in s.debt_statement.product_labels},
            "floor_fields": {ff.product_type: ff.account_field for ff in s.amounts.floor_field_by_type},
            "bands": [{"label": b.label, "days_late_min": b.days_late_min, "days_late_max": b.days_late_max,
                       "deadline_business_days": b.deadline_business_days, "persuasion_attempts": b.persuasion_attempts} for b in s.bands],
            "debt_include": list(tv(s.debt_statement.include)),
            "negotiation": {
                "attempts": [{"n": a.n, "amount": a.amount, "date": a.date, "if_today_is_that_day": a.if_today_is_that_day, "bands_allowed": list(a.bands_allowed)} for a in neg.attempts],
                "vague_ask_once": bool(tv(neg.vague.ask_once)), "no_answer_is_refusal": bool(tv(neg.no_answer_is_refusal)),
                "no_repeat_refused_offer": bool(tv(neg.no_repeat_refused_offer)),
                "refusing_deadline_is_flat_refusal": bool(tv(neg.after_deadline.refusing_deadline_is_flat_refusal)),
                "exhausted_outcome": neg.exhausted_close.outcome, "exhausted_reason": neg.exhausted_close.reason, "exhausted_note_reason": exhausted_note,
            },
            "amounts": {
                "too_much_offer_floor_once": bool(tv(s.amounts.too_much.offer_floor_once)), "too_much_say_rest_overdue": bool(tv(s.amounts.too_much.say_rest_overdue)),
                "below_floor_offer_floor_once": bool(tv(s.amounts.below_floor.offer_floor_once)),
            },
            "intents": [it.model_dump() for it in s.special_intents],
            "recording": {"max_attempts": int(tv(s.recording.max_attempts)), "failure_note_reason": tv(s.recording.failure_note_reason),
                          "failure_outcome": s.recording.failure_close.outcome, "failure_reason": s.recording.failure_close.reason, "failure_say": tv(s.recording.failure_say)},
            "closing": {
                "rows": [{"outcome": o, "reason": r} for o, r in self.rows],
                "promise_key": promise_rows[0] if promise_rows else fallback, "fallback_key": fallback,
                "promise_wins": bool(tv(agg.promise_wins)), "transfer_wins_over_promise": bool(tv(agg.transfer_wins_over_promise)),
                "all_noted_as": [{"note_reason": a.reason, "outcome": a.outcome, "reason": ""} for a in agg.all_noted_as],
                "else_outcome": else_out, "else_skip_reasons": skip,
                "note_reasons": list(tv(s.multi_product.note_reasons)), "note_unpromised": bool(tv(s.multi_product.note_unpromised_products)),
                "failure_note_reason": tv(s.recording.failure_note_reason), "exhausted_note_reason": exhausted_note,
            },
            "date_over_deadline_use_product_deadline": bool(tv(s.multi_product.date_over_deadline_use_product_deadline_and_say_so)),
            "multi": self.multi,
        }

    def _promise_outcome(self) -> str:
        """The outcome row that means 'a promise was recorded': the first row without a reason whose `when` mentions a promise, else the first row."""
        for r in self.spec.closing.outcome_table:
            if not r.reason and "promise" in (r.when or "").lower():
                return r.outcome
        return self.spec.closing.outcome_table[0].outcome if self.spec.closing.outcome_table else ""

    def snippet(self, name: str) -> str:
        return self.const_text + self.prelude + "\n" + self.snips[name]

    # ---- hooks (no CONST: constants injected directly)
    def hook_post_status(self, flag: str, id_fields: List[str], next_ok: str = "", next_fail: str = "") -> str:
        c = inject("H", {"flag": flag, "ids": id_fields, "ok": next_ok, "fail": next_fail})
        return c + """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        ok = isinstance(d, dict) and str(d.get('ok')).lower() == 'true'
        for k in H['ids']:
            if ok and not d.get(k):
                ok = False
        vars[H['flag']] = 'ok' if ok else 'failed'
        if isinstance(d, dict):
            d['what_to_do_next'] = H['ok'] if ok else (H['fail'] or ('Not done: ' + str(d.get('error') or 'unknown error')))
    else:
        vars[H['flag']] = 'failed'
except Exception:
    vars[H['flag']] = 'failed'
"""

    def hook_pre_numeric(self, op: str) -> str:
        nf = numeric_fields(self.api, op)
        if not nf:
            return ""
        return inject("NF", nf) + """try:
    b = config.get('body') if isinstance(config, dict) else None
    if isinstance(b, dict):
        for k in NF:
            if k in b and b[k] not in (None, ''):
                b[k] = float(b[k]) if NF[k] == 'float' else int(float(b[k]))
except Exception:
    pass
"""

    def hook_post_verify(self, i: int) -> str:
        idn = self.spec.identity
        c = inject("H", {"i": i, "max_wrong": int(tv(idn.max_wrong_total)), "swapped_hint": tv(idn.swapped.hint_value),
                         "swapped_counts": bool(tv(idn.swapped.counts_as_wrong)), "swapped_instruction": tv(idn.swapped.instruction),
                         "unreadable_counts": bool(tv(idn.unreadable_counts_as_wrong)) if hasattr(idn, "unreadable_counts_as_wrong") else False,
                         "fail_message": tv(idn.fail_message), "last": i == len(idn.questions) - 1})
        return c + """try:
    flag = 'vq' + str(H['i']) + '_status'
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if not isinstance(d, dict):
            d = dict()
            result['data'] = d
        wrong = int(float(vars.get('id_wrong_total') or 0))
        ok = str(d.get('ok')).lower() == 'true'
        verified = str(d.get('verified')).lower() == 'true'
        vars['id_declines'] = '0'
        hint = str(d.get('hint') or '')
        if not ok:
            if H['unreadable_counts']:
                wrong += 1
            vars[flag] = 'unreadable'
            d['what_to_do_next'] = 'The answer could not be read in the required format. Ask the same question again and convert the answer to the required format before calling the tool.'
        elif verified:
            vars[flag] = 'verified'
            d['what_to_do_next'] = 'Verified.' + (' The identity check is complete.' if H['last'] else ' Ask the next security question.')
        elif hint and hint == H['swapped_hint'] and not H['swapped_counts']:
            vars[flag] = 'swapped'
            d['what_to_do_next'] = H['swapped_instruction'] + ' Then call the tool again with the corrected date. This retry does not count as a wrong answer.'
        else:
            wrong += 1
            left = d.get('wrong_answers_left')
            try:
                if left is not None and int(float(left)) <= 0:
                    wrong = max(wrong, H['max_wrong'])
            except Exception:
                pass
            if wrong >= H['max_wrong']:
                vars[flag] = 'locked'
                d['what_to_do_next'] = 'That was the last allowed attempt. ' + H['fail_message']
            else:
                vars[flag] = 'wrong'
                d['what_to_do_next'] = 'The answer did not match. Say so and ask the same question once more.'
        vars['id_wrong_total'] = str(wrong)
    else:
        vars[flag] = 'unreadable'
except Exception:
    vars['vq' + str(H['i']) + '_status'] = 'unreadable'
"""

    def hook_post_products(self) -> str:
        return inject("H", {"field": self.api.product_list_field()}) + """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            vars['ga_products_json'] = json.dumps(d.get(H['field']) or [])
            vars['ga_status'] = 'ok' if str(d.get('ok')).lower() == 'true' else 'failed'
        else:
            vars['ga_status'] = 'failed'
except Exception:
    vars['ga_status'] = 'failed'
"""

    # ---- extraction schemas
    def date_parts(self, what: str) -> List[dict]:
        return [
            ev("d_ref", ["today", "tomorrow", "day_after_tomorrow", "weekday", "day_of_month", "vague", "none"],
               f"Based only on the customer's latest message, which kind of day they name for {what}: today; tomorrow; day_after_tomorrow; weekday (a named weekday such as Friday, this Friday, next Monday); day_of_month (a calendar date such as the 26th, the 6th of November); vague (a period without an exact day: next week, the week after next, end of the month, when my salary comes, in a few days); none if no day is mentioned."),
            ev("d_weekday", WEEKDAY_NAMES + ["none"], "The weekday the customer names in the latest message, if any; none otherwise."),
            ev("d_week", ["this", "next", "week_after_next", "none"], "this if the customer says 'this <weekday>' or 'this week'; next if 'next <weekday>' or 'next week'; week_after_next if 'the week after next'; none otherwise."),
            {"name": "d_dom", "type": "integer", "description": "The day of the month the customer names in the latest message (the 26th -> 26, 6 November -> 6, 'Monday the 26th' -> 26); 0 if none.", "min_confidence": MIN_CONF},
            ev("d_month", MONTH_NAMES + ["none"], "The month the customer names in the latest message, if any; none otherwise."),
            {"name": "d_year", "type": "integer", "description": "The year the customer names in the latest message; 0 if none.", "min_confidence": MIN_CONF},
        ]

    def amount_part(self) -> dict:
        return {"name": "amount_said", "type": "float", "min_confidence": MIN_CONF,
                "description": "The amount of money the customer says they can or will pay, taken only from the latest message, as a number (words count: 'three hundred' is 300, 'four hundred and twenty' is 420); 0 if the customer names no amount."}

    def intent_values(self, before_identity: bool) -> List[str]:
        return [it.key for it in self.spec.special_intents if (it.allowed_before_identity or not before_identity)]

    def intent_desc(self, keys: List[str]) -> str:
        return " ".join(f"{k}: {self.intents[k].trigger_description}" for k in keys if k in self.intents)

    def pay_schema(self) -> List[dict]:
        keys = self.intent_values(before_identity=False)
        values = ["yes_today", "accepts_offer", "proposes", "too_much", "refuses", "no_answer", "vague"] + keys + ["asks_question", "none"]
        desc = ("What the customer's latest message says about paying, based only on that message. "
                "yes_today: they can pay what was asked today. accepts_offer: they accept the amount and day the agent just proposed. "
                "proposes: they name their own day and/or amount (any named day or amount counts here, never as a refusal). "
                "too_much: the amount is too much for them without naming another amount. "
                "refuses: a plain no or 'I cannot pay' with no day and no amount. no_answer: they avoid the question or change the subject. "
                "vague: a period without an exact day, such as next week, the week after next, end of the month, when the salary comes. "
                + self.intent_desc(keys) + " asks_question: a question to the agent that none of the above covers. none: nothing about paying.")
        pay = ev("pay", values, desc)
        pay["min_confidence"] = 0.4
        ask_keys = [it.key for it in self.spec.special_intents if it.continue_call]
        asks = ev("asks", ask_keys + ["other_question", "none"],
                  "A question the customer asks the agent in the latest message in addition to anything about paying: " + self.intent_desc(ask_keys) + " other_question: any other question to the agent; none: no question.")
        frag = ev("fragment", ["yes", "no"], "yes if the customer's latest message is cut off or unfinished (it stops mid-sentence or mid-word, or only starts a thought without reaching the point); no otherwise.")
        return [pay, asks, frag] + self.date_parts("the payment") + [self.amount_part()] + self.scope_parts()

    def scope_parts(self) -> List[dict]:
        if not self.multi:
            return []
        return [ev("applies_to", ["all", "current", "none"], "Based only on the latest message: all if the customer speaks about all products together (everything, all of them, both); current if about one product only; none if unclear."),
                {"name": "product_hint", "type": "string", "min_confidence": MIN_CONF, "description": "The product the customer refers to in the latest message, in their own words (for example the card, the car loan); empty if none or if they mean all products."}]

    # ---- prompts
    def system_prompt(self) -> str:
        s = self.spec
        glob = [b.agent_instruction for b in s.behaviour_rules if b.stage == "global"]
        cont = [f"If {it.trigger_description[0].lower() + it.trigger_description[1:]} {it.say_text}".replace("..", ".") for it in s.special_intents if it.continue_call and it.say_text]
        lines = [
            f"You are {tv(s.agent_self_description)}, on an outbound phone call. Speak {lang_name(tv(s.language))}.",
            "Keep every turn to one or two short sentences. Ask one question at a time. Be polite and plain.",
            "Facts, amounts and dates you may state come only from the current task text and from tool results. Never invent figures, dates or reasons.",
            "Never say that anything was recorded, scheduled, booked or done unless a tool result in this conversation says it succeeded. If a tool result says it failed, say so honestly.",
            "The 'what_to_do_next' field of a tool result tells you what to say or do next; follow it.",
            "When the task text contains a sentence in quotes marked as exact, say it word for word.",
            "After every tool result, speak to the customer or call the next tool. Never end a turn with nothing.",
            "Do not describe steps, nodes or internal state. Do not narrate what you are about to do.",
        ]
        lines += glob + cont
        return "\n".join("- " + x for x in lines)

    def stage_rules(self, stage: str) -> str:
        rs = [b.agent_instruction for b in self.spec.behaviour_rules if b.stage == stage]
        ph = [f"Say exactly: \"{p.text}\" ({p.when})." for p in self.spec.required_phrases if p.stage == stage and "{" not in p.text]
        return "\n".join("- " + x for x in rs + ph)

    # ---- nodes
    def build(self) -> dict:
        s = self.spec
        nodes: Dict[str, dict] = {}
        addr = tv(s.roles.address_form).replace("{", "{{").replace("}", "}}")
        confirm_q = tv(s.opening.confirm_question).replace("{", "{{").replace("}", "}}")
        first = tv(s.opening.first_sentence)
        first_is_instr = is_instruction(first) or not first.strip()
        if first_is_instr:
            first_rule = (first.strip() or "Say the opening sentence") + f" (it must contain: {', '.join(tv(s.opening.required_elements))})"
        else:
            first_rule = f"say exactly: \"{first}\""

        # 1 opening
        opening_task = (
            f"You have just started the call. If you have not yet said the opening sentence, {first_rule} and then ask exactly: \"{confirm_q}\".\n"
            f"{{{{opening_hint}}}}\n"
            f"Only these count as confirmation: {', '.join(tv(s.opening.accept_examples))}. These do not: {', '.join(tv(s.opening.nonconfirm_examples))}.\n"
            f"Before identity is verified never mention: {', '.join(tv(s.opening.forbidden_before_identity))}. If asked why you call, say you can explain once you have confirmed who you are speaking with.\n"
            "No tool call is allowed in this step."
        )
        who_keys = self.intent_values(before_identity=True)
        who_vals = ["confirms", "third_party", "wrong_number", "deceased", "asks_question"] + who_keys + ["unclear", "none"]
        who_desc = ("Based only on the customer's latest message: confirms: the person confirms they are the customer (yes, that's me, speaking, or says the customer's own name). "
                    "third_party: someone else answered (a relative, partner, colleague) and the customer is not on the line. wrong_number: the number does not belong to the customer. "
                    "deceased: the customer has died. asks_question: a question to the agent (who is this, is this a robot, is this a scam, what is this about). "
                    + self.intent_desc(who_keys) + " unclear: hello, go ahead or anything that does not confirm. none: nothing relevant.")
        nodes["opening"] = conv_node("opening", opening_task, [always("route_opening")],
                                     extraction=[ev("who", who_vals, who_desc)],
                                     on_enter=({"type": "llm"} if first_is_instr else {"type": "tts", "text": f"{first} {confirm_q}"}), first_only=True)
        nodes["route_opening"] = code_node("route_opening", self.snippet("route_opening"), "opening",
                                           [eq("identity_start", "opening_next", "identity_start"), eq("third_party", "opening_next", "third_party"),
                                            eq("wrap_up", "opening_next", "wrap_up"), eq("offer", "opening_next", "offer"), eq("resume_router", "opening_next", "resume_router")])

        # 2 third party
        tp = s.third_party
        tp_rules = self.stage_rules("third_party")
        tp_task = (f"Someone other than the customer is on the line. {tv(tp.deceased_sentence) and ''}"
                   f"Do not say why you are calling and give no account information. Ask when the customer, {addr}, can be reached (day and time).\n"
                   f"{{{{tp_hint}}}}\n{tp_rules}\nNo tool call is allowed in this step.")
        tp_keys = self.intent_values(before_identity=True)
        tp_vals = ["gives_time", "wrong_number", "deceased", "refuses"] + tp_keys + ["none"]
        nodes["third_party"] = conv_node("third_party", tp_task, [always("callback_check")],
                                         extraction=[ev("tp_intent", tp_vals, "Based only on the latest message: gives_time: the person names a day and/or a time when the customer can be reached; wrong_number: this number does not belong to the customer; deceased: the customer has died; refuses: they will not say when the customer can be reached; "
                                                        + self.intent_desc(tp_keys) + " none: nothing of these.")]
                                         + self.date_parts("the callback") +
                                         [{"name": "cb_time", "type": "string", "min_confidence": MIN_CONF, "validation_pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9]$", "max_retries": 1,
                                           "description": "The time of day the person names in the latest message, as HH:MM in 24-hour form ('around eleven in the morning' -> 11:00, 'half past two in the afternoon' -> 14:30, 'at 6 pm' -> 18:00); leave empty if no time is named."}])
        nodes["callback_check"] = code_node("callback_check", self.snippet("callback_check"), "third_party",
                                            [eq("do_callback", "tp_next", "do_callback"), eq("wrap_up", "tp_next", "wrap_up"), eq("offer", "tp_next", "offer"), eq("resume_router", "tp_next", "resume_router")])
        cb_op = self._op_with_fields(["date", "time"]) or "schedule_callback"
        cb_fields = self.api.op(cb_op).fields
        baked = {self.cid: "{{" + self.cid + "}}"}
        for f in cb_fields:
            if f == self.cid:
                continue
            if "date" in f:
                baked[f] = "{{cb_date}}"
            elif "time" in f:
                baked[f] = "{{cb_time}}"
        nodes["do_callback"] = api_node("do_callback", api_tool(self.api, cb_op, baked, pre=self.hook_pre_numeric(cb_op), post=self.hook_post_status("cb_status", self.api.op(cb_op).id_fields, "Callback scheduled.")),
                                        "callback_result", [])
        nodes["callback_result"] = code_node("callback_result", self.snippet("callback_result"), "wrap_up", [])

        # 3 identity
        idn = s.identity
        vq = self._op_with_fields(["field", "answer"]) or "verify_identity"
        field_name = "field"
        answer_name = "answer"
        for f, sch in self.api.op(vq).fields.items():
            if sch.get("enum") and f != self.cid:
                field_name = f
            elif f != self.cid and not sch.get("enum"):
                answer_name = f
        nodes["identity_start"] = code_node("identity_start", self.const_text + self.prelude + "\ntry:\n    vars['id_wrong_total'] = '0'\n    vars['id_declines'] = '0'\n    vars['id_reply'] = 'none'\n    vars['id_hint'] = ''\n    vars['id_node'] = 'identity_q0'\n    vars['stage'] = 'identity'\nexcept Exception:\n    pass\n", "identity_q0", [])
        id_rules = self.stage_rules("identity")
        for i, q in enumerate(idn.questions):
            nxt = f"identity_q{i + 1}" if i + 1 < len(idn.questions) else "load_account"
            task = (f"Security question {i + 1} of {len(idn.questions)}. {q.ask_text} Ask one question at a time.\n{{{{id_hint}}}}\n"
                    f"When the customer answers, convert the answer to this format: {q.answer_format}" + (f" (a date given only as numbers is read as {q.numeric_date_order.replace('_', ', ')})" if q.numeric_date_order else "") +
                    f", then CALL {vq} with it. Do not state any account details. If asked why you need this, say the questions protect the account.\n"
                    "If the customer gives the answer in parts over several turns, combine the parts into one answer and call the tool as soon as the answer is complete; do not ask for parts you already have. "
                    "Only the tool decides whether an answer is right: never say an answer is wrong, never say the check has failed and never send the customer elsewhere unless what_to_do_next says so.\n"
                    f"{id_rules}\nAfter the tool result, do exactly what its what_to_do_next says.")
            tool = api_tool(self.api, vq, {self.cid: "{{" + self.cid + "}}", field_name: q.api_field},
                            description=f"Check the customer's answer to security question {i + 1} ({q.api_field}). CALL it every time the customer gives an answer to this question, with the answer converted to: {q.answer_format}.",
                            post=self.hook_post_verify(i), model_descriptions={answer_name: f"The customer's answer converted to: {q.answer_format}."})
            flag = f"vq{i}_status"
            id_keys = self.intent_values(before_identity=True)
            trans = [eq("id_locked", flag, "locked"), eq(nxt, flag, "verified"),
                     anyof("id_router", "id_reply", ["declines", "asks_purpose", "asks_why"] + id_keys, "the customer did not answer the question")]
            ex = [ev("id_reply", ["declines", "asks_purpose", "asks_why"] + id_keys + ["none"],
                     "Based only on the customer's latest message: declines: they refuse to answer the security question; asks_purpose: they ask what the call or the account is about instead of answering; asks_why: they ask why the agent needs this answer or what it is for, without refusing; "
                     + self.intent_desc(id_keys) + " none: they answered the question, asked how to answer, or said something else.")]
            n = conv_node(f"identity_q{i}", task, trans, extraction=ex, tools=[tool])
            nodes[f"identity_q{i}"] = n
        # set id_node when entering each question: done through small code nodes is heavy; instead the router reads id_node set by id_router targets
        nodes["id_router"] = code_node("id_router", self.snippet("id_router"), "identity_q0",
                                       [eq(f"identity_q{i}", "id_next", f"identity_q{i}") for i in range(len(idn.questions))]
                                       + [eq("wrap_up", "id_next", "wrap_up"), eq("offer", "id_next", "offer"), eq("resume_router", "id_next", "resume_router")])
        nodes["id_locked"] = code_node("id_locked", self.snippet("id_locked"), "wrap_up", [])
        # keep id_node current: each identity node's entry is preceded by a tiny code node for i>0
        for i in range(1, len(idn.questions)):
            nodes[f"identity_q{i}_enter"] = code_node(f"identity_q{i}_enter", self.const_text + self.prelude + f"\ntry:\n    vars['id_node'] = 'identity_q{i}'\n    vars['id_hint'] = ''\n    vars['id_reply'] = 'none'\nexcept Exception:\n    pass\n", f"identity_q{i}", [])
            # re-point transitions that go to identity_q{i} from the previous question to the enter node
            prev = nodes[f"identity_q{i - 1}"]
            for t in prev["transitions"]:
                if t["target_node"] == f"identity_q{i}":
                    t["target_node"] = f"identity_q{i}_enter"

        # 4 account
        ga = self._op_with_fields([]) or "get_account"
        nodes["load_account"] = api_node("load_account", api_tool(self.api, ga, {self.cid: "{{" + self.cid + "}}"}, post=self.hook_post_products(), retries=1), "account_facts", [])
        nodes["account_facts"] = code_node("account_facts", self.snippet("account_facts"), "state_debt", [])

        # 5 negotiation
        neg = s.negotiation
        nego_rules = "\n".join("- " + b.agent_instruction for b in s.behaviour_rules if b.stage == "negotiation")
        debt_task = (f"The customer is verified. {tv(s.debt_statement.intro_instruction)} State each late product with its figures, one sentence per product, from this list and nothing else:\n{{{{debt_text}}}}\n"
                     f"Then ask exactly: \"{tv(neg.first_question)}\"" + (" (about all products together)" if self.multi else "") + ".\n"
                     "Do not ask how much the customer can pay. No tool call is allowed in this step.")
        intro = tv(getattr(s.debt_statement, "intro_sentence", "")) or ""
        if intro.strip() and not is_instruction(intro) and not is_instruction(tv(neg.first_question)):
            debt_enter = {"type": "tts", "text": f"{intro} {{{{debt_text}}}} {tv(neg.first_question)}"}
        else:
            debt_enter = {"type": "llm"}
        nodes["state_debt"] = conv_node("state_debt", debt_task, [always("negotiation_router")], extraction=self.pay_schema(), on_enter=debt_enter, first_only=True)
        nego_task = ("You are agreeing a payment promise for: {{cur_label}}.\n{{date_facts}}\n"
                     "Instruction for this turn: {{nego_hint}}\n"
                     "Say only what the instruction asks, in one or two sentences, then wait for the answer. Never ask how much the customer can pay; you propose every amount. "
                     f"Never offer {', '.join(tv(neg.forbidden_offers))}. Do not add offers, dates or amounts of your own: the instruction already applies the policy below.\n"
                     f"Background policy:\n{nego_rules}\nNo tool call is allowed in this step.")
        nodes["negotiate"] = conv_node("negotiate", "You have just made the proposal shown above. Wait for the customer's answer. No tool call is allowed in this step.",
                                       [always("negotiation_router")], extraction=self.pay_schema(), on_enter={"type": "tts", "text": "{{nego_say}}"})
        nodes["negotiate_llm"] = conv_node("negotiate_llm", nego_task, [always("negotiation_router")], extraction=self.pay_schema())
        nodes["negotiation_router"] = code_node("negotiation_router", self.snippet("negotiation_router"), "negotiate_llm",
                                                [eq("negotiate", "nego_next", "negotiate"), eq("readback", "nego_next", "readback"), eq("offer", "nego_next", "offer"), eq("wrap_up", "nego_next", "wrap_up"),
                                                 eq("resume_router", "nego_next", "resume_router"), eq("product_done", "nego_next", "product_done")])
        nodes["product_done"] = code_node("product_done", self.snippet("product_done"), "wrap_up", [eq("negotiation_router", "pd_next", "negotiation_router"), eq("readback", "pd_next", "readback")])

        # 6 read-back
        conf = s.confirmation
        rb_task = ("Read the agreed promise back exactly from this list, naming the product, the amount and the day: {{readback_text}}. "
                   f"Then ask exactly: \"{tv(conf.confirm_question)}\"\n{{{{rb_hint}}}}\n{self.stage_rules('confirmation')}\nNo tool call is allowed in this step.")
        rb_tts = {"type": "llm"} if is_instruction(tv(conf.confirm_question)) else {"type": "tts", "text": "To confirm: {{readback_text}}. " + tv(conf.confirm_question)}
        rb_keys = self.intent_values(before_identity=False)
        rb_vals = ["confirms", "changes", "refuses"] + rb_keys + ["asks_question", "none"]
        nodes["readback"] = conv_node("readback", rb_task, [always("readback_router")],
                                      on_enter=rb_tts, first_only=True,
                                      extraction=[ev("rb", rb_vals, "Based only on the customer's latest message: confirms: an explicit yes, correct, that's right or I confirm, and nothing else is changed; changes: they name another day or amount, or give a fragment of a date (set the other fields); refuses: they no longer want to promise; "
                                                     + self.intent_desc(rb_keys) + " asks_question: a question; none: unclear.")] + self.date_parts("the payment") + [self.amount_part()] + self.scope_parts())
        nodes["readback_llm"] = conv_node("readback_llm", "{{rb_hint}}\nThen, in the same turn, read the promise back exactly like this and ask the question word for word: \"To confirm: {{readback_text}}. " + tv(conf.confirm_question) + "\"\nNo tool call is allowed in this step.",
                                          [always("readback_router")], extraction=nodes["readback"]["extraction_schema"])
        nodes["negotiation_router"]["transitions"].insert(0, eq("readback_llm", "nego_next", "readback_llm"))
        nodes["readback_router"] = code_node("readback_router", self.snippet("readback_router"), "readback",
                                             [eq("promise_guard", "rb_next", "promise_guard"), eq("negotiation_router", "rb_next", "negotiation_router")])

        # 7 write loop (G2)
        cp = self._op_with_fields(["amount", "date"]) or "create_promise"
        cp_fields = self.api.op(cp).fields
        baked = {self.cid: "{{" + self.cid + "}}"}
        for f in cp_fields:
            if f == self.cid:
                continue
            if "product" in f:
                baked[f] = "{{p_product}}"
            elif "amount" in f:
                baked[f] = "{{p_amount}}"
            elif "date" in f:
                baked[f] = "{{p_date}}"
        nodes["promise_guard"] = code_node("promise_guard", self.snippet("promise_guard"), "wrap_up", [eq("do_promise", "pg_next", "do_promise"), eq("negotiation_router", "pg_next", "negotiation_router")])
        nodes["do_promise"] = api_node("do_promise", api_tool(self.api, cp, baked, pre=self.hook_pre_numeric(cp), post=self.hook_post_status("pr_status", self.api.op(cp).id_fields, "Promise recorded.")), "promise_result", [])
        nodes["promise_result"] = code_node("promise_result", self.snippet("promise_result"), "wrap_up",
                                            [eq("do_promise", "prs_next", "do_promise"), eq("promise_guard", "prs_next", "promise_guard"), eq("say_recorded", "prs_next", "say_recorded")])
        rec = s.recording
        recorded_tts = f"Thank you. Your promise is recorded. {tv(rec.success_sentence)} {tv(s.closing.goodbye_instruction) if hasattr(s.closing, 'goodbye_instruction') else ''}".strip()
        succ = tv(rec.success_sentence)
        if is_instruction(succ):
            rec_enter = {"type": "llm"}
            rec_task = (f"The promise has just been recorded successfully (the tool returned ok). Say that it is recorded. {succ} Then thank the customer for their time and say goodbye in one short sentence. "
                        "If the customer later asks to change the recorded promise: " + tv(conf.change_after_record_text) + " No tool call is allowed.")
        else:
            rec_enter = {"type": "tts", "text": f"Thank you, your promise is recorded. {succ} Thank you for your time and goodbye."}
            rec_task = "The promise was recorded and you have said goodbye. If the customer asks to change the recorded promise: " + tv(conf.change_after_record_text) + " Otherwise say goodbye again in a few words. No tool call is allowed."
        nodes["say_recorded"] = conv_node("say_recorded", rec_task, [always("after_recorded")], on_enter=rec_enter, first_only=True)
        nodes["after_recorded"] = code_node("after_recorded", self.const_text + self.prelude + "\ntry:\n    vars['goodbye_done'] = 'yes'\nexcept Exception:\n    pass\n", "wrap_up", [])

        # 8 offers (ask_once_first intents)
        offer_task = ("{{offer_say}} {{offer_ask}} {{offer_hint}}\nWait for a yes or a no. Make no persuasion attempt and offer nothing else. No tool call is allowed in this step.")
        nodes["offer"] = conv_node("offer", offer_task, [always("offer_router")],
                                   extraction=[ev("offer_reply", ["accepts", "declines", "none"], "Based only on the customer's latest message: accepts: they say yes to what the agent just offered or asked, or insist on their request; declines: they say no, or let the agent carry on instead; none: unclear.")])
        nodes["offer_router"] = code_node("offer_router", self.snippet("offer_router"), "offer", [eq("wrap_up", "offer_next", "wrap_up"), eq("resume_router", "offer_next", "resume_router")])

        # 9 resume
        resumable = ["opening", "third_party", "negotiate_llm", "readback", "offer"] + [f"identity_q{i}" for i in range(len(idn.questions))]
        nodes["resume_router"] = code_node("resume_router", self.snippet("resume_router"), "negotiate_llm", [eq(n, "resume_next", n) for n in resumable if n != "negotiate_llm"])

        # 10 closing
        nodes["wrap_up"] = code_node("wrap_up", self.snippet("wrap_up"), "goodbye", [eq("pre_close", "wrap_next", "pre_close"), eq("do_note", "wrap_next", "do_note"), eq("goodbye_tts", "wrap_next", "goodbye_tts")])
        an = self._op_with_fields(["reason"]) or "add_note"
        nf = self.api.op(an).fields
        baked = {self.cid: "{{" + self.cid + "}}"}
        omit = []
        for f in nf:
            if f == self.cid:
                continue
            if "product" in f:
                baked[f] = "{{note_product}}"
            elif "reason" in f:
                baked[f] = "{{note_reason}}"
            else:
                omit.append(f)
        nodes["do_note"] = api_node("do_note", api_tool(self.api, an, baked, omit=omit, post=self.hook_post_status("note_status", [], "Noted.")), "wrap_up", [])
        goodbye_task = ("This is the last thing you say in this call. {{goodbye_prefix}}\nThen, in the same turn, thank the customer for their time and say goodbye in one short sentence. "
                        "Ask no question of any kind, propose nothing, mention no amount, date or payment, and do not call any tool.")
        nodes["goodbye"] = conv_node("goodbye", goodbye_task, [always("pre_close")])
        nodes["goodbye_tts"] = conv_node("goodbye_tts", "You have said goodbye. If the customer says anything, say goodbye again in a few words. No tool call is allowed.",
                                         [always("pre_close")], on_enter={"type": "tts", "text": "{{goodbye_say}} Thank you for your time and goodbye."}, first_only=True)
        nodes["pre_close"] = code_node("pre_close", self.snippet("pre_close"), "close_router", [eq("do_transfer", "pc_next", "do_transfer")])
        tr = self._op_with_fields(["queue"]) or "transfer_to_agent"
        qf = next((f for f, sch in self.api.op(tr).fields.items() if sch.get("enum") and f != self.cid), "queue")
        nodes["do_transfer"] = api_node("do_transfer", api_tool(self.api, tr, {self.cid: "{{" + self.cid + "}}", qf: "{{transfer_queue}}"}, post=self.hook_post_status("tr_status", [], "Transferred.")), "close_router", [])
        cc = self._op_with_fields(["outcome"]) or "close_call"
        of = next((f for f, sch in self.api.op(cc).fields.items() if sch.get("enum") and f != self.cid), "outcome")
        rf = next((f for f in self.api.op(cc).fields if f not in (self.cid, of)), "reason")
        nodes["close_router"] = code_node("close_router", self.const_text + self.prelude + "\ntry:\n    vars['close_key'] = _s(vars.get('close_key')) or _s(CONST['closing']['fallback_key'])\nexcept Exception:\n    pass\n",
                                          "close_" + self.const["closing"]["fallback_key"], [eq("close_" + k, "close_key", k) for k in self.row_keys])
        for (o, r), k in zip(self.rows, self.row_keys):
            baked = {self.cid: "{{" + self.cid + "}}", of: o}
            omit = []
            if r:
                baked[rf] = r
            else:
                omit = [rf]
            nodes["close_" + k] = api_node("close_" + k, api_tool(self.api, cc, baked, omit=omit, post=self.hook_post_status("close_status", [], "Closed.")), "end_" + k, [])
            nodes["end_" + k] = end_node("end_" + k, k)

        wf = {
            "initial_node": "opening",
            "system_prompt": self.system_prompt(),
            "test_variables": {},
            "global_nodes": {},
            "nodes": nodes,
        }
        return wf

    def _op_with_fields(self, fields: List[str]) -> str:
        """Operation whose body has all the given fields besides the customer id (empty list → the op with only the customer id)."""
        for name, op in self.api.ops.items():
            others = [f for f in op.fields if f != self.cid]
            if not fields and not others:
                return name
            if fields and all(any(f in o for o in others) for f in fields):
                return name
        return ""


def generate(spec: Spec, api: Api) -> dict:
    return Generator(spec, api).build()
