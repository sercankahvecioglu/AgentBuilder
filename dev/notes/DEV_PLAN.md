# DEV_PLAN.md: step-by-step development plan for the builder (v2)

Audience: the coding agent(s) that implement the builder. Kit v3.
- v1 written 2026-10-10 22:30 UTC.
- v2 written 2026-10-10 23:00 UTC, after an adversarial review (18 findings, all addressed; see §9).

Read first, in this order:
1. `memory.md` (decisions D1-D23, corrections C1-C10)
2. this file
3. `DEV_GUIDE.md` (file map, gotchas with line refs)
4. `docs/workflow-format.md` (wf)
5. `docs/tools-and-code.md` (tc)
6. `docs/api.md`
7. `README.md`

> **Dev material. The builder must never read this file**, nor `memory.md`, `DEV_GUIDE.md` or `dev/`. Never rename any of them to `CLAUDE.md`/`AGENTS.md`.
> After Sun 17:00 UTC nothing from the hidden briefs may enter code, prompts, templates or these files. Crash fixes only.

Legend: **P0** = needed for a valid entry, **P1** = big score impact, **P2** = only if time is left.
Every task has acceptance criteria (**AC**).

---

## 0. Working rules

1. **Vertical slice first:** gold spec → generator → working Brief A agent → then extraction, B, and polish. Extraction is a parallel track that plugs into the same `spec.json` contract.
2. **Spike before you build on undocumented behaviour.** Record results in `memory.md` §3c "Verified platform facts".
3. **No brief content in builder code, templates or prompts.** Brief A/B values may appear only in `dev/` (gold specs, tests, mocks).
4. **Never relax a failing test to match the agent.** The oracle comes from the brief. A test that is wrong must be proven from the brief text and logged in `dev/issues.json`.
5. **Platform hygiene:**
   - Reuse slots: `base` already exists, plus `spike`, `brief-a`, `brief-ab`, `mock`, `final-1`, `final-2`.
   - Only one simulation at a time; no probing or load-testing.
   - Always run from the repo root (`save_workflow`'s state file is relative to the working directory).
6. **Python ≥ 3.10** (system default is 3.9): use the conda env `freyahackathon` or a venv. Pin `requirements.txt`.
7. **Secrets:** env vars only. Copy `.env.example` → `.env` (git-ignored). Never put keys in traces, outputs or commits. See T0.0: keys are already in git history.
8. **`dev/issues.json`:** each issue has a stable id, a status (open | tentatively-fixed | confirmed-fixed | regressed), evidence (call id, failed check, transcript excerpt) and a fix history. Re-run confirmed fixes every evaluation round.

---

## 1. Design corrections (summary; memory.md §3b has the short form)

**C1. Write guards.**
- A code node cannot block a tool the model calls; routing runs **before** the dialogue model on every user message (wf L13-36).
- Target design **G2**: a code node validates the agreed values held in variables, then an `api_request` node runs `create_promise` with baked values.
  - Numbers are sent with `{{x:json}}` (wf L196).
  - The model never fills `product_id`, `amount` or `date`.
- Fallback **G3**: a model tool, a strong prompt, `date_facts`, and a post-hook `what_to_do_next`. This is the kit's working-builder pattern; use it if spikes S3/S6 fail.
- G1 (aborting a pre-hook) is undocumented: P2 only.
- Never rewrite a URL to "block" a call. Calls to other services fail the case.

**C2. Dates.**
- The extraction `date` type anchors relative expressions on the extractor's notion of today, which is probably the real clock and not the call's `now`. Spike S3 confirms this; until then assume it.
- A date typed as `string` gets no anchor at all (wf L577).
- So extraction captures **parts** and code resolves them against `now` using the spec's semantics:
  - `day_ref` {today, tomorrow, day_after_tomorrow, weekday, day_of_month, vague, none}
  - `weekday` enum, `week_ref` {this, next, none}, `day_of_month` int, `month` enum, optional `year`
  - `vague_kind` {next_week, end_of_month, payday, other}
- When the customer accepts an **agent proposal** (`accepts_offer`), code takes the proposal's values, which code itself computed. Most promises happen this way.

**C3. Stale state.**
- Variables are never cleared (wf L178). Flattened tool keys such as `verify_identity_response.data.*` persist across nodes and products.
- Extraction reads recent messages, not only the last one (wf L28), so older turns can re-produce an intent.
- Rules:
  - Never route on raw flattened tool keys.
  - Post-hooks write **per-step** flags, e.g. `idq2_status`.
  - A code node resets the step's flags right before entering the step.
  - Extraction descriptions say "based only on the customer's latest message; use `none` if it says nothing about this".
  - Intent consumers reset the intent to `none`.
  - Spike S4 checks whether reset intents re-appear.

**C4.** Node prompts are templated from the facts' `agent_instruction`s. No LLM call at generate time.

**C5. Reproducibility.** Opus 5.5 has no temperature control. Use structured outputs, code-based conflict resolution, and optional 3-way voting (P1). Code-relevant fields get re-parsed from their quotes.

**C6.** `chat/message` may skip a first code node, so `initial_node` is a conversation node. Smoke tests stop before any tool call.

**C7. Closing.**
- Generate **one close `api_request` node per row of the brief's outcome table**, with literal `outcome`/`reason` body values and **no `reason` leaf** where the table has none. `wrap_up` (code) picks the row.
- Not C-a (a model tool with an unset `{{reason}}` exposes the field, so the model invents a value) and not C-c (an unresolved lifecycle parameter triggers an LLM fill; the base agent got `(None, None)` on PUB-08/10).
- The goodbye must come **before** `close_call` (Brief A rule 47). Spike S5 decides how:
  - (i) `on_enter` tts on the close node, if it is spoken before `pre_actions` run, or
  - (ii) the last conversation node says goodbye and the customer's reply triggers the close.
- `end_call` uses `message_mode: none`.

**C8.** The Freya unit-test API and chat fork are P2.

**C9.** The builder calls the Anthropic API directly with explicit inputs. It is not a file-system agent.

**C10.** Call variables (names, address form) come from the brief's call-variable table via the spec.

**C11. Routing rules for nodes where the model must call a tool:**
- No `always` or self-transition.
- Leave only on (a) per-step tool-result flags or (b) explicit exit enums whose values exclude the normal path. The normal answer must not trigger any transition, or the router leaves before the tool is called.

**C12. Interrupts.**
- Global nodes only fire when the current node has no matching transition (wf L395-402, L488). Every node with an `always` transition blocks them.
- Handle **answer-and-continue** interrupts in prompts: "are you a robot", "is this a scam", unknown questions, off-topic talk.
- Handle **action** interrupts with node exit enums routed to code: paid, dispute, hardship, plan request, human request, does not want to talk.
- Use `is_tool_call: true` global nodes only if a spike shows a clear benefit.

**C13. Turn caps.** `{{node.current_turns}}` resets on every transition (wf L237), and nodes re-entered through a code router never reach `max_node_turns`. Count turns in code where a cap matters, e.g. confirmation asks or decline counts.

**C14. Injecting constants into snippets.**
- Emit `CONST = json.loads(<python repr of json.dumps(obj, indent=1)>)`.
- Never inline JSON literals: `true`, `false` and `null` raise NameError and the try/except silently hides it.
- The `indent=1` keeps braces off the same line, so no `}}` appears (tc L494).
- Static tests assert **outputs**, not only that a snippet did not crash.

---

## 2. Target architecture

### 2.1 One builder run

```
python3 builder/build.py <input> [<input> ...] <tool_api.json> [--slot NAME] [--votes 1|3] [--skip-smoke] [--guard g2|g3]
  inputs: any text files (md, txt, eml, csv). Concatenated in order, each labelled with its file name.
  The last argument ending in .json/.yaml is the tool API.

1  load inputs; parse OpenAPI (servers[0].url, operations, body schemas, enums)
2  EXTRACT 1a   LLM → facts[] + conflicts[]                 (structured output)
3  RESOLVE      code → governing facts, overrides, date-conditional values, unresolved (+ stricter default)
4  EXTRACT 1b   LLM → spec (filled only from governing facts; every leaf cites fact ids)
   (--votes 3: steps 2-4 run 3× in parallel → field-wise majority; disputes logged)
5  VERIFY       code checks (+ LLM sentence coverage, P1) → on errors one re-extract with feedback
6  GENERATE     code only: tools from OpenAPI, skeleton graph, snippet templates, hooks, templated prompts
7  STATIC TEST  local exec of snippets/hooks, invariants, fact examples, workflow lint, freya dry-run
8  SAVE         freya.save_workflow(slot) (+ one update after a first create)
9  SMOKE        chat/message: opening + first identity question only (no tool calls)
10 EXPORT       freya.export_workflow → submission/<slot>.workflow.json
11 TRACE        submission/<slot>.trace.txt (written incrementally from step 1; secrets redacted)
```

**Time guard:** no hard abort. If the elapsed time passes 20 minutes, skip voting and the smoke test and log the skip. The build must always end with a saved agent.

**Exit code:** non-zero only if no agent was saved. Failed verifications and failed tests are recorded as warnings in the trace.

### 2.2 Repo layout

```
builder/        build.py trace.py llm.py inputs.py schema.py extract.py resolve.py verify.py
                openapi_tools.py generate.py static_tests.py smoke.py freya_io.py
                templates/snippets/*.py.tmpl  templates/prompts/*.txt
dev/            gold/  mock_briefs/  cases/  spikes/  eval_extract.py  audit_grep.py  baselines.md  issues.json
out/            working artifacts (facts, spec, workflow) - git-ignored
submission/     final exports + traces (tracked; note .gitignore ignores traces/ and results/)
requirements.txt
```

### 2.3 Data contracts

**Fact** (1a):

| Field | Values |
|---|---|
| `id` | |
| `text` | |
| `agent_instruction` | `""` if not agent-facing |
| `source_quote` | verbatim |
| `doc_label` | |
| `doc_date` | |
| `effective_from` | |
| `kind` | `decision` \| `discussion` \| `definition` \| `code_list_entry` |
| `stage` | `opening` \| `third_party` \| `identity` \| `debt_statement` \| `negotiation` \| `confirmation` \| `recording` \| `special` \| `closing` \| `global` |
| `topic` | |
| `scope` | |
| `conditions` | |
| `exceptions` | |
| `operator` | |
| `value` | |

Use `""` rather than null where the structured-output schema requires it.

**Conflict:** `topic`, `fact_ids[]`, `note`. The LLM lists conflicts and never resolves them.

**Resolution** (`resolve.py`, deterministic):
1. Discussion never governs.
2. The later `doc_date` wins. `effective_from` that lies after some call dates gives a date-conditional value, picked by code at runtime from `now`.
3. An amendment or memo beats a policy extract of an equal or unknown date.
4. Otherwise the conflict is unresolved: apply the **stricter** rule as the default and log it.

**Spec:** every leaf carries `fact_ids`. Only closed, executable parameters plus free-text instructions. If a value is unknown, use the stricter default and log it.
- `bank_name`, `language`, `agent_self_description`
- `call_variables[]` {name, meaning}
- roles: `customer_id_var`, `now_var`, `address_form` (template over call variables)
- `opening`
  - `required_elements[]`, `forbidden_before_identity[]`
  - `accept_examples[]`, `nonconfirm_examples[]`
  - `max_confirm_asks` (int), `answer_question_then_count_as_ask` (bool)
  - `unclear_close` {outcome, reason}
- `third_party`
  - `say_only_opening` (bool)
  - `callback` {allowed_days: [today, next_business_day], from, to, inclusive (bool), after_now (bool), ask_again_times (int)}
  - closes for callback, no_callback, wrong_number, deceased
  - `deceased_sentence`, `relative_cannot_verify` (bool)
- `identity`
  - `questions[]` {api_field (OpenAPI enum), ask_text, answer_format, numeric_date_order}
  - `max_wrong_total`
  - `swapped` {hint_value, instruction, counts_as_wrong (bool)}
  - `decline` {explain_once_text, max_declines (int), purpose_question_counts (bool)}
  - `fail_message`
  - `fail_close`, `decline_close`
- `calendar`
  - `business_weekdays[]`, `holidays[]` (ISO, possibly date-conditional)
  - `deadline_rule` {kind: nth_business_day_after_today, n_from_band (bool)}
  - `next_weekday` (`following_calendar_week` \| `next_occurrence`), `this_weekday` (`current_week`)
  - `numeric_date_order`
- `bands[]` {days_late_min, days_late_max, deadline_business_days, persuasion_attempts}
- `debt_statement`
  - `intro_instruction`
  - `product_labels[]` {product_type, template e.g. "credit card ending {card_last4}"}
  - `include` [past_due, days_late]
- `amounts`
  - `floor_field_by_type[]` {product_type, account_field}
  - `ask_full_first` (bool), `never_ask_how_much` (bool)
  - `accept_range` {min: floor, max: full, inclusive (bool)}
  - `too_much` {offer_floor_once (bool), say_rest_overdue (bool)}
  - `below_floor` {offer_floor_once (bool)}
  - `refuse_floor_is_flat_refusal` (bool)
- `negotiation`
  - `first_question`
  - `attempts[]` {n, amount: full|floor|floor_if_full_refused, date: last_business_day_this_week|deadline|…, if_today_is_that_day: next_week (bool), bands_allowed[]}
  - `proposal_is_not_refusal` (bool)
  - `vague` {ask_once (bool), then: propose_deadline}
  - `nonbusiness_date` {offer_next_business_day (bool)}
  - `after_deadline` {offer_deadline (bool), refusing_deadline_is_flat_refusal (bool)}
  - `no_answer_is_refusal` (bool), `forbidden_offers[]`
- `special_intents[]`
  - {key, trigger_description, allowed_before_identity (bool), applies_to: all|current_product|named_product}
  - `say` {verbatim|instruction}
  - `ask_once_first` (bool)
  - `action` {kind: none|transfer|note|callback, queue, note_reason}
  - `close` {outcome, reason} or `continue_other_products` (bool)
  - `precedence` (int)
  - `suppresses_persuasion` (bool), `customer_named_terms_still_recorded` (bool)
- `confirmation`
  - `readback_elements[]`, `confirm_question`
  - `recheck_on_change` (bool)
  - `one_promise_per_product` (bool), `change_after_record_text`
- `recording`: `max_attempts` (int), `success_sentence` (verbatim), `failure_close`, `failure_note_reason`
- `multi_product`
  - `enabled`, `state_all_first`, `ask_all_today_first`, `per_product_attempts`
  - `single_combined_readback`, `order: as_returned`
  - `date_over_deadline: use_product_deadline_and_say_so` (bool)
  - `note_reasons[]`, `notes_on_transfer` (bool)
  - `unrecorded_on_transfer_are_dropped` (bool)
- `closing`
  - `goodbye_before_close` (bool)
  - `outcome_table[]` {outcome, reason or "", when}
  - `aggregation` {promise_wins (bool), transfer_wins_over_promise (bool), all_noted_as: {reason → outcome}, else: first_non_X_note_reason_in_order}
- `required_phrases[]` {text, when}
- `behaviour_rules[]` {agent_instruction, stage, fact_ids}
- `unresolved[]` {topic, default_applied}

**Rule:** extend the schema only **generically**; no field named after a Brief A-only concept.

**Early check (T2.1):** the JSON Schema must compile under the structured-output limits (nesting, size). If it doesn't, split 1b into 2-3 calls by section.

### 2.4 Phone-agent reference graph (adjust after spikes)

**State variables** (string values, written by code and hooks; names defined in the templates):

| Area | Variables |
|---|---|
| Progress | `stage`, `confirm_asks`, `id_q_idx`, `id_wrong_total`, `id_declines`, `debt_stated` |
| Products | `products_json`, `product_count`, `cur_idx`, `cur_product_id`, `cur_label`, `cur_past_due`, `cur_floor`, `cur_deadline_iso`, `cur_deadline_text`, `cur_attempts_max`, `cur_attempts_used` |
| Proposals | `cur_proposal_amount`, `cur_proposal_date`, `cur_proposal_text` |
| Calendar | `date_facts`, `callback_facts` |
| Per product | `agreed_json`, `promised_json`, `notes_json`, `promise_attempts` |
| Per step | `<step>_status` flags |
| Closing | `close_key`, `turns_<node>` counters |

Text variables shown to the model:
- `date_facts` lists every day from today to the largest deadline + 7 days, each with its weekday, business day or holiday, this/next-week labels, and the deadline per product.
- `debt_text`, `readback_text` and `proposal_text` are built by code.

**Nodes** (keys are illustrative). In every conversation node, extraction runs on the **latest customer message only**, and enum values come from the spec plus the generic set below.

1. **`opening`** (conversation, initial, no tool)
   - `on_enter` tts: opening plus confirm question from the spec.
   - Extraction: `who` {confirms, third_party, wrong_number, deceased, asks_question, wants_human, not_talk, unclear, none}.
   - → `always` → `route_opening`.
2. **`route_opening`** (code, passthrough)
   - Initializes the calendar facts once.
   - Applies the confirm-ask policy (rule 3 incl. "answer a question first"), the human-request and not-talk policies, consumes `who`.
   - → identity / third_party / `opening_reask` (conversation) / close nodes.
3. **`third_party`** (conversation, no tool)
   - Extraction: callback date parts + `cb_time` (HH:MM pattern) + `tp_intent` {gives_time, refuses, wrong_number, deceased, none}.
   - → `callback_check` (code: resolve, window, ask-again counter) → `do_callback` (api_request, baked `{{cb_date}}` / `{{cb_time}}`) → `wrap_up`, or back to `third_party`, or close.
4. **`identity_q{i}`** (conversation; tool `verify_identity` with `field` **baked** to the question's `api_field`, `answer` model-filled)
   - Post-hook: `idq{i}_status` = verified | wrong | swapped | unreadable | locked, plus `what_to_do_next`.
   - Exits per C11: on the status flag (→ next question / `identity_ok` / same node again via `idq_reset` code / failed close), or on the exit enum `id_reply` {declines, asks_purpose, wants_human, not_talk} → `id_router` (code).
   - Never `always`.
5. **`load_account`** (api_request `get_account`, passthrough) → **`account_facts`** (code)
   - Parses products defensively (S2): labels, floors, bands, deadlines, attempts, `debt_text`, `date_facts`, `cur_*` for index 0.
6. **`state_debt`** (conversation, no tool)
   - Says `debt_text` and asks the first question.
   - Extraction: `pay` {yes_today, accepts_offer, proposes, too_much, refuses, no_answer, vague, already_paid, dispute, hardship, wants_plan, wants_human, not_talk, asks_question, none} + date parts + `amount_said` (float) + `applies_to` {all, current, other_product} + `product_hint`.
   - → `negotiation_router` (code).
7. **`negotiation_router`** (code)
   - Consumes `pay`.
   - Applies amount and date policy (floor, range, non-business day, after the deadline, vague).
   - Applies attempts and special intents (precedence; hardship suppresses persuasion; customer-named terms still recorded).
   - Sets `cur_proposal_*` and `proposal_text`, or marks the product agreed or noted, advances `cur_idx`.
   - Routes to `negotiate` / `readback` / special handlers / `wrap_up`.
8. **`negotiate`** (conversation, no tool): says `proposal_text` or asks per policy. Same extraction as `state_debt`. → `negotiation_router`.
9. **`readback`** (conversation, no tool)
   - Reads `readback_text` (all agreed promises, with deadline adjustments stated) and asks the confirm question.
   - Extraction: `rb` {confirms, changes, refuses, none} + date and amount parts.
   - → `readback_router` (code: re-validate a change → `readback` again, or `negotiate`).
10. **Write loop (G2).** `promise_guard` (code: business day, ≥ today, ≤ the product's deadline, floor ≤ amount ≤ past_due, not yet promised) → `do_promise` (api_request; `product_id` / `amount:json` / `date` baked) → `promise_result` (code: per-step status; retry once; on the second failure follow the failure policy) → next product or `say_recorded` (conversation, tts `success_sentence`) → `wrap_up`.
    - G3 fallback: a `record` conversation node with the model tool; C11 rules apply.
11. **Special handlers.** `do_transfer` (api_request, baked queue) and `do_note` loop (api_request per unpromised product), entered from the routers.
    - Answer-and-continue interrupts live in the prompts (C12).
12. **`wrap_up`** (code)
    - Pre-close check: every needed note exists; no notes on transfer; one promise per product; nothing recorded twice.
    - Picks `close_key` from `outcome_table` and `aggregation`.
    - → `goodbye` (per S5) → `close_<key>` (api_request with literal body) → `end_<key>` (end_call `none`; function name = outcome).

**Required everywhere:**
- no `null`
- `min_confidence` 0.6-0.7 on extraction variables
- every passthrough node ends with `always`
- tools only on conversation nodes
- imperative tool descriptions
- `maxRetries: 0` on writes
- post-hooks strip `header`, write per-step flags, add `what_to_do_next`
- prompts say "after every tool result speak or call the next tool"
- no model-filled field name equal to an already-set variable (tc L99)
- C11 and C13 hold

---

## 3. Schedule (UTC; now Sat 23:00)

**Freeze is Sun 15:00, which leaves 2 h of buffer.** About 16 h remain including sleep, so plan about 11-12 focused hours.

With two coding agents, run Track A (platform + generator) and Track B (extraction + verify) in parallel. They meet at the `spec.json` contract (the gold spec is the stub).

| Window | Track A (platform, generator) | Track B (extraction) | Checkpoint |
|---|---|---|---|
| 23:00-00:00 | Phase 0 (keys!, env), start spikes S1-S7 | T2.1 schema + T2.2 gold spec A | spikes S1-S3 answered |
| 00:00-03:00 | finish spikes; Phase 5 MVP from gold spec A (snippets, graph, G2 or G3) | T3.1-T3.4 extraction on A (+ T3.3 resolve tests) | **MVP agent saved and run on PUB-01..10 (reps 1)** |
| sleep | | | |
| 08:00-10:30 | fix loop on A (reps 3); multi-product B (T5.5) | gold spec B; T4.1 verify; one raw mock (T2.4a) + eval | A ≥ 8/10 at reps 3 |
| 10:30-12:30 | static tests (Phase 6); CLI, trace, export (Phase 7) | T3.4 on B and the raw mock | one command A+B end to end |
| 12:30-14:30 | evaluation round (A+B reps 3, a few styles at reps 1, own cases); fixes | voting (T3.5, if stable); grep audit | DoD check |
| 14:30-15:00 | reproducibility (T10.1 light), dry run of the final runbook, tag `pre-final` | | **freeze** |

**If behind, cut in this order:**
1. variant comparison
2. styles beyond `in_words`/`pieces`
3. voting
4. LLM sentence coverage (T4.2b)
5. mock briefs beyond the raw one
6. own cases beyond the top 6

---

## 4. Phases and tasks

### Phase 0: Setup (P0)

- **T0.0 Key hygiene (CRITICAL, user action).**
  - Commit `c2e5c12` added `.env` with non-empty `FREYA_API_KEY` and `FREYA_BANK_TEAM_KEY`. It was pushed to the GitHub remote (`sercan-dev`, merged into `master` via PR #1). Organizers will clone the repo.
  - **Rotate** the Freya API key in workspace settings and choose a **new** `FREYA_BANK_TEAM_KEY`.
  - Then **purge `.env` from history** (e.g. `git filter-repo --path .env --invert-paths`, then force-push the branches). That is a destructive rewrite; the user does it or explicitly approves it.
  - **AC:** `git log --all -- .env` is empty; the old key is revoked; the trace grep (T7.4) also scans `git log -p`.
- **T0.1 Environment.**
  - Python ≥ 3.10 env; `requirements.txt` (`anthropic`, `pydantic`).
  - `.env.example` → `.env`; `source .env`.
  - **AC:** `import anthropic, pydantic` works; `freya.workspace_id()` returns the workspace id.
- **T0.2 Baselines** (reuse the existing `base` slot; do not create a new one).
  - `results/log.jsonl` already shows the base agent at 0/10 on A (reps 1); the README reported 2/13.
  - Optionally run the example builder once and score it with `--reps 3`.
  - **AC:** `dev/baselines.md` records the numbers. Our builder must beat them.

### Phase 1: Spikes (P0, about 2 h, in the `spike` slot)

Use tiny workflows. Test with `chat/message` for pre-tool behaviour, and for anything that writes to the bank use a **PUB practice session** (`run_cases.py --only PUB-xx`). Never use fake customer ids against the bank. Record each result in `memory.md` §3c.

| Id | Question | Decides |
|---|---|---|
| S1 | Do pre- and post-hooks run on a `pre_actions` api_call in an `api_request` node? (That hooks can write vars is already documented, tc L416.) | G2 status flags, close nodes |
| S2 | In what form do `get_account` products arrive in `vars` (mapped list, JSON string, flattened keys)? | `account_facts` parser |
| S3 | Does extraction see assistant turns? What does a `date`-typed value anchor on? Does `{{var}}` resolve in an extraction `description`? Can a `float` extraction parse amounts said in words? | date and amount capture (C2) |
| S4 | After a code node resets an extracted enum to `none`, does extraction re-produce it from older turns? | C3 rules |
| S5 | Is the close node's `on_enter` tts spoken before its `pre_actions` run? Does a close node with a literal body plus `end_call none` give the right ledger and transcript order? | C7 goodbye mechanism |
| S6 | Is `{{amount:json}}` baked into a number field sent as a number, and does the ledger record a float? Do baked `product_id`/`date` from code variables reach the bank? | G2 feasibility |
| S7 | What does the PUB-10 failure look like (HTTP 500 or `ok:false`)? How do the `<node>_failure_count`/`_success_count` counters behave on an api_request node? | retry logic |
| S8 (P1) | Can code → api → code re-enter the same api node N times (notes and promises per product)? | B write loop |
| S9 (P1) | Is a code node right after a conversation node executed in `chat/message`? | smoke design |
| S10 | Median slowest turn with node-scoped prompts. | prompt budget |

**AC:** each spike's result is recorded, and the open choices (G2 vs G3, the S5 goodbye mechanism, date capture) are decided in `memory.md`.

### Phase 2: Schema and gold specs (P0)

- **T2.1** `builder/schema.py` (§2.3), using lists of objects rather than free-form dicts.
  - **AC:** the models validate; the JSON Schema compiles under the structured-output limits (test one call); otherwise split 1b by section.
- **T2.2** `dev/gold/brief-a.spec.json` (first) and `dev/gold/brief-ab.spec.json` (A+B).
  - **AC:** every Brief A rule (1-47) and Brief B item (1-11 + closing) maps to a field or a `behaviour_rule`, with its rule id in `fact_ids` (e.g. `A-R18`). The coverage table is in `dev/gold/README.md`.
- **T2.3** `dev/eval_extract.py`: field-by-field comparison with the gold spec (normalized).
  - **AC:** gold vs gold gives 100%.
- **T2.4** Mock briefs with a mock OpenAPI and a gold spec each.
  - (a) **P1:** a raw-material version of A: mail + policy + a dated memo that changes ≥ 2 values without saying "supersedes" + a code list + a discussion thread that decides nothing.
  - (b-d) **P2:** shifted values; other identity fields and outcome codes; other call-variable names.

### Phase 3: Extraction (P0, Track B)

- **T3.1** `llm.py`:
  - model `claude-opus-5-5`; do not send `thinking` disable, `temperature` or `budget_tokens` (they return 400)
  - set effort explicitly (`high` for extraction); the default is `medium`
  - structured outputs (`client.messages.parse(output_format=…)`, or `output_config.format` + pydantic)
  - **no forced `tool_choice`**
  - check `stop_reason` (`refusal`, `max_tokens`); stream large outputs
  - SDK retries
  - trace line per call: model, purpose, seconds, tokens, request id
  - **AC:** a test call returns a validated model and writes a trace line.
- **T3.2** Stage 1a prompt. Instructions:
  - read everything
  - one atomic fact per checkable statement, quoted verbatim
  - classify kind and stage
  - documents may conflict or supersede each other: list conflicts, don't resolve them
  - code lists define the allowed codes
  - no outside knowledge
  - write `agent_instruction` in plain English
  - **AC:** on A, the gold topics are present (measured through 1b); on mock (a), the memo/policy conflicts are listed.
- **T3.3** `resolve.py` per §2.3.
  - **AC:** unit tests: a newer memo wins; discussion is ignored; an equal-date conflict is unresolved and gets the stricter default; `effective_from` gives a date-conditional value.
- **T3.4** Stage 1b prompt: fill the spec from governing facts only; tool fields and enums from the OpenAPI.
  - **AC:** `eval_extract` vs gold gives A ≥ 95%, A+B ≥ 95%, mock (a) ≥ 90%. Misses go to `dev/issues.json`.
- **T3.5 (P1)** Voting `--votes 3`: field-wise majority. A disagreement on a code-relevant field is settled by the quote re-parse (T4.1), else the stricter value; it is logged.
  - **AC:** three runs on A give identical code-relevant fields.

### Phase 4: Verify (P0 for T4.1, P1 for T4.2b)

- **T4.1** Code checks:
  - identity `api_field`s, queues and note reasons exist in the OpenAPI enums
  - close outcomes exist in the `close_call` outcome enum
  - **close reasons** match the brief's outcome table or code list (the OpenAPI has no reason enum)
  - holidays are valid ISO dates; bands are contiguous; times are HH:MM
  - every leaf's `fact_ids` point to governing decision facts
  - numbers and operators are re-parsed from `source_quote` (digits and number words) and match
  - required phrases are verbatim substrings of the inputs
  - **AC:** a seeded wrong value (e.g. 10 where the quote says "8") is caught.
- **T4.2a** Every governing decision fact is used by the spec or `behaviour_rules` (code check).
- **T4.2b (P1)** Sentence coverage: sentences are split in code; one LLM call (effort medium) labels each with fact ids or "none"/"boilerplate".
  - **AC:** a deleted fact is detected.
- **T4.3** On errors: one re-extract with feedback, then continue with warnings logged.

### Phase 5: Generator (P0, Track A, built from the gold spec first)

- **T5.1** `openapi_tools.py`:
  - per operation, an `api_call` tool: `url` = servers[0].url + path, `method`, the Content-Type header
  - body leaves with type, description and enum
  - baked fields: `customer_id` from the spec's `customer_id_var`, numbers as `{{x:json}}`
  - model-filled fields default to `{{<field>}}`, using no existing variable name
  - variants per use: a baked identity `field`; fully baked bodies for engine-run writes
  - **AC:** the tools match the base agent's shape without its nulls and undocumented fields; dry run passes.
- **T5.2** Snippet templates (`json`, `re`, `datetime` only; C14 constant injection; no `{{`/`}}`; try/except with fallbacks; string flags):
  - `calendar_facts`: business days, holidays, nth business day, last business day of this or next week (rule 30 exception), this/next weekday per the spec, `date_facts` window
  - `callback_check`
  - `account_facts`
  - `negotiation_router` (the policy engine: amounts, dates, attempts, special intents, precedence, multi-product scope)
  - `readback_router`
  - `promise_guard` and `promise_result`
  - `note_loop`
  - `id_router` / `idq_reset`
  - `route_opening`
  - `wrap_up` (pre-close check, outcome table, aggregation)
  - post-hooks per tool
  - **AC:** every template renders for gold A and A+B and passes Phase 6.
- **T5.3** Prompt templates:
  - `system_prompt`: identity, language, tone, short turns, "after every tool result speak or call the next tool", "never say something is recorded unless the result says so", answer-and-continue interrupts (C12)
  - per-node `task_message` = fixed template + that stage's `agent_instruction`s + the stage's required phrases + code-built text variables
  - **AC:** no prompt contains another stage's instructions; sizes are logged.
- **T5.4** `generate.py` assembles the graph per §2.4:
  - extraction schemas with enums generated from the spec's `special_intents` plus the generic set
  - transitions with deterministic ones first
  - per-outcome close nodes
  - **AC (MVP):** the Brief A workflow from the gold spec saves and runs through `run_cases --brief A`; no deadlocks; the lint passes.
- **T5.5** Multi-product (B):
  - state all products → ask all today → per-product negotiation (attempts per product)
  - one date for all, applying each product's own deadline and saying so (B6)
  - per-product dispute or paid notes while continuing with the others (B9)
  - a transfer drops unrecorded agreements and adds no notes (B10)
  - per-product write failure → `service_error` note (B11)
  - combined read-back → write loop → note loop → aggregation
  - **AC:** PUB-11..13 pass at reps 1; the ledger shows one promise per agreed product and the correct notes.
- **T5.6** `--guard g2|g3` switch (default from the S6 result).

### Phase 6: Static tests (P0)

- **T6.1** Local harness:
  - code nodes: `exec(snippet, {"vars": v})`
  - hooks: simulated `result` envelopes and `config`
  - **assert outputs**
  - **AC:** each template is run on several `now` dates (Mon, Wed, Fri, the last business day of a week, the day before a holiday, month end, year end), on empty or garbage input, and on malformed tool responses ("True"/"true", missing fields, a datetime in place of a date, `ok:true` without an id).
- **T6.2** Invariants:
  - deadlines are business days, N business days after today
  - this/next weekday semantics
  - the rule 30 exception
  - the callback window
  - the guard accepts every in-policy value and rejects every out-of-policy value
  - `wrap_up` returns only rows of the outcome table
  - the reason is absent where the table has none
  - B aggregation
  - **create_promise failing twice** (static only; the bank cannot simulate it on other customers)
- **T6.3** Test-first fact examples generated **in code from the spec**: one compliant and one violating example per code-relevant fact.
- **T6.4** Workflow lint:
  - no `null`; no `{{`/`}}` in code
  - every prompt `{{var}}` is set by an upstream node (data-flow check)
  - passthrough nodes end with `always`
  - C11 holds on tool nodes; no global node is blocked by design mistake
  - every path reaches an `end_call`
  - `min_confidence` is set; writes have `maxRetries: 0`
  - no model-filled field collides with a variable name
  - `freya.validate_workflow` dry run
- **AC:** `python -m builder.static_tests out/<slot>.workflow.json out/<slot>.spec.json` passes for A, A+B and the mock in under 30 s.

### Phase 7: Save, smoke, export, trace, CLI (P0)

- **T7.1** `freya_io.save`: absolute state path; one extra update after a first create.
  - **AC:** a second build updates the same workflow and the published version increases.
- **T7.2** Smoke (chat/message, two turns, no tool calls).
  - Checks: required opening elements; no forbidden words; the turn-2 reply asks the first identity question; ends with `chat/end`.
  - A failure is a warning, not a stop.
- **T7.3** Export to `submission/<slot>.workflow.json`.
- **T7.4** Trace `submission/<slot>.trace.txt`:
  - start/end UTC and duration
  - every model call (model + one-line purpose + tokens/seconds)
  - workflow id, agent id, version, node count, tool count
  - static and smoke results
  - resolved conflicts, unresolved defaults, vote disputes, skipped steps
  - redact keys
  - **AC:** a grep for `fak_` and `sk-ant-` is clean in the trace and in `git log -p`.
- **T7.5** CLI per §2.1.
  - **AC:** a fresh clone + `.env` + `pip install -r requirements.txt` → one command builds A and A+B with no manual step.

### Phase 8: Practice evaluation loop (P1)

- **T8.1** Run `--reps 3` on A and B with the default style. Run styles `in_words`, `pieces` and `corrects` at reps 1; add more if time allows. Failures go to `dev/issues.json`.
- **T8.2** Own cases (`dev/cases/*.json`, same format as `public-test-set.json`).
  - **Constraints:**
    - `run_cases.py` opens bank sessions by case id, so an own case must **reuse a PUB id**. The bank then fixes `now` (Wed 2026-10-14), the products, the identity and the faults (PUB-10's first failure).
    - Third-party scripts need `"family": "Third party"`.
    - Write `script`, `expected` and `checks` from the brief.
    - Verify early on one case that the bank accepts the reuse and the scorer reads it.
  - **Top 6 gaps** (none is tested by any PUB case):
    - 40: dispute
    - 42: asks for a human, insists
    - 13: day/month swapped
    - 27: amount below the floor
    - 32: support transfer accepted
    - 45: says twice they do not want to talk
  - **Then:**
    - 8 wrong number
    - 9 deceased
    - 3 unclear
    - 7 callback outside the window
    - 15 declines identity questions
    - 22 "next Friday"
    - 20 weekend date
    - 23 refuses the deadline
    - 26 refuses the floor
    - 35-36 change at read-back / change a recorded promise
    - 43-44 scam question / question the agent cannot answer
    - transfer after a recorded promise
    - B8 no promise at all
    - B9 dispute on one product
    - B10 restructuring after a recorded promise
    - B closing aggregation
  - **Static tests only:** rule 37 "fails twice"; other calendar days (including the rule 30 exception, since every bank session is on a Wednesday).
- **T8.3** Fix loop: fix in templates or prompts, never by editing a workflow; rebuild through the CLI; re-run the affected cases plus confirmed fixes.
- **T8.4 (P2)** Variant comparison (G2 vs G3, prompt granularity).
- **Target before the freeze:** A 10/10 and B 3/3 at reps 3 (default style); styles mostly green at reps 1; the top 6 own cases passing.

### Phase 9: Generalization (P1, light)

- Run the builder on mock (a), and on others if they exist, with `--skip-smoke` and a `mock` slot.
  - **AC:** extraction ≥ 90%; Verify catches seeded errors; static tests pass; the freya dry run passes.
- `dev/audit_grep.py`: no Brief A/B literal (dates, bank name, rule numbers, "4821", outcome names) in `builder/` outside test fixtures.
  - **AC:** clean.

### Phase 10: Final readiness (P0, by 15:00)

- **T10.1** Build A+B twice; diff the code-relevant spec fields and the workflow (ignoring ids); one `--reps 3` on the second agent.
  - **AC:** identical code-relevant fields; score within ±1.
- **T10.2** Timing: an A+B build takes < 15 min.
- **T10.3** Isolation: the builder opens only its CLI inputs and `builder/` (test by temporarily moving `dev/` and the md docs away).
- **T10.4** Dry run of the runbook on mock (a) with a fresh slot; tag `pre-final`.

### Phase 11: Sunday runbook (17:00-20:00 UTC)

1. Put the hidden inputs in `final_inputs/`, outside `builder/`. Don't paste their content anywhere else. Committing them is not required.
2. Run `python3 builder/build.py final_inputs/<files…> final_inputs/<api>.json --slot final-<n>`. Add `--votes 3` only if T3.5 is done and stable.
3. On a crash: make a **generic** fix (parser, schema edge case), commit it with a generic message, and rebuild from scratch. Never add brief values, names or rules.
4. Check the trace and the static results. **No hand edits.**
5. Commit the code + `submission/` + `requirements.txt`; record the hash.
6. Email the form before 20:00: team, repo, commit, run command, workflow paths, trace paths.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| The schema lacks a hidden-brief concept | `behaviour_rules` → prompts; log it |
| Extraction misreads an operator or number | quote re-parse; voting (P1) |
| Agent model latency → hang-ups | node-scoped prompts, few tools per node; S10 |
| G2 spike fails | G3 fallback; never fake a block |
| Stale flags or intents misroute | C3, C11, lint, S4 |
| Top-10 rerun scores lower | deterministic generation, resolution, voting, T10.1 |
| Time | §3 cut order |

## 6. Definition of done (Sun 15:00 UTC)

- [ ] Keys rotated and purged from history (T0.0)
- [ ] One command builds A and A+B from a fresh clone; complete trace; < 15 min
- [ ] A 10/10 and B 3/3 at `--reps 3`; top 6 own cases pass
- [ ] Static tests pass for A, A+B and the raw mock; extraction ≥ 90% on the mock
- [ ] Grep audit clean; isolation verified; tag `pre-final`
- [ ] `memory.md` updated with verified platform facts and final decisions

## 9. Review log (v1 → v2)

The 18 findings of the adversarial review and their fixes:

1. Time budget → §3 schedule, cut order, P-levels moved.
2. Order → vertical slice from the gold spec, parallel extraction track.
3. Global nodes are blocked by `always`, and routing preempts tools → C11, C12, lint.
4. Stale flags and intents → C3.
5. Close mechanism → C7 (one close node per outcome row).
6. G4 / number baking → C1 (G2 with `{{x:json}}`), S6.
7. Date capture parts → C2.
8. Incomplete enums → §2.4 enums generated from the spec.
9. Non-executable spec fields → §2.3 closed parameters.
10. JSON constant injection → C14.
11. PUB coverage list fixed (rules 30-31 are covered by PUB-12; gaps added) and own-case constraints added → T8.2.
12. The close reason has no OpenAPI enum → T4.1.
13. Keys in git history → T0.0.
14. memory.md mismatches → fixed in memory.md.
15. Turn caps → C13.
16. Spike list adjusted → Phase 1.
17. Name-collision lint → T6.4.
18. Housekeeping: `submission/`, `.env.example`, no hard abort, conditional `--votes`, `date_facts` window, S6 on a PUB session, schema size check, non-md inputs.
