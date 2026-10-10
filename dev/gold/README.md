# Gold specs (dev material, never read by the builder)

`make_gold.py` writes `brief-a.spec.json` (Brief A) and `brief-ab.spec.json` (A+B) in the `builder/schema.py` format.
Fact ids: `A-R<n>` = Brief A rule n, `A-S<n>` = Brief A section n text, `B-<n>` = Brief B item n, `B-C` = Brief B closing.

## Coverage, Brief A

| Rule | Spec field(s) |
|---|---|
| S2 call variables | `call_variables`, `roles` |
| 1 | `opening.required_elements`, `opening.forbidden_before_identity` |
| 2 | `opening.confirm_question`, `required_phrases` |
| 3 | `opening.accept_examples`, `nonconfirm_examples`, `max_confirm_asks`, `answer_question_then_count_as_ask`, `unclear_close` |
| 4 | `opening.robot_question_reply`, special intent `robot_question` |
| 5 | `third_party.say_only_opening`, `ask_when_reachable` |
| 6 | `third_party.callback`, `callback_close` |
| 7 | `third_party.callback.ask_again_times`, `no_callback_close` |
| 8 | `third_party.wrong_number_close` |
| 9 | `third_party.deceased_sentence`, `deceased_ask_nothing_else`, `deceased_close` |
| 10 | `third_party.relative_cannot_verify`, behaviour rule |
| 11 | `identity.questions` (order, `answer_format`, `numeric_date_order`), `one_at_a_time`, `calendar.numeric_date_order` |
| 12 | `identity.max_wrong_total`, `wrong_may_retry` |
| 13 | `identity.swapped` |
| 14 | `identity.fail_message`, `fail_close`, `do_not_state_debt_on_fail` |
| 15 | `identity.decline`, `decline_close` |
| 16 | `debt_statement.account_tool_after_identity` |
| 17 | `debt_statement.intro_instruction`, `product_labels`, `include` |
| S7 holidays | `calendar.business_weekdays`, `holidays` |
| 18 | `bands`, `calendar.deadline_rule` |
| 19 | generator invariant (today ≤ date ≤ deadline, business day) |
| 20 | `negotiation.nonbusiness_date` |
| 21 | `negotiation.vague` |
| 22 | `calendar.next_weekday`, `this_weekday` |
| 23 | `negotiation.after_deadline` |
| 24 | `amounts.ask_full_first`, `never_ask_how_much`, `agent_proposes_every_amount` |
| 25 | `amounts.floor_field_by_type` |
| 26 | `amounts.too_much`, `refuse_floor_is_flat_refusal`; attempt 2 |
| 27 | `amounts.accept_range`, `below_floor` |
| 28 | `negotiation.first_question`, `required_phrases` |
| 29 | `negotiation.proposal_is_not_refusal` |
| 30 | `negotiation.attempts`, `no_to_today_without_terms_is_refusal`, `no_answer_is_refusal` |
| 31 | `negotiation.no_repeat_refused_offer`, `exhausted_close` |
| 32 | special intent `hardship` (say, ask once, transfer support, decline close) |
| 33 | `negotiation.forbidden_offers`, behaviour rule |
| 34 | `confirmation.readback_elements`, `confirm_question`, `record_only_after_clear_yes` |
| 35 | `confirmation.recheck_on_change` |
| 36 | `confirmation.one_promise_per_product`, `change_after_record_text` |
| 37 | `recording.max_attempts`, `say_recorded_only_on_ok`, `failure_say`, `failure_close` |
| 38 | `recording.success_sentence`, `required_phrases` |
| 39 | special intent `already_paid` |
| 40 | special intent `dispute` |
| 41 | special intent `wants_plan` |
| 42 | special intent `wants_human` (allowed before identity) |
| 43 | special intent `scam_question` |
| 44 | behaviour rule (global) |
| 45 | special intent `not_talk` (before-identity close), `wants_human.allowed_before_identity` |
| 46 | `closing.outcome_table`, `exactly_one_close`, `close_is_last_tool_call`, `aggregation.transfer_wins_over_promise`, `note_tool_used` |
| 47 | `closing.goodbye_before_close` |

## Coverage, Brief B (on top of A)

| Item | Spec field(s) |
|---|---|
| 1 | `multi_product.enabled`, `max_products` |
| 2 | `multi_product.state_all_first`, behaviour rule |
| 3 | `bands` (per product, generator) |
| 4 | `multi_product.ask_all_today_first`, `order`, `attempts_restart_per_product`, behaviour rule |
| 5 | `multi_product.per_product_attempts` |
| 6 | `multi_product.date_over_deadline_use_product_deadline_and_say_so` |
| 7 | `multi_product.single_combined_readback` |
| 8 | `multi_product.note_unpromised_products`, `note_reasons`, `closing.note_tool_used` |
| 9 | `multi_product.single_product_dispute_or_paid_continues`; intents `already_paid`/`dispute` with `continue_other_products` and note reasons |
| 10 | `multi_product.notes_on_transfer`, `unrecorded_on_transfer_are_dropped`, `recorded_before_transfer_stay` |
| 11 | `recording.failure_note_reason` |
| closing | `closing.aggregation.all_noted_as`, `else_rule`, `promise_wins` |

Note: the structured-output size check of the schema (T2.1 AC) needs `ANTHROPIC_API_KEY`; Track B runs it. `check_schema()` gives the local numbers.
