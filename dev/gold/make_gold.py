"""Build the gold specs for Brief A and Brief A+B by hand (DEV_PLAN T2.2).

Dev material: contains Brief A/B values. The builder never reads this.
Fact ids: A-R<n> = Brief A rule n, A-S<n> = Brief A section <n> prose/table,
B-<n> = Brief B item n, B-CLOSE = Brief B closing paragraph, IMPL = implied by the brief as a whole.

Run from the repo root:  python dev/gold/make_gold.py
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from builder.schema import Spec  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def s(value, *ids):
    return {"value": value, "fact_ids": list(ids)}


def i(value, *ids):
    return {"value": int(value), "fact_ids": list(ids)}


def b(value, *ids):
    return {"value": bool(value), "fact_ids": list(ids)}


def l(values, *ids):
    return {"values": list(values), "fact_ids": list(ids)}


def close(outcome, reason, *ids):
    return {"outcome": outcome, "reason": reason, "fact_ids": list(ids)}


def intent(key, **kw):
    d = {
        "key": key,
        "trigger_description": "",
        "allowed_before_identity": False,
        "applies_to": "all",
        "say_text": "",
        "say_is_verbatim": False,
        "ask_once_first": False,
        "action_kind": "none",
        "action_queue": "",
        "action_note_reason": "",
        "count_before_action": 1,
        "close_outcome": "",
        "close_reason": "",
        "declined_close_outcome": "",
        "declined_close_reason": "",
        "before_identity_close_outcome": "",
        "before_identity_close_reason": "",
        "continue_call": False,
        "continue_other_products": False,
        "precedence": 50,
        "suppresses_persuasion": False,
        "customer_named_terms_still_recorded": False,
        "fact_ids": [],
    }
    d.update(kw)
    return d


def rule(text, stage, *ids):
    return {"agent_instruction": text, "stage": stage, "fact_ids": list(ids)}


def phrase(text, when, stage, *ids):
    return {"text": text, "when": when, "stage": stage, "fact_ids": list(ids)}


# ---------------------------------------------------------------------------
# Brief A
# ---------------------------------------------------------------------------

A = {
    "bank_name": s("Freya Bank", "A-S1"),
    "language": s("English", "IMPL"),
    "agent_self_description": s("a digital assistant calling from Freya Bank", "A-R1"),
    "call_variables": [
        {"name": "customer_id", "meaning": "Pass it to every tool call.", "fact_ids": ["A-S2"]},
        {"name": "first_name", "meaning": "The person to ask for.", "fact_ids": ["A-S2"]},
        {"name": "last_name", "meaning": "The person to ask for.", "fact_ids": ["A-S2"]},
        {"name": "title", "meaning": "Mr or Ms. Address the customer as title plus last name.", "fact_ids": ["A-S2"]},
        {"name": "now", "meaning": "The current date and time. All date rules use this, never the real clock.", "fact_ids": ["A-S2"]},
    ],
    "roles": {
        "customer_id_var": s("customer_id", "A-S2"),
        "now_var": s("now", "A-S2"),
        "address_form": s("{title} {last_name}", "A-S2"),
    },
    "opening": {
        "required_elements": l(["digital assistant", "calling from Freya Bank", "the call is recorded"], "A-R1"),
        "forbidden_before_identity": l(["collections", "debt", "payment", "the product"], "A-R1"),
        "confirm_question": s("Am I speaking with {title} {last_name}?", "A-R2"),
        "accept_examples": l(["yes", "that's me", "speaking", "the customer's own name"], "A-R3"),
        "nonconfirm_examples": l(["hello", "go ahead", "who is this"], "A-R3"),
        "max_confirm_asks": i(2, "A-R3"),
        "answer_question_then_count_as_ask": b(True, "A-R3"),
        "unclear_close": close("not_reached", "unclear", "A-R3"),
        "robot_question_reply": s("Say that you are Freya Bank's digital assistant and continue.", "A-R4"),
    },
    "third_party": {
        "say_only_opening": b(True, "A-R5", "A-R1"),
        "ask_when_reachable": b(True, "A-R5"),
        "callback": {
            "allowed_days": l(["today", "next_business_day"], "A-R6"),
            "from_time": s("10:00", "A-R6"),
            "to_time": s("19:00", "A-R6"),
            "inclusive": b(True, "A-R6"),
            "after_now": b(True, "A-R6"),
            "ask_again_times": i(1, "A-R7"),
        },
        "callback_close": close("not_reached", "callback", "A-R6"),
        "no_callback_close": close("not_reached", "no_callback", "A-R7"),
        "wrong_number_close": close("not_reached", "wrong_number", "A-R8"),
        "deceased_close": close("not_reached", "deceased", "A-R9"),
        "deceased_sentence": s("I am sorry for your loss.", "A-R9"),
        "deceased_ask_nothing_else": b(True, "A-R9"),
        "relative_cannot_verify": b(True, "A-R10"),
    },
    "identity": {
        "questions": [
            {
                "api_field": "date_of_birth",
                "ask_text": "Ask for the date of birth.",
                "answer_format": "YYYY-MM-DD",
                "numeric_date_order": "day_month_year",
                "fact_ids": ["A-R11"],
            },
            {
                "api_field": "phone_last4",
                "ask_text": "Ask for the last four digits of the phone number on file.",
                "answer_format": "four digits",
                "numeric_date_order": "",
                "fact_ids": ["A-R11"],
            },
        ],
        "one_at_a_time": b(True, "A-R11"),
        "max_wrong_total": i(3, "A-R12"),
        "wrong_may_retry": b(True, "A-R12"),
        "swapped": {
            "hint_value": s("day_month_swapped", "A-R13"),
            "instruction": s("Ask the customer to say the month as a word.", "A-R13"),
            "counts_as_wrong": b(False, "A-R13"),
        },
        "decline": {
            "explain_once_text": s("Explain once that the questions protect their account.", "A-R15"),
            "max_declines": i(2, "A-R15"),
            "purpose_question_counts": b(True, "A-R15"),
        },
        "fail_message": s("Tell the customer to use the mobile app or a branch.", "A-R14"),
        "fail_close": close("not_verified", "failed", "A-R14"),
        "decline_close": close("not_verified", "declined", "A-R15"),
        "do_not_state_debt_on_fail": b(True, "A-R14"),
    },
    "calendar": {
        "business_weekdays": l(["monday", "tuesday", "wednesday", "thursday", "friday"], "A-S7"),
        "holidays": l(["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"], "A-S7"),
        "deadline_rule": {"kind": s("nth_business_day_after_today", "A-R18"), "n_from_band": b(True, "A-R18")},
        "next_weekday": s("following_calendar_week", "A-R22"),
        "this_weekday": s("current_week", "A-R22"),
        "numeric_date_order": s("day_month_year", "A-R11"),
        "date_source": s("now", "A-S2"),
    },
    "bands": [
        {"label": "early", "days_late_min": 1, "days_late_max": 7, "deadline_business_days": 12, "persuasion_attempts": 1, "fact_ids": ["A-R18"]},
        {"label": "late", "days_late_min": 8, "days_late_max": 45, "deadline_business_days": 7, "persuasion_attempts": 2, "fact_ids": ["A-R18"]},
    ],
    "debt_statement": {
        "intro_instruction": s("Say that you are calling from the collections team about a late payment.", "A-R17"),
        "product_labels": [
            {"product_type": "credit_card", "template": "credit card ending {card_last4}", "fact_ids": ["A-R17"]},
            {"product_type": "personal_loan", "template": "personal loan", "fact_ids": ["A-R17"]},
            {"product_type": "car_loan", "template": "car loan", "fact_ids": ["A-R17"]},
        ],
        "include": l(["past_due", "days_late"], "A-R17"),
        "account_tool_after_identity": b(True, "A-R16"),
    },
    "amounts": {
        "floor_field_by_type": [
            {"product_type": "credit_card", "account_field": "minimum_payment", "fact_ids": ["A-R25"]},
            {"product_type": "personal_loan", "account_field": "instalment_amount", "fact_ids": ["A-R25"]},
            {"product_type": "car_loan", "account_field": "instalment_amount", "fact_ids": ["A-R25"]},
        ],
        "ask_full_first": b(True, "A-R24"),
        "never_ask_how_much": b(True, "A-R24"),
        "agent_proposes_every_amount": b(True, "A-R24"),
        "accept_range": {"min": s("floor", "A-R27"), "max": s("full", "A-R27"), "inclusive": b(True, "A-R27")},
        "too_much": {"offer_floor_once": b(True, "A-R26"), "say_rest_overdue": b(True, "A-R26")},
        "below_floor": {"say_cannot_record": b(True, "A-R27"), "offer_floor_once": b(True, "A-R27")},
        "refuse_floor_is_flat_refusal": b(True, "A-R26", "A-R27"),
    },
    "negotiation": {
        "first_question": s("Can you make this payment today?", "A-R28"),
        "promise_date": {
            "not_before": s("today", "A-R19"),
            "business_day_only": b(True, "A-R19"),
            "not_after": s("deadline", "A-R19"),
        },
        "attempts": [
            {
                "n": 1,
                "amount": "floor_if_full_refused",
                "date": "last_business_day_this_week",
                "if_today_is_that_day": "last_business_day_next_week",
                "bands_allowed": [],
                "fact_ids": ["A-R30"],
            },
            {
                "n": 2,
                "amount": "floor",
                "date": "deadline",
                "if_today_is_that_day": "",
                "bands_allowed": ["late"],
                "fact_ids": ["A-R30", "A-R26"],
            },
        ],
        "proposal_is_not_refusal": b(True, "A-R29"),
        "no_to_today_without_terms_is_refusal": b(True, "A-R30"),
        "vague": {"ask_once": b(True, "A-R21"), "then": s("propose_deadline", "A-R21")},
        "nonbusiness_date": {"offer_next_business_day": b(True, "A-R20")},
        "after_deadline": {"offer_deadline": b(True, "A-R23"), "refusing_deadline_is_flat_refusal": b(True, "A-R23")},
        "no_answer_is_refusal": b(True, "A-R30"),
        "no_repeat_refused_offer": b(True, "A-R31"),
        "exhausted_close": close("no_promise", "refused", "A-R31"),
        "forbidden_offers": l(["discount", "waiver", "instalment plan", "any term not in the brief"], "A-R33"),
    },
    "special_intents": [
        intent(
            "hardship",
            trigger_description="The customer mentions illness, a death in the family or job loss.",
            say_text="One short sentence of sympathy.",
            ask_once_first=True,
            action_kind="transfer",
            action_queue="support",
            close_outcome="transferred",
            close_reason="support",
            declined_close_outcome="no_promise",
            declined_close_reason="hardship",
            precedence=10,
            suppresses_persuasion=True,
            customer_named_terms_still_recorded=True,
            fact_ids=["A-R32"],
        ),
        intent(
            "already_paid",
            trigger_description="The customer says they already paid this past-due amount.",
            say_text="Say that payments can take one business day to appear.",
            action_kind="none",
            close_outcome="paid",
            close_reason="",
            precedence=20,
            suppresses_persuasion=True,
            fact_ids=["A-R39"],
        ),
        intent(
            "dispute",
            trigger_description="The customer says the debt is not theirs, they never had the product, or the product was closed or paid off in the past.",
            say_text="Do not argue and do not take a promise.",
            action_kind="none",
            close_outcome="no_promise",
            close_reason="dispute",
            precedence=20,
            suppresses_persuasion=True,
            fact_ids=["A-R40"],
        ),
        intent(
            "wants_plan",
            trigger_description="The customer asks for a new payment plan or lower instalments.",
            say_text="Do not describe a plan.",
            action_kind="transfer",
            action_queue="restructuring",
            close_outcome="transferred",
            close_reason="restructuring",
            precedence=30,
            suppresses_persuasion=True,
            fact_ids=["A-R41"],
        ),
        intent(
            "wants_human",
            trigger_description="The customer asks for a human.",
            allowed_before_identity=True,
            ask_once_first=True,
            action_kind="transfer",
            action_queue="general",
            close_outcome="transferred",
            close_reason="human",
            precedence=30,
            fact_ids=["A-R42", "A-R45"],
        ),
        intent(
            "not_talk",
            trigger_description="The customer says they do not want to talk.",
            allowed_before_identity=True,
            count_before_action=2,
            action_kind="none",
            close_outcome="no_promise",
            close_reason="refused",
            before_identity_close_outcome="not_verified",
            before_identity_close_reason="declined",
            precedence=40,
            fact_ids=["A-R45"],
        ),
        intent(
            "robot_question",
            trigger_description="The customer asks whether this is a robot or an AI.",
            allowed_before_identity=True,
            say_text="Say that you are Freya Bank's digital assistant and continue.",
            continue_call=True,
            precedence=90,
            fact_ids=["A-R4"],
        ),
        intent(
            "scam_question",
            trigger_description="The customer asks whether this is a scam.",
            allowed_before_identity=True,
            say_text="Say they can verify the call by phoning Freya Bank's customer service number, and continue.",
            continue_call=True,
            precedence=90,
            fact_ids=["A-R43"],
        ),
        intent(
            "unknown_question",
            trigger_description="A question the agent cannot answer from the tools.",
            allowed_before_identity=True,
            say_text="Say you do not have that information. Do not invent figures, dates or reasons.",
            continue_call=True,
            precedence=90,
            fact_ids=["A-R44"],
        ),
    ],
    "confirmation": {
        "readback_elements": l(["product", "amount", "date"], "A-R34"),
        "confirm_question": s("Do you confirm?", "A-R34"),
        "record_only_after_clear_yes": b(True, "A-R34"),
        "recheck_on_change": b(True, "A-R35"),
        "one_promise_per_product": b(True, "A-R36"),
        "change_after_record_text": s("Say they can change it in the mobile app.", "A-R36"),
    },
    "recording": {
        "max_attempts": i(2, "A-R37"),
        "say_recorded_only_on_ok": b(True, "A-R37"),
        "success_sentence": s("You will receive a text message confirming this promise.", "A-R38"),
        "failure_say": s("Say you could not record it.", "A-R37"),
        "failure_close": close("no_promise", "service_error", "A-R37"),
        "failure_note_reason": s("", "A-S12"),
    },
    "multi_product": {
        "enabled": b(False, "A-S1"),
        "max_products": i(1, "A-S1"),
        "state_all_first": b(False, "A-S1"),
        "per_product_deadline": b(False, "A-S1"),
        "ask_all_today_first": b(False, "A-S1"),
        "ask_today_once": b(False, "A-S1"),
        "per_product_attempts": b(False, "A-S1"),
        "attempts_restart_per_product": b(False, "A-S1"),
        "single_combined_readback": b(False, "A-S1"),
        "order": s("as_returned", "A-S1"),
        "date_over_deadline_use_product_deadline_and_say_so": b(False, "A-S1"),
        "note_unpromised_products": b(False, "A-S12"),
        "note_even_when_no_promise": b(False, "A-S12"),
        "note_reasons": l([], "A-S12"),
        "notes_on_transfer": b(False, "A-S12"),
        "unrecorded_on_transfer_are_dropped": b(False, "A-S1"),
        "recorded_before_transfer_stay": b(True, "A-S12"),
        "single_product_dispute_or_paid_continues": b(False, "A-S1"),
    },
    "closing": {
        "goodbye_before_close": b(True, "A-R47"),
        "exactly_one_close": b(True, "A-R46"),
        "close_is_last_tool_call": b(True, "A-R46"),
        "outcome_table": [
            {"outcome": "promise", "reason": "", "when": "at least one promise was recorded", "fact_ids": ["A-S12"]},
            {"outcome": "paid", "reason": "", "when": "rule 39", "fact_ids": ["A-S12", "A-R39"]},
            {"outcome": "transferred", "reason": "restructuring", "when": "rule 41", "fact_ids": ["A-S12", "A-R41"]},
            {"outcome": "transferred", "reason": "human", "when": "rule 42", "fact_ids": ["A-S12", "A-R42"]},
            {"outcome": "transferred", "reason": "support", "when": "rule 32", "fact_ids": ["A-S12", "A-R32"]},
            {"outcome": "no_promise", "reason": "refused", "when": "rules 31 and 45", "fact_ids": ["A-S12", "A-R31", "A-R45"]},
            {"outcome": "no_promise", "reason": "hardship", "when": "rule 32", "fact_ids": ["A-S12", "A-R32"]},
            {"outcome": "no_promise", "reason": "dispute", "when": "rule 40", "fact_ids": ["A-S12", "A-R40"]},
            {"outcome": "no_promise", "reason": "service_error", "when": "rule 37", "fact_ids": ["A-S12", "A-R37"]},
            {"outcome": "not_verified", "reason": "failed", "when": "rule 14", "fact_ids": ["A-S12", "A-R14"]},
            {"outcome": "not_verified", "reason": "declined", "when": "rule 15", "fact_ids": ["A-S12", "A-R15"]},
            {"outcome": "not_reached", "reason": "callback", "when": "rule 6", "fact_ids": ["A-S12", "A-R6"]},
            {"outcome": "not_reached", "reason": "no_callback", "when": "rule 7", "fact_ids": ["A-S12", "A-R7"]},
            {"outcome": "not_reached", "reason": "wrong_number", "when": "rule 8", "fact_ids": ["A-S12", "A-R8"]},
            {"outcome": "not_reached", "reason": "deceased", "when": "rule 9", "fact_ids": ["A-S12", "A-R9"]},
            {"outcome": "not_reached", "reason": "unclear", "when": "rule 3", "fact_ids": ["A-S12", "A-R3"]},
        ],
        "aggregation": {
            "promise_wins": b(True, "A-S12"),
            "transfer_wins_over_promise": b(True, "A-S12"),
            "all_noted_as": [],
            "else_rule": s("", "A-S12"),
        },
        "note_tool_used": b(False, "A-S12"),
    },
    "required_phrases": [
        phrase("Am I speaking with {title} {last_name}?", "opening confirm question", "opening", "A-R2"),
        phrase("I am sorry for your loss.", "a third party says the customer has died", "third_party", "A-R9"),
        phrase("Can you make this payment today?", "first question after stating the debt", "negotiation", "A-R28"),
        phrase("Do you confirm?", "after reading the promise back", "confirmation", "A-R34"),
        phrase("You will receive a text message confirming this promise.", "after create_promise returned ok", "recording", "A-R38"),
    ],
    "behaviour_rules": [
        rule("Do not say collections, debt, payment or the product before identity is verified. This applies to everyone, including relatives.", "global", "A-R1"),
        rule("If the customer asks whether you are a robot or an AI, say that you are Freya Bank's digital assistant and continue.", "global", "A-R4"),
        rule("With someone else on the line, do not say why you are calling; say nothing beyond the opening sentence and ask when the customer can be reached.", "third_party", "A-R5"),
        rule("A relative may not answer the security questions and may not be told anything about the account, even if they offer to pay.", "third_party", "A-R10"),
        rule("Send a date of birth as YYYY-MM-DD, whatever way the customer said it. Read a date given only as numbers as day, then month, then year.", "identity", "A-R11"),
        rule("If the date of birth comes back with the hint day_month_swapped, ask the customer to say the month as a word; that retry does not count as a wrong answer.", "identity", "A-R13"),
        rule("After three wrong answers, do not state the debt; tell the customer to use the mobile app or a branch.", "identity", "A-R14"),
        rule("If the customer does not want to answer, explain once that the questions protect their account; asking what the call is about instead of answering counts as declining.", "identity", "A-R15"),
        rule("Say that you are calling from the collections team about a late payment; name the product in words; state the past-due amount and how many days late it is.", "debt_statement", "A-R17"),
        rule("A promise date must be today or later, a business day, and not after the deadline.", "negotiation", "A-R19"),
        rule("If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day.", "negotiation", "A-R20"),
        rule("If the customer gives a vague period, ask once for the exact day; if they still give none, propose the deadline.", "negotiation", "A-R21"),
        rule("Next <weekday> means that weekday in the following calendar week; this <weekday> means the one in the current week.", "negotiation", "A-R22"),
        rule("If the customer asks for a date after the deadline, say the latest date you can record is the deadline and offer it; refusing the deadline is a flat refusal.", "negotiation", "A-R23"),
        rule("Ask for the full past-due amount first. Never ask how much the customer can pay; the agent proposes every amount.", "negotiation", "A-R24"),
        rule("If the full amount is too much, offer the floor once and say that the rest stays overdue; refusing the floor is a flat refusal.", "negotiation", "A-R26"),
        rule("Accept any amount from the floor up to the full amount, both included. Below the floor, say it cannot be recorded and offer the floor once.", "negotiation", "A-R27"),
        rule("A date or an amount the customer proposes is never a refusal.", "negotiation", "A-R29"),
        rule("A flat refusal or a non-answer uses one persuasion attempt; a no to paying today with no date and no amount is a flat refusal.", "negotiation", "A-R30"),
        rule("When the attempts are used up, stop and do not repeat an offer the customer already refused.", "negotiation", "A-R31"),
        rule("On illness, a death in the family or job loss: one short sentence of sympathy, no persuasion attempt, offer to connect to customer support; still record a promise if the customer names a date or an amount themselves.", "special", "A-R32"),
        rule("Never offer a discount, a waiver, an instalment plan or any term that is not in the brief.", "global", "A-R33"),
        rule("Read the product, the amount and the date back and ask for confirmation; record only after a clear yes.", "confirmation", "A-R34"),
        rule("If the customer changes the date or the amount at the read-back, check the new value and read it back again.", "confirmation", "A-R35"),
        rule("A recorded promise cannot be changed or cancelled in the same call; if asked, say they can change it in the mobile app.", "confirmation", "A-R36"),
        rule("Say the promise is recorded only after create_promise returns ok true; if it fails, try once more; if it fails again, say you could not record it.", "recording", "A-R37"),
        rule("Already paid: say that payments can take one business day to appear and take no promise.", "special", "A-R39"),
        rule("Dispute: do not argue and do not take a promise. A claim that the product was closed or paid off in the past is a dispute.", "special", "A-R40"),
        rule("Payment plan request: do not describe a plan; transfer to restructuring.", "special", "A-R41"),
        rule("Request for a human: ask once whether you can help first; if they insist, transfer to the general queue.", "special", "A-R42"),
        rule("Is this a scam: say they can verify the call by phoning Freya Bank's customer service number, and continue.", "global", "A-R43"),
        rule("For a question you cannot answer from the tools, say you do not have that information; do not invent figures, dates or reasons.", "global", "A-R44"),
        rule("If the customer says twice that they do not want to talk, close the call.", "global", "A-R45"),
        rule("Thank the customer and say goodbye before close_call.", "closing", "A-R47"),
    ],
    "unresolved": [],
    "date_conditional": [],
}

# ---------------------------------------------------------------------------
# Brief A + B
# ---------------------------------------------------------------------------

AB = copy.deepcopy(A)
AB["multi_product"] = {
    "enabled": b(True, "B-1"),
    "max_products": i(3, "B-1"),
    "state_all_first": b(True, "B-2"),
    "per_product_deadline": b(True, "B-3"),
    "ask_all_today_first": b(True, "B-4"),
    "ask_today_once": b(True, "B-4"),
    "per_product_attempts": b(True, "B-5"),
    "attempts_restart_per_product": b(True, "B-4"),
    "single_combined_readback": b(True, "B-7"),
    "order": s("as_returned", "B-4"),
    "date_over_deadline_use_product_deadline_and_say_so": b(True, "B-6"),
    "note_unpromised_products": b(True, "B-8"),
    "note_even_when_no_promise": b(True, "B-8"),
    "note_reasons": l(["refused", "hardship", "dispute", "paid", "service_error"], "B-8"),
    "notes_on_transfer": b(False, "B-10"),
    "unrecorded_on_transfer_are_dropped": b(True, "B-10"),
    "recorded_before_transfer_stay": b(True, "B-10", "A-S12"),
    "single_product_dispute_or_paid_continues": b(True, "B-9"),
}
AB["recording"]["failure_note_reason"] = s("service_error", "B-11")
AB["closing"]["note_tool_used"] = b(True, "B-8")
AB["closing"]["aggregation"] = {
    "promise_wins": b(True, "B-CLOSE"),
    "transfer_wins_over_promise": b(True, "B-10", "A-S12"),
    "all_noted_as": [{"reason": "paid", "outcome": "paid", "fact_ids": ["B-CLOSE"]}],
    "else_rule": s("first_non_paid_note_reason_in_order", "B-CLOSE"),
}
for it in AB["special_intents"]:
    if it["key"] in ("dispute", "already_paid"):
        it["applies_to"] = "current_product"
        it["action_kind"] = "note"
        it["action_note_reason"] = "dispute" if it["key"] == "dispute" else "paid"
        it["close_outcome"] = ""
        it["close_reason"] = ""
        it["continue_other_products"] = True
        it["fact_ids"].append("B-9")
    if it["key"] == "hardship":
        it["action_note_reason"] = "hardship"
        it["fact_ids"].append("B-8")
    if it["key"] == "wants_plan":
        it["fact_ids"].append("B-10")
AB["behaviour_rules"] += [
    rule("State every late product, one sentence each, before asking for anything.", "debt_statement", "B-2"),
    rule("First ask whether the customer can pay all of them today. If not, go through the products one by one in the order returned; do not ask about today again for each product; start each product at attempt 1.", "negotiation", "B-4"),
    rule("If the customer names one date for everything and it is after one product's deadline, record that product on its own deadline and say so in the read-back.", "confirmation", "B-6"),
    rule("Read all promises back together and ask for one confirmation; then call create_promise once per product.", "confirmation", "B-7"),
    rule("A dispute or an already-paid claim on one product does not end the call: note it and continue with the others.", "special", "B-9"),
    rule("On any transfer add no notes at all, before or after it. Promises recorded before the request stay; promises agreed but not yet recorded are not recorded.", "special", "B-10"),
    rule("If one create_promise fails twice, keep the promises that were recorded and add a note with reason service_error for the failed product.", "recording", "B-11"),
]


def write(spec: dict, name: str) -> None:
    model = Spec.model_validate(spec)  # raises on any schema mismatch
    path = os.path.join(HERE, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model.model_dump(), f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote", path)


if __name__ == "__main__":
    write(A, "brief-a.spec.json")
    write(AB, "brief-ab.spec.json")
