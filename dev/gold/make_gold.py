"""Gold specs for Brief A and A+B, hand-written from the briefs (dev material; never read by the builder).

    python dev/gold/make_gold.py        # writes dev/gold/brief-a.spec.json and dev/gold/brief-ab.spec.json

Fact ids: A-R<n> = Brief A rule n, A-S<n> = Brief A section n (text outside a numbered rule), B-<n> = Brief B item n, B-C = Brief B closing.
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from builder.schema import Spec


def S(v, *f): return {"value": v, "fact_ids": list(f)}
def I(v, *f): return {"value": v, "fact_ids": list(f)}
def B(v, *f): return {"value": v, "fact_ids": list(f)}
def L(v, *f): return {"values": list(v), "fact_ids": list(f)}
def C(o, r, *f): return {"outcome": o, "reason": r, "fact_ids": list(f)}


def intent(key, trigger, *, before=False, say="", verbatim=False, ask_once=False, action="none", queue="", note="",
           close=("", ""), before_close=("", ""), decline_close=("", ""), count=1, cont=False, cont_products=False, prec=50,
           suppress=False, named_terms=False, applies="all", facts=()):
    return {"key": key, "trigger_description": trigger, "allowed_before_identity": before, "applies_to": applies,
            "say_text": say, "say_is_verbatim": verbatim, "ask_once_first": ask_once, "action_kind": action,
            "action_queue": queue, "action_note_reason": note, "close_outcome": close[0], "close_reason": close[1],
            "before_identity_close_outcome": before_close[0], "before_identity_close_reason": before_close[1],
            "declined_close_outcome": decline_close[0], "declined_close_reason": decline_close[1], "count_before_action": count,
            "continue_call": cont, "continue_other_products": cont_products, "precedence": prec,
            "suppresses_persuasion": suppress, "customer_named_terms_still_recorded": named_terms, "fact_ids": list(facts)}


def gold_a():
    return {
        "bank_name": S("Freya Bank", "A-S0"),
        "language": S("English", "A-S0"),
        "agent_self_description": S("Freya Bank's digital assistant", "A-R1", "A-R4"),
        "call_variables": [
            {"name": "customer_id", "meaning": "Pass it to every tool call.", "fact_ids": ["A-S2"]},
            {"name": "first_name", "meaning": "The person to ask for.", "fact_ids": ["A-S2"]},
            {"name": "last_name", "meaning": "The person to ask for.", "fact_ids": ["A-S2"]},
            {"name": "title", "meaning": "Mr or Ms. Address the customer as title plus last name.", "fact_ids": ["A-S2"]},
            {"name": "now", "meaning": "The current date and time. All date rules use this, never the real clock.", "fact_ids": ["A-S2"]},
        ],
        "roles": {"customer_id_var": S("customer_id", "A-S2"), "now_var": S("now", "A-S2"), "address_form": S("{title} {last_name}", "A-S2")},
        "opening": {
            "required_elements": L(["you are a digital assistant calling from Freya Bank", "the call is recorded"], "A-R1"),
            "forbidden_before_identity": L(["collections", "debt", "payment", "the product"], "A-R1"),
            "confirm_question": S("Am I speaking with {title} {last_name}?", "A-R2"),
            "accept_examples": L(["yes", "that's me", "speaking", "the customer's own name"], "A-R3"),
            "nonconfirm_examples": L(["hello", "go ahead", "who is this"], "A-R3"),
            "max_confirm_asks": I(2, "A-R3"),
            "answer_question_then_count_as_ask": B(True, "A-R3"),
            "unclear_close": C("not_reached", "unclear", "A-R3"),
            "robot_question_reply": S("Say that you are Freya Bank's digital assistant and continue.", "A-R4"),
        },
        "third_party": {
            "say_only_opening": B(True, "A-R5"),
            "ask_when_reachable": B(True, "A-R5"),
            "callback": {"allowed_days": L(["today", "next_business_day"], "A-R6"), "from_time": S("10:00", "A-R6"), "to_time": S("19:00", "A-R6"),
                         "inclusive": B(True, "A-R6"), "after_now": B(True, "A-R6"), "ask_again_times": I(1, "A-R7")},
            "callback_close": C("not_reached", "callback", "A-R6"),
            "no_callback_close": C("not_reached", "no_callback", "A-R7"),
            "wrong_number_close": C("not_reached", "wrong_number", "A-R8"),
            "deceased_close": C("not_reached", "deceased", "A-R9"),
            "deceased_sentence": S("I am sorry for your loss.", "A-R9"),
            "deceased_ask_nothing_else": B(True, "A-R9"),
            "relative_cannot_verify": B(True, "A-R10"),
        },
        "identity": {
            "questions": [
                {"api_field": "date_of_birth", "ask_text": "Ask for the date of birth.", "answer_format": "YYYY-MM-DD", "numeric_date_order": "day_month_year", "fact_ids": ["A-R11"]},
                {"api_field": "phone_last4", "ask_text": "Ask for the last four digits of the phone number on file.", "answer_format": "four digits", "numeric_date_order": "", "fact_ids": ["A-R11"]},
            ],
            "one_at_a_time": B(True, "A-R11"),
            "max_wrong_total": I(3, "A-R12"),
            "wrong_may_retry": B(True, "A-R12"),
            "swapped": {"hint_value": S("day_month_swapped", "A-R13"), "instruction": S("Ask the customer to say the month as a word.", "A-R13"), "counts_as_wrong": B(False, "A-R13")},
            "decline": {"explain_once_text": S("Explain once that the questions protect their account.", "A-R15"), "max_declines": I(2, "A-R15"), "purpose_question_counts": B(True, "A-R15")},
            "fail_message": S("Tell the customer to use the mobile app or a branch.", "A-R14"),
            "fail_close": C("not_verified", "failed", "A-R14"),
            "decline_close": C("not_verified", "declined", "A-R15"),
            "do_not_state_debt_on_fail": B(True, "A-R14"),
        },
        "calendar": {
            "business_weekdays": L(["monday", "tuesday", "wednesday", "thursday", "friday"], "A-S7"),
            "holidays": L(["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"], "A-S7"),
            "deadline_rule": {"kind": S("nth_business_day_after_today", "A-R18"), "n_from_band": B(True, "A-R18")},
            "next_weekday": S("following_calendar_week", "A-R22"),
            "this_weekday": S("current_week", "A-R22"),
            "numeric_date_order": S("day_month_year", "A-R11"),
            "date_source": S("now", "A-S2"),
        },
        "bands": [
            {"label": "early", "days_late_min": 1, "days_late_max": 7, "deadline_business_days": 12, "persuasion_attempts": 1, "fact_ids": ["A-R18"]},
            {"label": "late", "days_late_min": 8, "days_late_max": 45, "deadline_business_days": 7, "persuasion_attempts": 2, "fact_ids": ["A-R18"]},
        ],
        "debt_statement": {
            "intro_instruction": S("Say that you are calling from the collections team about a late payment.", "A-R17"),
            "product_labels": [
                {"product_type": "credit_card", "template": "credit card ending {card_last4}", "fact_ids": ["A-R17"]},
                {"product_type": "personal_loan", "template": "personal loan", "fact_ids": ["A-R17"]},
                {"product_type": "car_loan", "template": "car loan", "fact_ids": ["A-R17"]},
            ],
            "include": L(["past_due", "days_late"], "A-R17"),
            "account_tool_after_identity": B(True, "A-R16"),
        },
        "amounts": {
            "floor_field_by_type": [
                {"product_type": "credit_card", "account_field": "minimum_payment", "fact_ids": ["A-R25"]},
                {"product_type": "personal_loan", "account_field": "instalment_amount", "fact_ids": ["A-R25"]},
                {"product_type": "car_loan", "account_field": "instalment_amount", "fact_ids": ["A-R25"]},
            ],
            "ask_full_first": B(True, "A-R24"),
            "never_ask_how_much": B(True, "A-R24"),
            "agent_proposes_every_amount": B(True, "A-R24"),
            "accept_range": {"min": S("floor", "A-R27"), "max": S("full", "A-R27"), "inclusive": B(True, "A-R27")},
            "too_much": {"offer_floor_once": B(True, "A-R26"), "say_rest_overdue": B(True, "A-R26")},
            "below_floor": {"say_cannot_record": B(True, "A-R27"), "offer_floor_once": B(True, "A-R27")},
            "refuse_floor_is_flat_refusal": B(True, "A-R26", "A-R27"),
        },
        "negotiation": {
            "first_question": S("Can you make this payment today?", "A-R28"),
            "promise_date": {"not_before": S("today", "A-R19"), "business_day_only": B(True, "A-R19"), "not_after": S("deadline", "A-R19")},
            "attempts": [
                {"n": 1, "amount": "floor_if_full_refused", "date": "last_business_day_this_week", "if_today_is_that_day": "last_business_day_next_week", "bands_allowed": [], "fact_ids": ["A-R30"]},
                {"n": 2, "amount": "floor", "date": "deadline", "if_today_is_that_day": "", "bands_allowed": ["late"], "fact_ids": ["A-R30"]},
            ],
            "proposal_is_not_refusal": B(True, "A-R29"),
            "no_to_today_without_terms_is_refusal": B(True, "A-R30"),
            "vague": {"ask_once": B(True, "A-R21"), "then": S("propose_deadline", "A-R21")},
            "nonbusiness_date": {"offer_next_business_day": B(True, "A-R20")},
            "after_deadline": {"offer_deadline": B(True, "A-R23"), "refusing_deadline_is_flat_refusal": B(True, "A-R23")},
            "no_answer_is_refusal": B(True, "A-R30"),
            "no_repeat_refused_offer": B(True, "A-R31"),
            "exhausted_close": C("no_promise", "refused", "A-R31"),
            "forbidden_offers": L(["a discount", "a waiver", "an instalment plan", "any term that is not in the brief"], "A-R33"),
        },
        "special_intents": [
            intent("hardship", "The customer mentions illness, a death in the family or job loss.",
                   say="Say one short sentence of sympathy and make no persuasion attempt.", ask_once=True,
                   action="transfer", queue="support", close=("transferred", "support"), decline_close=("no_promise", "hardship"),
                   prec=10, suppress=True, named_terms=True, facts=("A-R32",)),
            intent("already_paid", "The customer says they already paid this past-due amount.",
                   say="Say that payments can take one business day to appear. Take no promise.",
                   close=("paid", ""), prec=20, suppress=True, facts=("A-R39",)),
            intent("dispute", "The customer says the debt is not theirs, they never had this product, or it was closed or paid off in the past.",
                   say="Do not argue and do not take a promise.", close=("no_promise", "dispute"), prec=20, suppress=True, facts=("A-R40",)),
            intent("wants_plan", "The customer asks for a new payment plan or lower instalments.",
                   say="Do not describe a plan.", action="transfer", queue="restructuring", close=("transferred", "restructuring"),
                   prec=30, suppress=True, facts=("A-R41",)),
            intent("wants_human", "The customer asks to speak to a human or a real person.", before=True,
                   say="Ask once whether you can help first.", ask_once=True, action="transfer", queue="general",
                   close=("transferred", "human"), before_close=("transferred", "human"), decline_close=("", ""),
                   prec=40, facts=("A-R42", "A-R45")),
            intent("not_talk", "The customer says they do not want to talk (the second time closes the call).", before=True,
                   close=("no_promise", "refused"), before_close=("not_verified", "declined"), count=2, prec=50, facts=("A-R45",)),
            intent("robot_question", "The customer asks whether they are talking to a robot or an AI.", before=True,
                   say="Say that you are Freya Bank's digital assistant and continue.", cont=True, prec=90, facts=("A-R4",)),
            intent("scam_question", "The customer asks whether this is a scam.", before=True,
                   say="Say they can verify the call by phoning Freya Bank's customer service number, and continue.", cont=True, prec=90, facts=("A-R43",)),
        ],
        "confirmation": {
            "readback_elements": L(["product", "amount", "date"], "A-R34"),
            "confirm_question": S("Do you confirm?", "A-R34"),
            "record_only_after_clear_yes": B(True, "A-R34"),
            "recheck_on_change": B(True, "A-R35"),
            "one_promise_per_product": B(True, "A-R36"),
            "change_after_record_text": S("A recorded promise cannot be changed or cancelled in this call; say they can change it in the mobile app.", "A-R36"),
        },
        "recording": {
            "max_attempts": I(2, "A-R37"),
            "say_recorded_only_on_ok": B(True, "A-R37"),
            "success_sentence": S("You will receive a text message confirming this promise.", "A-R38"),
            "failure_say": S("Say that you could not record the promise.", "A-R37"),
            "failure_close": C("no_promise", "service_error", "A-R37"),
            "failure_note_reason": S("", "A-R46"),
        },
        "multi_product": {
            "enabled": B(False, "A-S1"), "max_products": I(1, "A-S1"), "state_all_first": B(False, "A-S1"), "per_product_deadline": B(False, "A-S1"), "ask_all_today_first": B(False, "A-S1"), "ask_today_once": B(False, "A-S1"),
            "per_product_attempts": B(False, "A-S1"), "attempts_restart_per_product": B(False, "A-S1"), "single_combined_readback": B(False, "A-S1"),
            "order": S("as_returned", "A-S1"), "date_over_deadline_use_product_deadline_and_say_so": B(False, "A-S1"),
            "note_unpromised_products": B(False, "A-R46"), "note_even_when_no_promise": B(False, "A-R46"), "note_reasons": L([], "A-R46"), "notes_on_transfer": B(False, "A-R46"),
            "unrecorded_on_transfer_are_dropped": B(True, "A-R46"), "recorded_before_transfer_stay": B(True, "A-R46"),
            "single_product_dispute_or_paid_continues": B(False, "A-R39", "A-R40"),
        },
        "closing": {
            "goodbye_before_close": B(True, "A-R47"),
            "exactly_one_close": B(True, "A-R46"),
            "close_is_last_tool_call": B(True, "A-R46"),
            "outcome_table": [
                {"outcome": "promise", "reason": "", "when": "at least one promise was recorded", "fact_ids": ["A-R46"]},
                {"outcome": "paid", "reason": "", "when": "rule 39", "fact_ids": ["A-R46"]},
                {"outcome": "transferred", "reason": "restructuring", "when": "rule 41", "fact_ids": ["A-R46"]},
                {"outcome": "transferred", "reason": "human", "when": "rule 42", "fact_ids": ["A-R46"]},
                {"outcome": "transferred", "reason": "support", "when": "rule 32", "fact_ids": ["A-R46"]},
                {"outcome": "no_promise", "reason": "refused", "when": "rules 31 and 45", "fact_ids": ["A-R46"]},
                {"outcome": "no_promise", "reason": "hardship", "when": "rule 32", "fact_ids": ["A-R46"]},
                {"outcome": "no_promise", "reason": "dispute", "when": "rule 40", "fact_ids": ["A-R46"]},
                {"outcome": "no_promise", "reason": "service_error", "when": "rule 37", "fact_ids": ["A-R46"]},
                {"outcome": "not_verified", "reason": "failed", "when": "rule 14", "fact_ids": ["A-R46"]},
                {"outcome": "not_verified", "reason": "declined", "when": "rule 15", "fact_ids": ["A-R46"]},
                {"outcome": "not_reached", "reason": "callback", "when": "rule 6", "fact_ids": ["A-R46"]},
                {"outcome": "not_reached", "reason": "no_callback", "when": "rule 7", "fact_ids": ["A-R46"]},
                {"outcome": "not_reached", "reason": "wrong_number", "when": "rule 8", "fact_ids": ["A-R46"]},
                {"outcome": "not_reached", "reason": "deceased", "when": "rule 9", "fact_ids": ["A-R46"]},
                {"outcome": "not_reached", "reason": "unclear", "when": "rule 3", "fact_ids": ["A-R46"]},
            ],
            "aggregation": {"promise_wins": B(True, "A-R46"), "transfer_wins_over_promise": B(True, "A-R46"), "all_noted_as": [], "else_rule": S("", "A-R46")},
            "note_tool_used": B(False, "A-R46"),
        },
        "required_phrases": [
            {"text": "Am I speaking with {title} {last_name}?", "when": "after the opening sentence", "stage": "opening", "fact_ids": ["A-R2"]},
            {"text": "I am sorry for your loss.", "when": "when told the customer has died", "stage": "third_party", "fact_ids": ["A-R9"]},
            {"text": "Can you make this payment today?", "when": "the first question about paying", "stage": "negotiation", "fact_ids": ["A-R28"]},
            {"text": "Do you confirm?", "when": "after reading the promise back", "stage": "confirmation", "fact_ids": ["A-R34"]},
            {"text": "You will receive a text message confirming this promise.", "when": "after a recorded promise", "stage": "recording", "fact_ids": ["A-R38"]},
        ],
        "behaviour_rules": [
            {"agent_instruction": "If asked something you cannot answer from the tools, say you do not have that information. Do not invent figures, dates or reasons.", "stage": "global", "fact_ids": ["A-R44"]},
            {"agent_instruction": "Never offer a discount, a waiver, an instalment plan or any term that is not in the brief.", "stage": "negotiation", "fact_ids": ["A-R33"]},
            {"agent_instruction": "A relative may not answer the security questions and may not be told anything about the account, even if they offer to pay.", "stage": "third_party", "fact_ids": ["A-R10"]},
            {"agent_instruction": "Ask the security questions one at a time. A wrong answer may be asked again.", "stage": "identity", "fact_ids": ["A-R11", "A-R12"]},
            {"agent_instruction": "Never repeat an offer the customer already refused.", "stage": "negotiation", "fact_ids": ["A-R31"]},
            {"agent_instruction": "A recorded promise cannot be changed or cancelled in this call. If the customer asks, say they can change it in the mobile app.", "stage": "recording", "fact_ids": ["A-R36"]},
        ],
        "unresolved": [],
        "date_conditional": [],
    }


def gold_ab():
    g = gold_a()
    g["multi_product"] = {
        "enabled": B(True, "B-1"), "max_products": I(3, "B-1"), "state_all_first": B(True, "B-2"), "per_product_deadline": B(True, "B-3"), "ask_all_today_first": B(True, "B-4"), "ask_today_once": B(True, "B-4"),
        "per_product_attempts": B(True, "B-5"), "attempts_restart_per_product": B(True, "B-4"), "single_combined_readback": B(True, "B-7"),
        "order": S("as_returned", "B-4"), "date_over_deadline_use_product_deadline_and_say_so": B(True, "B-6"),
        "note_unpromised_products": B(True, "B-8"), "note_even_when_no_promise": B(True, "B-8"), "note_reasons": L(["refused", "hardship", "dispute", "paid", "service_error"], "B-8"),
        "notes_on_transfer": B(False, "B-10"), "unrecorded_on_transfer_are_dropped": B(True, "B-10"), "recorded_before_transfer_stay": B(True, "B-10"),
        "single_product_dispute_or_paid_continues": B(True, "B-9"),
    }
    g["recording"]["failure_note_reason"] = S("service_error", "B-11")
    g["closing"]["note_tool_used"] = B(True, "B-8")
    g["closing"]["aggregation"] = {"promise_wins": B(True, "B-C"), "transfer_wins_over_promise": B(True, "B-10"),
                                   "all_noted_as": [{"reason": "paid", "outcome": "paid", "fact_ids": ["B-C"]}],
                                   "else_rule": S("first_non_paid_note_reason_in_order", "B-C")}
    g["bands"] = [dict(b, fact_ids=b["fact_ids"] + ["B-3"]) for b in g["bands"]]
    for it in g["special_intents"]:
        if it["key"] in ("already_paid", "dispute"):
            it["continue_other_products"] = True
            it["action_kind"] = "note"; it["action_note_reason"] = "paid" if it["key"] == "already_paid" else "dispute"
            it["applies_to"] = "named_product"
            it["fact_ids"] = it["fact_ids"] + ["B-9"]
        if it["key"] == "hardship":
            it["action_note_reason"] = "hardship"; it["fact_ids"] = it["fact_ids"] + ["B-8"]
    g["behaviour_rules"].append({"agent_instruction": "State every late product, one sentence each, before asking for anything.", "stage": "debt_statement", "fact_ids": ["B-2"]})
    g["behaviour_rules"].append({"agent_instruction": "Do not ask about paying today again for each product.", "stage": "negotiation", "fact_ids": ["B-4"]})
    return g


if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parent
    for name, g in (("brief-a", gold_a()), ("brief-ab", gold_ab())):
        spec = Spec.model_validate(g)
        (out / f"{name}.spec.json").write_text(json.dumps(spec.model_dump(), indent=1, ensure_ascii=False))
        print("wrote", name, "intents", len(spec.special_intents), "rows", len(spec.closing.outcome_table))
