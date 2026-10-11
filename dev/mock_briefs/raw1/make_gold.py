"""Gold spec for the raw-material mock brief raw1 (DEV_PLAN T2.4a). Dev material.

Documents: 01 mail (2026-09-02), 02 policy extract v4.2 (2026-06-15), 03 memo (2026-09-20, changes three values without
saying "supersedes" and adds a holiday), 04 code list, 05 thread (discussion, decides nothing). Tool API: tools.json
(identity fields postcode/birth_year, queues payment_plans/agents/care).

Expected resolution: memo (later date) wins on band max (60 -> 75) and fresh deadline (10 -> 8 business days); the
callback close 18:00 -> 17:00 carries effective_from 2026-10-01, so the spec holds 18:00 and `date_conditional` holds
17:00 from 2026-10-01. The thread's Saturday window and half-minimum floor are discussion and never appear.

Fact ids: M-MAIL, M-POL-<rule>, M-MEMO-<n>, M-CODE, M-IMPL.   Run from the repo root: python dev/mock_briefs/raw1/make_gold.py
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "dev", "gold"))
from make_gold import A, b, close, i, intent, l, phrase, rule, s  # noqa: E402  (Brief A gold as the base shape)

from builder.schema import Spec  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

G = copy.deepcopy(A)
G["bank_name"] = s("Nordlys Bank", "M-MAIL")
G["agent_self_description"] = s("an automated assistant from Nordlys Bank", "M-MAIL")
G["call_variables"] = [
    {"name": "customer_id", "meaning": "Send it in every tool call.", "fact_ids": ["M-MAIL"]},
    {"name": "given_name", "meaning": "The person we are trying to reach.", "fact_ids": ["M-MAIL"]},
    {"name": "family_name", "meaning": "The person we are trying to reach.", "fact_ids": ["M-MAIL"]},
    {"name": "salutation", "meaning": "Mr, Ms or Mx; address the customer as salutation plus family name.", "fact_ids": ["M-MAIL"]},
    {"name": "call_time", "meaning": "The current date and time; all date arithmetic uses it, never the machine clock.", "fact_ids": ["M-MAIL"]},
]
G["roles"] = {"customer_id_var": s("customer_id", "M-MAIL"), "now_var": s("call_time", "M-MAIL"), "address_form": s("{salutation} {family_name}", "M-MAIL")}
G["opening"] = {
    "required_elements": l(["automated assistant", "from Nordlys Bank", "the call may be recorded"], "M-MAIL"),
    "first_sentence": s("Hello, this is an automated assistant from Nordlys Bank. This call may be recorded.", "M-MAIL"),
    "forbidden_before_identity": l(["arrears", "overdue", "payment", "the product"], "M-MAIL"),
    "confirm_question": s("Am I speaking with {salutation} {family_name}?", "M-MAIL"),
    "accept_examples": l(["yes", "that's me", "speaking", "the person's own name"], "M-MAIL"),
    "nonconfirm_examples": l(["hello", "go on", "who is calling"], "M-MAIL"),
    "max_confirm_asks": i(2, "M-MAIL"),
    "answer_question_then_count_as_ask": b(True, "M-MAIL"),
    "unclear_close": close("not_reached", "unclear", "M-MAIL", "M-CODE"),
    "robot_question_reply": s("Say it is Nordlys Bank's automated assistant and carry on.", "M-MAIL"),
}
G["third_party"] = {
    "say_only_opening": b(True, "M-POL-A1", "M-MAIL"),
    "ask_when_reachable": b(True, "M-POL-A1"),
    "callback": {
        "allowed_days": l(["today", "next_business_day"], "M-POL-A2"),
        "from_time": s("09:00", "M-POL-A2", "M-MEMO-1"),
        "to_time": s("18:00", "M-POL-A2"),
        "inclusive": b(True, "M-POL-A2"),
        "after_now": b(True, "M-POL-A2"),
        "ask_again_times": i(1, "M-POL-A3"),
    },
    "callback_close": close("not_reached", "callback", "M-POL-A2", "M-CODE"),
    "no_callback_close": close("not_reached", "no_callback", "M-POL-A3", "M-CODE"),
    "wrong_number_close": close("not_reached", "wrong_number", "M-POL-A4", "M-CODE"),
    "deceased_close": close("not_reached", "deceased", "M-POL-A5", "M-CODE"),
    "deceased_sentence": s("Please accept my condolences.", "M-POL-A5"),
    "deceased_ask_nothing_else": b(True, "M-POL-A5"),
    "relative_cannot_verify": b(True, "M-POL-A6"),
}
G["identity"] = {
    "questions": [
        {"api_field": "postcode", "ask_text": "Ask for the postcode of the registered address.", "answer_format": "postcode, spaces removed", "numeric_date_order": "", "fact_ids": ["M-MAIL"]},
        {"api_field": "birth_year", "ask_text": "Ask for the year of birth.", "answer_format": "four digits", "numeric_date_order": "", "fact_ids": ["M-MAIL"]},
    ],
    "one_at_a_time": b(True, "M-MAIL"),
    "max_wrong_total": i(3, "M-POL-B1"),
    "wrong_may_retry": b(True, "M-POL-B1"),
    "swapped": {"hint_value": s("", "M-IMPL"), "instruction": s("", "M-IMPL"), "counts_as_wrong": b(False, "M-IMPL")},
    "decline": {"explain_once_text": s("Explain once that the questions protect their account.", "M-POL-B3"), "max_declines": i(2, "M-POL-B3"), "purpose_question_counts": b(True, "M-POL-B3")},
    "fail_message": s("Tell the customer to call the service line or visit a branch.", "M-POL-B2"),
    "fail_close": close("not_verified", "failed", "M-POL-B2", "M-CODE"),
    "decline_close": close("not_verified", "declined", "M-POL-B3", "M-CODE"),
    "do_not_state_debt_on_fail": b(True, "M-POL-B2"),
}
G["calendar"] = {
    "business_weekdays": l(["monday", "tuesday", "wednesday", "thursday", "friday"], "M-POL-D"),
    "holidays": l(["2026-10-19", "2026-11-02", "2026-12-24", "2026-12-25", "2026-12-31", "2027-01-01"], "M-POL-D", "M-MEMO-4"),
    "deadline_rule": {"kind": s("nth_business_day_after_today", "M-POL-D1"), "n_from_band": b(True, "M-POL-D1")},
    "next_weekday": s("following_calendar_week", "M-POL-D5"),
    "this_weekday": s("current_week", "M-POL-D5"),
    "numeric_date_order": s("", "M-IMPL"),
    "date_source": s("call_time", "M-MAIL"),
}
G["bands"] = [
    {"label": "fresh", "days_late_min": 1, "days_late_max": 10, "deadline_business_days": 8, "persuasion_attempts": 1, "fact_ids": ["M-POL-D1", "M-MEMO-3"]},
    {"label": "overdue", "days_late_min": 11, "days_late_max": 75, "deadline_business_days": 6, "persuasion_attempts": 2, "fact_ids": ["M-POL-D1", "M-MEMO-2"]},
]
G["debt_statement"] = {
    "intro_instruction": s("Say that you are calling from the collections department about an overdue payment.", "M-POL-C2"),
    "product_labels": [
        {"product_type": "credit_card", "template": "credit card ending {card_last4}", "fact_ids": ["M-POL-C2"]},
        {"product_type": "personal_loan", "template": "personal loan", "fact_ids": ["M-POL-C2"]},
        {"product_type": "car_loan", "template": "car loan", "fact_ids": ["M-POL-C2"]},
    ],
    "include": l(["past_due", "days_late"], "M-POL-C2"),
    "account_tool_after_identity": b(True, "M-POL-C1"),
}
G["amounts"] = {
    "floor_field_by_type": [
        {"product_type": "credit_card", "account_field": "minimum_payment", "fact_ids": ["M-POL-E2"]},
        {"product_type": "personal_loan", "account_field": "instalment_amount", "fact_ids": ["M-POL-E2"]},
        {"product_type": "car_loan", "account_field": "instalment_amount", "fact_ids": ["M-POL-E2"]},
    ],
    "ask_full_first": b(True, "M-POL-E1"),
    "never_ask_how_much": b(True, "M-POL-E1"),
    "agent_proposes_every_amount": b(True, "M-POL-E1"),
    "accept_range": {"min": s("floor", "M-POL-E4"), "max": s("full", "M-POL-E4"), "inclusive": b(True, "M-POL-E4")},
    "too_much": {"offer_floor_once": b(True, "M-POL-E3", "M-MEMO-5"), "say_rest_overdue": b(True, "M-POL-E3")},
    "below_floor": {"say_cannot_record": b(True, "M-POL-E4"), "offer_floor_once": b(True, "M-POL-E4")},
    "refuse_floor_is_flat_refusal": b(True, "M-POL-E3", "M-POL-E4"),
}
G["negotiation"] = {
    "first_question": s("Could you settle this amount today?", "M-POL-F1"),
    "promise_date": {"not_before": s("today", "M-POL-D2"), "business_day_only": b(True, "M-POL-D2"), "not_after": s("deadline", "M-POL-D2")},
    "attempts": [
        {"n": 1, "amount": "floor_if_full_refused", "date": "last_business_day_this_week", "if_today_is_that_day": "last_business_day_next_week", "bands_allowed": [], "fact_ids": ["M-POL-F3"]},
        {"n": 2, "amount": "floor", "date": "deadline", "if_today_is_that_day": "", "bands_allowed": ["overdue"], "fact_ids": ["M-POL-F3", "M-POL-E3"]},
    ],
    "proposal_is_not_refusal": b(True, "M-POL-F2"),
    "no_to_today_without_terms_is_refusal": b(True, "M-POL-F3"),
    "vague": {"ask_once": b(True, "M-POL-D4"), "then": s("propose_deadline", "M-POL-D4")},
    "nonbusiness_date": {"offer_next_business_day": b(True, "M-POL-D3")},
    "after_deadline": {"offer_deadline": b(True, "M-POL-D6"), "refusing_deadline_is_flat_refusal": b(True, "M-POL-D6")},
    "no_answer_is_refusal": b(True, "M-POL-F3"),
    "no_repeat_refused_offer": b(True, "M-POL-F4"),
    "exhausted_close": close("no_promise", "refused", "M-POL-F4", "M-CODE"),
    "forbidden_offers": l(["discount", "fee waiver", "payment plan", "any term not in the policy"], "M-POL-F6"),
}
G["special_intents"] = [
    intent("hardship", trigger_description="The customer mentions illness, a bereavement or losing their job.", say_text="One short sentence of sympathy.",
           ask_once_first=True, ask_once_text="Offer to connect them to the customer care team.", action_kind="transfer", action_queue="care",
           close_outcome="transferred", close_reason="care", declined_close_outcome="no_promise", declined_close_reason="hardship",
           precedence=10, suppresses_persuasion=True, customer_named_terms_still_recorded=True, fact_ids=["M-POL-F5", "M-CODE"]),
    intent("already_paid", trigger_description="The customer says they have already paid this overdue amount.", say_text="Say that payments can take one business day to show.",
           close_outcome="paid", close_reason="", precedence=50, suppresses_persuasion=True, fact_ids=["M-POL-G1", "M-CODE"]),
    intent("dispute", trigger_description="The customer says this is not their debt, they never had the product, or it was closed or settled in the past.",
           say_text="Do not argue and take no promise.", close_outcome="no_promise", close_reason="disputed", precedence=50, suppresses_persuasion=True, fact_ids=["M-POL-G2", "M-CODE"]),
    intent("wants_plan", trigger_description="The customer asks for a payment plan or lower instalments.", say_text="Do not describe any plan.",
           action_kind="transfer", action_queue="payment_plans", close_outcome="transferred", close_reason="plan", precedence=50, suppresses_persuasion=True, fact_ids=["M-POL-G3", "M-CODE"]),
    intent("wants_human", trigger_description="The customer asks for a human.", allowed_before_identity=True, ask_once_first=True, ask_once_text="Ask once whether you can help first.",
           action_kind="transfer", action_queue="agents", close_outcome="transferred", close_reason="agent", precedence=50, fact_ids=["M-POL-G4", "M-POL-G7", "M-CODE"]),
    intent("not_talk", trigger_description="The customer says they do not want to talk.", allowed_before_identity=True, count_before_action=2,
           close_outcome="no_promise", close_reason="refused", before_identity_close_outcome="not_verified", before_identity_close_reason="declined",
           precedence=50, fact_ids=["M-POL-G7", "M-CODE"]),
    intent("robot_question", trigger_description="The customer asks whether they are talking to a robot.", allowed_before_identity=True,
           say_text="Say it is Nordlys Bank's automated assistant and carry on.", continue_call=True, precedence=50, fact_ids=["M-MAIL"]),
    intent("scam_question", trigger_description="The customer asks whether this is a scam.", allowed_before_identity=True,
           say_text="Say the customer can check by calling the number on the back of their card, and continue.", continue_call=True, precedence=50, fact_ids=["M-POL-G5"]),
    intent("unknown_question", trigger_description="A question the assistant cannot answer from the tools.", allowed_before_identity=True,
           say_text="Say you do not have that information. Never invent figures, dates or reasons.", continue_call=True, precedence=50, fact_ids=["M-POL-G6"]),
]
G["confirmation"] = {
    "readback_elements": l(["product", "amount", "date"], "M-POL-H1"),
    "confirm_question": s("Is that correct?", "M-POL-H1"),
    "record_only_after_clear_yes": b(True, "M-POL-H1"),
    "recheck_on_change": b(True, "M-POL-H2"),
    "one_promise_per_product": b(True, "M-POL-H3"),
    "change_after_record_text": s("Say it can be changed in online banking.", "M-POL-H3"),
}
G["recording"] = {
    "max_attempts": i(2, "M-POL-H4"),
    "say_recorded_only_on_ok": b(True, "M-POL-H4"),
    "success_sentence": s("We will send you an SMS confirming this arrangement.", "M-POL-H5"),
    "failure_say": s("Say you could not record it.", "M-POL-H4"),
    "failure_close": close("no_promise", "service_error", "M-POL-H4", "M-CODE"),
    "failure_note_reason": s("", "M-POL-I1"),
}
for k in G["multi_product"]:
    G["multi_product"][k]["fact_ids"] = ["M-MAIL"]
G["closing"] = {
    "goodbye_before_close": b(True, "M-MAIL"),
    "exactly_one_close": b(True, "M-POL-I1"),
    "close_is_last_tool_call": b(True, "M-POL-I1"),
    "outcome_table": [
        {"outcome": "promise", "reason": "", "when": "at least one promise was recorded", "fact_ids": ["M-CODE"]},
        {"outcome": "paid", "reason": "", "when": "already paid (G.1)", "fact_ids": ["M-CODE", "M-POL-G1"]},
        {"outcome": "transferred", "reason": "plan", "when": "payment plan request (G.3)", "fact_ids": ["M-CODE", "M-POL-G3"]},
        {"outcome": "transferred", "reason": "agent", "when": "insisted on a human (G.4)", "fact_ids": ["M-CODE", "M-POL-G4"]},
        {"outcome": "transferred", "reason": "care", "when": "hardship, accepted care team (F.5)", "fact_ids": ["M-CODE", "M-POL-F5"]},
        {"outcome": "no_promise", "reason": "refused", "when": "attempts used up or twice did not want to talk (F.4, G.7)", "fact_ids": ["M-CODE", "M-POL-F4", "M-POL-G7"]},
        {"outcome": "no_promise", "reason": "hardship", "when": "hardship, declined care team (F.5)", "fact_ids": ["M-CODE", "M-POL-F5"]},
        {"outcome": "no_promise", "reason": "disputed", "when": "dispute (G.2)", "fact_ids": ["M-CODE", "M-POL-G2"]},
        {"outcome": "no_promise", "reason": "service_error", "when": "create_promise failed twice (H.4)", "fact_ids": ["M-CODE", "M-POL-H4"]},
        {"outcome": "not_verified", "reason": "failed", "when": "three wrong answers (B.2)", "fact_ids": ["M-CODE", "M-POL-B2"]},
        {"outcome": "not_verified", "reason": "declined", "when": "declined the questions (B.3) or twice did not want to talk before verification (G.7)", "fact_ids": ["M-CODE", "M-POL-B3"]},
        {"outcome": "not_reached", "reason": "callback", "when": "callback booked (A.2)", "fact_ids": ["M-CODE", "M-POL-A2"]},
        {"outcome": "not_reached", "reason": "no_callback", "when": "no callback possible (A.3)", "fact_ids": ["M-CODE", "M-POL-A3"]},
        {"outcome": "not_reached", "reason": "wrong_number", "when": "wrong number (A.4)", "fact_ids": ["M-CODE", "M-POL-A4"]},
        {"outcome": "not_reached", "reason": "deceased", "when": "customer deceased (A.5)", "fact_ids": ["M-CODE", "M-POL-A5"]},
        {"outcome": "not_reached", "reason": "unclear", "when": "unclear after two asks", "fact_ids": ["M-CODE", "M-MAIL"]},
    ],
    "aggregation": {"promise_wins": b(True, "M-POL-I1"), "transfer_wins_over_promise": b(True, "M-POL-I1"), "all_noted_as": [], "else_rule": s("", "M-POL-I1")},
    "note_tool_used": b(False, "M-POL-I1"),
}
G["required_phrases"] = [
    phrase("Am I speaking with {salutation} {family_name}?", "opening confirm question", "opening", "M-MAIL"),
    phrase("Please accept my condolences.", "a third party says the customer has died", "third_party", "M-POL-A5"),
    phrase("Could you settle this amount today?", "first question after stating what is owed", "negotiation", "M-POL-F1"),
    phrase("Is that correct?", "after reading the promise back", "confirmation", "M-POL-H1"),
    phrase("We will send you an SMS confirming this arrangement.", "after create_promise returned ok", "recording", "M-POL-H5"),
]
G["behaviour_rules"] = [
    rule("Do not say arrears, overdue, payment or the product before identity is verified, to anyone, relatives included.", "global", "M-MAIL"),
    rule("With someone else on the line say only the opening sentence and ask when the customer can be reached.", "third_party", "M-POL-A1"),
    rule("A relative or partner may not answer the security questions and may not be told anything about the account.", "third_party", "M-POL-A6"),
    rule("After three wrong answers do not state the arrears; tell the customer to call the service line or visit a branch.", "identity", "M-POL-B2"),
    rule("If the customer does not want to answer, explain once that the questions protect their account; asking what the call is about counts as declining.", "identity", "M-POL-B3"),
    rule("Say you are calling from the collections department about an overdue payment; name the product in words; state the overdue amount and the days overdue.", "debt_statement", "M-POL-C2"),
    rule("A promise date must be today or later, a business day, and not after the deadline.", "negotiation", "M-POL-D2"),
    rule("If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day.", "negotiation", "M-POL-D3"),
    rule("If the customer gives a vague period, ask once for the exact day; if they still give none, propose the deadline.", "negotiation", "M-POL-D4"),
    rule("Next <weekday> means that weekday in the following calendar week; this <weekday> means the one in the current week.", "negotiation", "M-POL-D5"),
    rule("If the customer asks for a date after the deadline, say the latest date that can be recorded is the deadline and offer it; refusing it is a flat refusal.", "negotiation", "M-POL-D6"),
    rule("Ask for the full overdue amount first; never ask how much the customer can pay; propose every amount.", "negotiation", "M-POL-E1"),
    rule("If the full amount is too much, offer the floor once and say the remainder stays overdue; refusing the floor is a flat refusal.", "negotiation", "M-POL-E3"),
    rule("Accept any amount from the floor to the full amount, both included; below the floor say it cannot be recorded and offer the floor once.", "negotiation", "M-POL-E4"),
    rule("A date or an amount proposed by the customer is never a refusal.", "negotiation", "M-POL-F2"),
    rule("A flat refusal or a non-answer uses one persuasion attempt; a no to paying today with no date and no amount is a flat refusal.", "negotiation", "M-POL-F3"),
    rule("When the attempts are used up, stop; never repeat an offer the customer has already refused.", "negotiation", "M-POL-F4"),
    rule("On illness, bereavement or job loss: one short sentence of sympathy, no persuasion attempt, offer the customer care team; still record a promise if the customer names a date or amount.", "special", "M-POL-F5"),
    rule("Never offer a discount, a fee waiver, a payment plan or any term not in the policy.", "global", "M-POL-F6"),
    rule("Already paid: say payments can take one business day to show and take no promise.", "special", "M-POL-G1"),
    rule("Dispute: do not argue and take no promise; a product said to be closed or settled in the past is a dispute.", "special", "M-POL-G2"),
    rule("Payment plan request: do not describe any plan; transfer to payment_plans.", "special", "M-POL-G3"),
    rule("Request for a human: ask once whether you can help first; if the customer insists, transfer to agents.", "special", "M-POL-G4"),
    rule("Is this a scam: say the customer can check by calling the number on the back of their card, and continue.", "global", "M-POL-G5"),
    rule("For a question you cannot answer from the tools, say you do not have that information; never invent figures, dates or reasons.", "global", "M-POL-G6"),
    rule("If the customer says twice that they do not want to talk, end the call.", "global", "M-POL-G7"),
    rule("Read the product, amount and date back and ask for confirmation; record only after a clear yes.", "confirmation", "M-POL-H1"),
    rule("If the customer changes the date or amount at the read-back, check the new value and read it back again.", "confirmation", "M-POL-H2"),
    rule("A recorded promise cannot be changed or cancelled in the same call; if asked, say it can be changed in online banking.", "confirmation", "M-POL-H3"),
    rule("Say the promise is recorded only after create_promise returns ok true; if it fails, try once more; if it fails again say you could not record it.", "recording", "M-POL-H4"),
    rule("Thank the customer and say goodbye before close_call.", "closing", "M-MAIL"),
]
G["unresolved"] = []
G["date_conditional"] = [
    {"field_path": "third_party.callback.to_time", "effective_from": "2026-10-01", "value": "\"17:00\"", "fact_ids": ["M-MEMO-1", "M-POL-A2"]},
]

if __name__ == "__main__":
    model = Spec.model_validate(G)
    path = os.path.join(HERE, "gold.spec.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model.model_dump(), f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote", path)
