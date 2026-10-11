"""Data contracts for the builder (DEV_PLAN §2.3): Fact, Conflict, Spec.

Design rules
- Every spec leaf carries `fact_ids` (provenance). Leaves are wrapped in the small
  value models `S` (string), `I` (int), `B` (bool), `L` (list of strings) and
  `Close` (outcome + reason). Lists of objects are used instead of free-form dicts.
- Use "" rather than null: the structured-output schema requires every field.
- No field is named after a concept that exists only in one brief. New
  concepts go to `behaviour_rules` (free-text agent instructions) or are added
  generically.
- The JSON Schema must compile under the structured-output limits: no
  recursion, no numeric/string constraints, `additionalProperties: false`.
  `strict_schema()` returns the schema in that form; `check_schema()` sanity-
  checks depth and size locally before a real call is made.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """Base model: forbid unknown keys so a mis-named field fails loudly."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Stage 1a: facts and conflicts
# --------------------------------------------------------------------------

FactKind = Literal["decision", "discussion", "definition", "code_list_entry"]
Stage = Literal[
    "opening",
    "third_party",
    "identity",
    "debt_statement",
    "negotiation",
    "confirmation",
    "recording",
    "special",
    "closing",
    "global",
]


class Fact(Strict):
    id: str = Field(description="Short unique id, e.g. F017.")
    text: str = Field(description="One atomic, checkable statement in plain English.")
    agent_instruction: str = Field(
        description="What the phone agent must do, in plain English; '' if the fact is not agent-facing."
    )
    source_quote: str = Field(description="Verbatim quote from the input that supports the fact.")
    doc_label: str = Field(description="Which input document the quote comes from (file name or heading).")
    doc_date: str = Field(description="Date of that document as ISO YYYY-MM-DD, or '' if unknown.")
    effective_from: str = Field(
        description="ISO date from which the rule applies, or '' if it applies from the start."
    )
    kind: FactKind = Field(
        description="decision = a rule that governs; discussion = a question, proposal or opinion that decides nothing; definition = a term; code_list_entry = an allowed code or value."
    )
    stage: Stage
    topic: str = Field(description="Short topic key used to group related facts, e.g. 'callback_window'.")
    scope: str = Field(description="What it applies to: all products, a product type, a situation; '' if general.")
    conditions: str = Field(description="When it applies; '' if unconditional.")
    exceptions: str = Field(description="When it does not apply; '' if none.")
    operator: str = Field(
        description="Comparison or relation if the fact carries one: '<=', '>=', '==', 'between', 'before', 'after', 'nth_business_day', ''."
    )
    value: str = Field(description="The number, date, time, code or phrase the fact fixes; '' if none.")
    value_kind: Literal["parameter", "set_member", "none"] = Field(
        description="parameter = a single setting that can hold only one value (a limit, a count, a time, a deadline); "
        "set_member = one item of a list that may hold several (one holiday, one accepted phrase, one code, one product type); "
        "none = no value."
    )


class Conflict(Strict):
    topic: str
    fact_ids: list[str] = Field(description="Ids of the facts that disagree.")
    note: str = Field(description="What they disagree on. Do not resolve it.")


DocKind = Literal["policy", "amendment", "request", "code_list", "discussion", "other"]


class Document(Strict):
    label: str = Field(description="The document's name attribute or heading, exactly as used in the facts' doc_label.")
    date: str = Field(description="ISO date of the document, or '' if none is given.")
    kind: DocKind = Field(
        description="policy = the base rules; amendment = a memo, update or later brief that changes another document; "
        "request = a mail or note commissioning the agent; code_list = allowed codes; discussion = a thread that decides nothing; other."
    )
    amends: str = Field(description="Label of the document this one changes or builds on, when the text says so (\"builds on\", \"replaces\", \"update to\", \"applies unless a rule below replaces it\"); '' otherwise.")
    note: str = Field(description="One line on what the document is.")


class Extraction(Strict):
    """Stage 1a output."""

    documents: list[Document] = Field(description="One entry per input document, in reading order.")
    facts: list[Fact]
    conflicts: list[Conflict]


# --------------------------------------------------------------------------
# Spec leaves
# --------------------------------------------------------------------------


class S(Strict):
    value: str
    fact_ids: list[str]


class I(Strict):
    value: int
    fact_ids: list[str]


class B(Strict):
    value: bool
    fact_ids: list[str]


class L(Strict):
    values: list[str]
    fact_ids: list[str]


class Close(Strict):
    outcome: str = Field(description="A close_call outcome from the tool API enum.")
    reason: str = Field(description="The reason from the brief's outcome table, or '' when the table lists none.")
    fact_ids: list[str]


# --------------------------------------------------------------------------
# Spec sections
# --------------------------------------------------------------------------


class CallVariable(Strict):
    name: str
    meaning: str
    fact_ids: list[str]


class Roles(Strict):
    customer_id_var: S = Field(description="Call variable passed to every tool call.")
    now_var: S = Field(description="Call variable holding the current date and time.")
    address_form: S = Field(
        description="How to address the customer, as a template over call variables, e.g. '{title} {last_name}'."
    )


class Opening(Strict):
    required_elements: L = Field(description="What the first sentence must contain.")
    first_sentence: S = Field(description="A ready-to-speak first sentence in the first person that contains every required element, using the brief's own words.")
    forbidden_before_identity: L = Field(description="Words or topics not to mention before identity is verified.")
    confirm_question: S = Field(description="The question that asks whether the right person is on the line (template).")
    accept_examples: L = Field(description="Replies that count as confirmation.")
    nonconfirm_examples: L = Field(description="Replies that do not count.")
    max_confirm_asks: I = Field(description="How many times to ask before closing as unclear.")
    answer_question_then_count_as_ask: B = Field(
        description="A customer question is answered first; the ask that follows counts as the next ask."
    )
    unclear_close: Close
    robot_question_reply: S = Field(description="What to say if asked whether this is a robot or AI; '' if not specified.")


class CallbackWindow(Strict):
    allowed_days: L = Field(description="Generic day keys, e.g. today, next_business_day.")
    from_time: S = Field(description="HH:MM")
    to_time: S = Field(description="HH:MM")
    inclusive: B
    after_now: B
    ask_again_times: I = Field(description="How many times to ask for another time when the offer is outside the window.")


class ThirdParty(Strict):
    say_only_opening: B = Field(description="Say nothing beyond the opening sentence; never the reason for the call.")
    ask_when_reachable: B
    callback: CallbackWindow
    callback_close: Close
    no_callback_close: Close
    wrong_number_close: Close
    deceased_close: Close
    deceased_sentence: S
    deceased_ask_nothing_else: B
    relative_cannot_verify: B = Field(description="A relative may not answer security questions nor be told about the account.")


class IdentityQuestion(Strict):
    api_field: str = Field(description="Value of the verify_identity `field` enum in the tool API.")
    ask_text: str = Field(description="How to ask for it.")
    answer_format: str = Field(description="Format sent to the tool, e.g. 'YYYY-MM-DD' or 'four digits'.")
    numeric_date_order: str = Field(description="For dates given only as numbers: 'day_month_year', 'month_day_year' or ''.")
    fact_ids: list[str]


class Swapped(Strict):
    hint_value: S = Field(description="The hint value the identity tool returns when the date parts are swapped (from the tool API response enum); '' if none.")
    instruction: S = Field(description="What to ask the customer when the hint comes back.")
    counts_as_wrong: B


class Decline(Strict):
    explain_once_text: S = Field(description="The one-time explanation given when the customer does not want to answer.")
    max_declines: I = Field(description="How many declines close the call.")
    purpose_question_counts: B = Field(description="Asking what the call is about instead of answering counts as a decline.")


class Identity(Strict):
    questions: list[IdentityQuestion]
    one_at_a_time: B
    max_wrong_total: I
    wrong_may_retry: B
    swapped: Swapped
    decline: Decline
    fail_message: S = Field(description="What to say after the check failed.")
    fail_close: Close
    decline_close: Close
    do_not_state_debt_on_fail: B


class DeadlineRule(Strict):
    kind: S = Field(description="e.g. nth_business_day_after_today")
    n_from_band: B


class Calendar(Strict):
    business_weekdays: L = Field(description="Lower-case English weekday names.")
    holidays: L = Field(description="ISO dates.")
    deadline_rule: DeadlineRule
    next_weekday: S = Field(description="following_calendar_week | next_occurrence")
    this_weekday: S = Field(description="current_week | next_occurrence")
    numeric_date_order: S = Field(description="day_month_year | month_day_year")
    date_source: S = Field(description="Which variable all date rules use, e.g. the `now` call variable, never the real clock.")


class Band(Strict):
    label: str
    days_late_min: int
    days_late_max: int
    deadline_business_days: int
    persuasion_attempts: int
    fact_ids: list[str]


class ProductLabel(Strict):
    product_type: str = Field(description="Value of the product type enum in the tool API.")
    template: str = Field(description="How to name the product in words, with product fields in braces, e.g. 'mortgage ending {account_suffix}' or just 'overdraft'.")
    fact_ids: list[str]


class DebtStatement(Strict):
    intro_instruction: S
    intro_sentence: S = Field(description="A ready-to-speak sentence in the first person that introduces the debt statement (who is calling and why), using the brief's own words; '' if the brief prescribes none.")
    product_labels: list[ProductLabel]
    include: L = Field(description="Account fields to state, e.g. past_due, days_late.")
    account_tool_after_identity: B


class FloorField(Strict):
    product_type: str
    account_field: str
    fact_ids: list[str]


class AcceptRange(Strict):
    min: S = Field(description="floor")
    max: S = Field(description="full")
    inclusive: B


class TooMuch(Strict):
    offer_floor_once: B
    say_rest_overdue: B


class BelowFloor(Strict):
    say_cannot_record: B
    offer_floor_once: B


class Amounts(Strict):
    floor_field_by_type: list[FloorField]
    ask_full_first: B
    never_ask_how_much: B
    agent_proposes_every_amount: B
    accept_range: AcceptRange
    too_much: TooMuch
    below_floor: BelowFloor
    refuse_floor_is_flat_refusal: B


class Attempt(Strict):
    n: int
    amount: str = Field(description="full | floor | floor_if_full_refused")
    date: str = Field(description="last_business_day_this_week | deadline | next_business_day | ...")
    if_today_is_that_day: str = Field(description="What to propose instead, e.g. last_business_day_next_week; '' if n/a.")
    bands_allowed: list[str] = Field(description="Band labels this attempt exists for; empty = all bands.")
    fact_ids: list[str]


class Vague(Strict):
    ask_once: B
    then: S = Field(description="propose_deadline | ...")


class NonBusinessDate(Strict):
    offer_next_business_day: B


class AfterDeadline(Strict):
    offer_deadline: B
    refusing_deadline_is_flat_refusal: B


class PromiseDateRule(Strict):
    not_before: S = Field(description="Earliest promise date, e.g. today.")
    business_day_only: B
    not_after: S = Field(description="Latest promise date, e.g. deadline.")


class Negotiation(Strict):
    first_question: S
    promise_date: PromiseDateRule
    attempts: list[Attempt]
    proposal_is_not_refusal: B
    no_to_today_without_terms_is_refusal: B
    vague: Vague
    nonbusiness_date: NonBusinessDate
    after_deadline: AfterDeadline
    no_answer_is_refusal: B
    no_repeat_refused_offer: B
    exhausted_close: Close
    forbidden_offers: L


class SpecialIntent(Strict):
    key: str = Field(description="Snake-case key, e.g. already_paid, dispute, hardship, wants_plan, wants_human, scam_question, not_talk.")
    trigger_description: str
    allowed_before_identity: bool
    applies_to: str = Field(description="all | current_product | named_product")
    say_text: str = Field(description="Sentence or instruction; '' if nothing specific.")
    say_is_verbatim: bool
    ask_once_first: bool = Field(description="Ask once (e.g. 'can I help first?' or 'shall I connect you?') before acting.")
    ask_once_text: str = Field(description="What to ask or offer once when ask_once_first is true, as an instruction; '' otherwise.")
    action_kind: str = Field(description="none | transfer | note | callback")
    action_queue: str = Field(description="transfer queue from the tool API enum; '' if none.")
    action_note_reason: str = Field(description="add_note reason; '' if none.")
    count_before_action: int = Field(description="How many times the customer must say it before the action applies (1 = at once).")
    close_outcome: str = Field(description="'' if the call continues.")
    close_reason: str
    declined_close_outcome: str = Field(description="Close used when ask_once_first is true and the customer declines the offered action; '' = continue the call.")
    declined_close_reason: str
    before_identity_close_outcome: str = Field(description="Close used when it happens before identity; '' = same as close_outcome.")
    before_identity_close_reason: str
    continue_call: bool = Field(description="True if the agent answers and continues (no close).")
    continue_other_products: bool
    precedence: int = Field(description="Lower wins when several apply.")
    suppresses_persuasion: bool
    customer_named_terms_still_recorded: bool
    fact_ids: list[str]


class Confirmation(Strict):
    readback_elements: L
    confirm_question: S
    record_only_after_clear_yes: B
    recheck_on_change: B
    one_promise_per_product: B
    change_after_record_text: S


class Recording(Strict):
    max_attempts: I
    say_recorded_only_on_ok: B
    success_sentence: S = Field(description="Verbatim sentence to say after a recorded promise.")
    failure_say: S
    failure_close: Close
    failure_note_reason: S = Field(description="add_note reason on a failed write in multi-product mode; '' if n/a.")


class MultiProduct(Strict):
    enabled: B
    max_products: I
    state_all_first: B
    per_product_deadline: B
    ask_all_today_first: B
    ask_today_once: B = Field(description="Do not ask about paying today again for each product.")
    per_product_attempts: B
    attempts_restart_per_product: B
    single_combined_readback: B
    order: S = Field(description="as_returned")
    date_over_deadline_use_product_deadline_and_say_so: B
    note_unpromised_products: B
    note_even_when_no_promise: B
    note_reasons: L
    notes_on_transfer: B
    unrecorded_on_transfer_are_dropped: B
    recorded_before_transfer_stay: B
    single_product_dispute_or_paid_continues: B


class OutcomeRow(Strict):
    outcome: str
    reason: str = Field(description="'' when the table lists none.")
    when: str
    fact_ids: list[str]


class ReasonOutcome(Strict):
    reason: str
    outcome: str
    fact_ids: list[str]


class Aggregation(Strict):
    promise_wins: B
    transfer_wins_over_promise: B
    all_noted_as: list[ReasonOutcome] = Field(description="If every product is noted with this reason, close with this outcome.")
    else_rule: S = Field(description="e.g. first_non_paid_note_reason_in_order")


class Closing(Strict):
    goodbye_before_close: B
    exactly_one_close: B
    close_is_last_tool_call: B
    outcome_table: list[OutcomeRow]
    aggregation: Aggregation
    note_tool_used: B = Field(description="Whether add_note is used at all in this brief.")


class RequiredPhrase(Strict):
    text: str = Field(description="Verbatim.")
    when: str
    stage: Stage
    fact_ids: list[str]


class BehaviourRule(Strict):
    agent_instruction: str
    stage: Stage
    fact_ids: list[str]


class Unresolved(Strict):
    topic: str
    default_applied: str
    fact_ids: list[str]


class DateConditional(Strict):
    """A value that changes on a date (an amendment with `effective_from` later than some call dates)."""

    field_path: str = Field(description="Dotted path into the spec, e.g. calendar.holidays")
    effective_from: str = Field(description="ISO date")
    value: str = Field(description="JSON-encoded value that applies from that date.")
    fact_ids: list[str]


class Spec(Strict):
    bank_name: S
    language: S
    agent_self_description: S
    call_variables: list[CallVariable]
    roles: Roles
    opening: Opening
    third_party: ThirdParty
    identity: Identity
    calendar: Calendar
    bands: list[Band]
    debt_statement: DebtStatement
    amounts: Amounts
    negotiation: Negotiation
    special_intents: list[SpecialIntent]
    confirmation: Confirmation
    recording: Recording
    multi_product: MultiProduct
    closing: Closing
    required_phrases: list[RequiredPhrase]
    behaviour_rules: list[BehaviourRule]
    unresolved: list[Unresolved]
    date_conditional: list[DateConditional]


# --------------------------------------------------------------------------
# Schema helpers
# --------------------------------------------------------------------------


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema as sent to the API (the SDK's own transform: additionalProperties false, no unsupported constraints)."""
    from anthropic.lib._parse._transform import transform_schema  # type: ignore

    return transform_schema(model.model_json_schema())


def _depth(node: Any, d: int = 0) -> int:
    if isinstance(node, dict):
        return max([d] + [_depth(v, d + 1) for v in node.values()])
    if isinstance(node, list):
        return max([d] + [_depth(v, d + 1) for v in node])
    return d


def check_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Local sanity numbers for the structured-output schema: size, nesting, $defs, recursion."""
    schema = strict_schema(model)
    text = json.dumps(schema)
    defs = schema.get("$defs", {})
    # recursion check: a def that references itself (directly)
    recursive = [k for k, v in defs.items() if f'"#/$defs/{k}"' in json.dumps(v)]
    return {
        "model": model.__name__,
        "bytes": len(text),
        "defs": len(defs),
        "max_depth": _depth(schema),
        "recursive_defs": recursive,
    }


def load_spec(path: str) -> Spec:
    with open(path, encoding="utf-8") as f:
        return Spec.model_validate(json.load(f))


def dump_model(obj: BaseModel) -> str:
    return json.dumps(obj.model_dump(), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    for m in (Extraction, Spec):
        print(check_schema(m))
