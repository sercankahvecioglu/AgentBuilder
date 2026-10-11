# Gold specs (DEV_PLAN T2.2)

Hand-written target output of the Extract stage for Brief A and Brief A+B, in the `builder/schema.py` `Spec` contract (DEV_PLAN §2.3).

- `brief-a.spec.json`: Brief A alone (`multi_product.enabled = false`).
- `brief-ab.spec.json`: Brief A with Brief B applied.
- `make_gold.py` builds both files and validates them against `Spec`. Edit the script, not the JSON.
- `coverage.py` prints the table below from the JSON.
- `../eval_extract.py` compares an extracted spec with a gold spec.

Fact id convention in `fact_ids`: `A-R<n>` = Brief A rule n, `A-S<n>` = Brief A section n prose or table
(S1 the job, S2 call variables, S7 business days and holidays, S12 outcome table), `B-<n>` = Brief B item n,
`B-CLOSE` = Brief B closing paragraph, `IMPL` = implied by the document (language).

Conventions worth knowing for Track A:
- Every leaf is `{value, fact_ids}` (`S`/`I`/`B`), `{values, fact_ids}` (`L`) or `{outcome, reason, fact_ids}` (`Close`). A `reason` of `""` means the outcome table lists none (C7: no `reason` leaf in the close body).
- `negotiation.attempts[].amount`: `full | floor | floor_if_full_refused`; `.date`: `last_business_day_this_week | deadline`; `.if_today_is_that_day`: `last_business_day_next_week`; `bands_allowed = []` means every band.
- `special_intents[]`: `action_kind` `none | transfer | note`; `close_outcome = ""` plus `continue_call = true` means answer and continue (C12 answer-and-continue); `count_before_action = 2` means "says it twice"; `before_identity_close_*` overrides the close before identity is verified; `declined_close_*` is the close when the customer declines the offered action (`ask_once_first`), `""` meaning the call continues.
- `multi_product`: when `enabled` is false the other leaves are placeholders and the eval ignores them.
- `closing.aggregation.all_noted_as`: `[{reason: paid, outcome: paid}]` in B; `else_rule = first_non_paid_note_reason_in_order`.
- `calendar.date_source = now`: all date math from the `now` call variable, never the real clock.
- `behaviour_rules` are the prompt-side instructions; code-relevant values never live only there.

## Rule coverage

### Brief A → `brief-a.spec.json`

| Rule | Spec fields (dotted paths; `behaviour_rules[...]` = prompt instruction) |
|---|---|
| A-S1 | `bank_name`, `multi_product.enabled`, `multi_product.max_products`, `multi_product.state_all_first`, `multi_product.per_product_deadline`, `multi_product.ask_all_today_first`, `multi_product.ask_today_once`, `multi_product.per_product_attempts`, `multi_product.attempts_restart_per_product`, `multi_product.single_combined_readback`, `multi_product.order`, `multi_product.date_over_deadline_use_product_deadline_and_say_so`, `multi_product.unrecorded_on_transfer_are_dropped`, `multi_product.single_product_dispute_or_paid_continues` |
| A-S2 | `call_variables[customer_id]`, `call_variables[first_name]`, `call_variables[last_name]`, `call_variables[title]`, `call_variables[now]`, `roles.customer_id_var`, `roles.now_var`, `roles.address_form`, `calendar.date_source` |
| A-S7 | `calendar.business_weekdays`, `calendar.holidays` |
| A-S12 | `recording.failure_note_reason`, `multi_product.note_unpromised_products`, `multi_product.note_even_when_no_promise`, `multi_product.note_reasons`, `multi_product.notes_on_transfer`, `multi_product.recorded_before_transfer_stay`, `closing.outcome_table[promise/-]`, `closing.outcome_table[paid/-]`, `closing.outcome_table[transferred/restructuring]`, `closing.outcome_table[transferred/human]`, `closing.outcome_table[transferred/support]`, `closing.outcome_table[no_promise/refused]`, `closing.outcome_table[no_promise/hardship]`, `closing.outcome_table[no_promise/dispute]`, `closing.outcome_table[no_promise/service_error]`, `closing.outcome_table[not_verified/failed]`, `closing.outcome_table[not_verified/declined]`, `closing.outcome_table[not_reached/callback]`, `closing.outcome_table[not_reached/no_callback]`, `closing.outcome_table[not_reached/wrong_number]`, `closing.outcome_table[not_reached/deceased]`, `closing.outcome_table[not_reached/unclear]`, `closing.aggregation.promise_wins`, `closing.aggregation.transfer_wins_over_promise`, `closing.aggregation.else_rule`, `closing.note_tool_used` |
| A-R1 | `agent_self_description`, `opening.required_elements`, `opening.first_sentence`, `opening.forbidden_before_identity`, `third_party.say_only_opening` + 1 behaviour rule(s) |
| A-R2 | `opening.confirm_question`, `required_phrases[0]` |
| A-R3 | `opening.accept_examples`, `opening.nonconfirm_examples`, `opening.max_confirm_asks`, `opening.answer_question_then_count_as_ask`, `opening.unclear_close`, `closing.outcome_table[not_reached/unclear]` |
| A-R4 | `opening.robot_question_reply`, `special_intents[robot_question]` + 1 behaviour rule(s) |
| A-R5 | `third_party.say_only_opening`, `third_party.ask_when_reachable` + 1 behaviour rule(s) |
| A-R6 | `third_party.callback.allowed_days`, `third_party.callback.from_time`, `third_party.callback.to_time`, `third_party.callback.inclusive`, `third_party.callback.after_now`, `third_party.callback_close`, `closing.outcome_table[not_reached/callback]` |
| A-R7 | `third_party.callback.ask_again_times`, `third_party.no_callback_close`, `closing.outcome_table[not_reached/no_callback]` |
| A-R8 | `third_party.wrong_number_close`, `closing.outcome_table[not_reached/wrong_number]` |
| A-R9 | `third_party.deceased_close`, `third_party.deceased_sentence`, `third_party.deceased_ask_nothing_else`, `closing.outcome_table[not_reached/deceased]`, `required_phrases[1]` |
| A-R10 | `third_party.relative_cannot_verify` + 1 behaviour rule(s) |
| A-R11 | `identity.questions[date_of_birth]`, `identity.questions[phone_last4]`, `identity.one_at_a_time`, `calendar.numeric_date_order` + 1 behaviour rule(s) |
| A-R12 | `identity.max_wrong_total`, `identity.wrong_may_retry` |
| A-R13 | `identity.swapped.hint_value`, `identity.swapped.instruction`, `identity.swapped.counts_as_wrong` + 1 behaviour rule(s) |
| A-R14 | `identity.fail_message`, `identity.fail_close`, `identity.do_not_state_debt_on_fail`, `closing.outcome_table[not_verified/failed]` + 1 behaviour rule(s) |
| A-R15 | `identity.decline.explain_once_text`, `identity.decline.max_declines`, `identity.decline.purpose_question_counts`, `identity.decline_close`, `closing.outcome_table[not_verified/declined]` + 1 behaviour rule(s) |
| A-R16 | `debt_statement.account_tool_after_identity` |
| A-R17 | `debt_statement.intro_instruction`, `debt_statement.product_labels[credit_card]`, `debt_statement.product_labels[personal_loan]`, `debt_statement.product_labels[car_loan]`, `debt_statement.include` + 1 behaviour rule(s) |
| A-R18 | `calendar.deadline_rule.kind`, `calendar.deadline_rule.n_from_band`, `bands[early]`, `bands[late]` |
| A-R19 | `negotiation.promise_date.not_before`, `negotiation.promise_date.business_day_only`, `negotiation.promise_date.not_after` + 1 behaviour rule(s) |
| A-R20 | `negotiation.nonbusiness_date.offer_next_business_day` + 1 behaviour rule(s) |
| A-R21 | `negotiation.vague.ask_once`, `negotiation.vague.then` + 1 behaviour rule(s) |
| A-R22 | `calendar.next_weekday`, `calendar.this_weekday` + 1 behaviour rule(s) |
| A-R23 | `negotiation.after_deadline.offer_deadline`, `negotiation.after_deadline.refusing_deadline_is_flat_refusal` + 1 behaviour rule(s) |
| A-R24 | `amounts.ask_full_first`, `amounts.never_ask_how_much`, `amounts.agent_proposes_every_amount` + 1 behaviour rule(s) |
| A-R25 | `amounts.floor_field_by_type[credit_card]`, `amounts.floor_field_by_type[personal_loan]`, `amounts.floor_field_by_type[car_loan]` |
| A-R26 | `amounts.too_much.offer_floor_once`, `amounts.too_much.say_rest_overdue`, `amounts.refuse_floor_is_flat_refusal`, `negotiation.attempts[n2]` + 1 behaviour rule(s) |
| A-R27 | `amounts.accept_range.min`, `amounts.accept_range.max`, `amounts.accept_range.inclusive`, `amounts.below_floor.say_cannot_record`, `amounts.below_floor.offer_floor_once`, `amounts.refuse_floor_is_flat_refusal` + 1 behaviour rule(s) |
| A-R28 | `negotiation.first_question`, `required_phrases[2]` |
| A-R29 | `negotiation.proposal_is_not_refusal` + 1 behaviour rule(s) |
| A-R30 | `negotiation.attempts[n1]`, `negotiation.attempts[n2]`, `negotiation.no_to_today_without_terms_is_refusal`, `negotiation.no_answer_is_refusal` + 1 behaviour rule(s) |
| A-R31 | `negotiation.no_repeat_refused_offer`, `negotiation.exhausted_close`, `closing.outcome_table[no_promise/refused]` + 1 behaviour rule(s) |
| A-R32 | `special_intents[hardship]`, `closing.outcome_table[transferred/support]`, `closing.outcome_table[no_promise/hardship]` + 1 behaviour rule(s) |
| A-R33 | `negotiation.forbidden_offers` + 1 behaviour rule(s) |
| A-R34 | `confirmation.readback_elements`, `confirmation.confirm_question`, `confirmation.record_only_after_clear_yes`, `required_phrases[3]` + 1 behaviour rule(s) |
| A-R35 | `confirmation.recheck_on_change` + 1 behaviour rule(s) |
| A-R36 | `confirmation.one_promise_per_product`, `confirmation.change_after_record_text` + 1 behaviour rule(s) |
| A-R37 | `recording.max_attempts`, `recording.say_recorded_only_on_ok`, `recording.failure_say`, `recording.failure_close`, `closing.outcome_table[no_promise/service_error]` + 1 behaviour rule(s) |
| A-R38 | `recording.success_sentence`, `required_phrases[4]` |
| A-R39 | `special_intents[already_paid]`, `closing.outcome_table[paid/-]` + 1 behaviour rule(s) |
| A-R40 | `special_intents[dispute]`, `closing.outcome_table[no_promise/dispute]` + 1 behaviour rule(s) |
| A-R41 | `special_intents[wants_plan]`, `closing.outcome_table[transferred/restructuring]` + 1 behaviour rule(s) |
| A-R42 | `special_intents[wants_human]`, `closing.outcome_table[transferred/human]` + 1 behaviour rule(s) |
| A-R43 | `special_intents[scam_question]` + 1 behaviour rule(s) |
| A-R44 | `special_intents[unknown_question]` + 1 behaviour rule(s) |
| A-R45 | `special_intents[wants_human]`, `special_intents[not_talk]`, `closing.outcome_table[no_promise/refused]` + 1 behaviour rule(s) |
| A-R46 | `closing.exactly_one_close`, `closing.close_is_last_tool_call` |
| A-R47 | `closing.goodbye_before_close` + 1 behaviour rule(s) |

### Brief B → `brief-ab.spec.json` (B items only; A rules map as above)

| Rule | Spec fields (dotted paths; `behaviour_rules[...]` = prompt instruction) |
|---|---|
| B-1 | `multi_product.enabled`, `multi_product.max_products` |
| B-2 | `multi_product.state_all_first` + 1 behaviour rule(s) |
| B-3 | `multi_product.per_product_deadline` |
| B-4 | `multi_product.ask_all_today_first`, `multi_product.ask_today_once`, `multi_product.attempts_restart_per_product`, `multi_product.order` + 1 behaviour rule(s) |
| B-5 | `multi_product.per_product_attempts` |
| B-6 | `multi_product.date_over_deadline_use_product_deadline_and_say_so` + 1 behaviour rule(s) |
| B-7 | `multi_product.single_combined_readback` + 1 behaviour rule(s) |
| B-8 | `special_intents[hardship]`, `multi_product.note_unpromised_products`, `multi_product.note_even_when_no_promise`, `multi_product.note_reasons`, `closing.note_tool_used` |
| B-9 | `special_intents[already_paid]`, `special_intents[dispute]`, `multi_product.single_product_dispute_or_paid_continues` + 1 behaviour rule(s) |
| B-10 | `special_intents[wants_plan]`, `multi_product.notes_on_transfer`, `multi_product.unrecorded_on_transfer_are_dropped`, `multi_product.recorded_before_transfer_stay`, `closing.aggregation.transfer_wins_over_promise` + 1 behaviour rule(s) |
| B-11 | `recording.failure_note_reason` + 1 behaviour rule(s) |
| B-CLOSE | `closing.aggregation.promise_wins`, `closing.aggregation.all_noted_as[0]`, `closing.aggregation.else_rule` |
