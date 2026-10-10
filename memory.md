# memory.md: shared project memory for Build the Builder

Shared context for every agent working on this repo: decisions, why we made them, and what is still open.
Last updated: 2026-10-10 (Sat), kit version 3. Checked against https://www.freyavoice.ai/hackathon (Overview, Data, Evaluation) on 2026-10-10.

> **The builder must not read this file.** It is dev material. `examples/agent_builder.py` runs Claude with `cwd=KIT`,
> `setting_sources=["project"]` and Read/Glob/Grep, so every file in this folder is reachable. Before any final run,
> move this file, `DEV_GUIDE.md` and all gold specs and tests out of the builder's reach, or deny them in its permissions.
> Never rename this file to `CLAUDE.md` or `AGENTS.md`: the builder's own agent would load it automatically.
> After the hidden briefs open (Sun 17:00 UTC), add **nothing** from them to this file. The reviewer checks the commit.

Related files: `DEV_PLAN.md` (step-by-step implementation plan and spikes), `DEV_GUIDE.md` (file map, line refs, Brief A rule index), `README.md` (kit rules), `docs/` (Freya workflow format).
Visual version of the pipeline: https://claude.ai/artifact/2YaT7XTeG3MN66XvFt7eBv (private to the owner).

---

## 1. The challenge (checked against the hackathon page)

- **Task:** write a *builder*, a program that reads a bank's debt-collection brief plus a tool API file (OpenAPI) and creates a Freya *phone agent* (workflow) with no manual step.
- **Domain:** a phone agent calls customers late on payments, verifies identity, states the debt, records a promise to pay, or handles dispute, paid, hardship, transfer, callback and similar cases, and closes with exactly one `close_call`.
- **Kit:** Brief A (one product, 47 rules), Brief B (up to 3 products, builds on A), `tools/openapi.json` (7 tools: `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`), 13 practice cases (PUB-01..10 on A, PUB-11..13 on B, all at `now = 2026-10-14T11:00`), Freya docs, `freya.py`, example agent and builder, scorer.
- **Final:** on Sun 17:00 UTC, two hidden briefs are released, each with **its own tool API file**. The 7 tool names stay the same; **fields and allowed values can change**.
  - One brief is a clean specification. The other is **raw bank material: a mail, a policy extract, a memo that changes it, and a code list**.
  - They contain other rules, numbers, limits, identity questions, outcome table and calendar.
  - **No practice cases come with the hidden briefs.** Builders cannot open practice customers; only PUB-01..PUB-13 exist. Organizers suggest `POST /api/v2/chat/message` for testing a brief without cases.
- **Benchmark:** 60 hidden cases (30 per brief), 1-3 products each, **several calendar days**, each case **run 3 times, passes only if all 3 pass**.
- **Customers talk like people:** they split numbers in two, correct themselves, go off topic, ask questions back, and say amounts and dates in words. Practise with `run_cases.py --style pieces|corrects|talkative|asks_back|in_words`.

## 2. Scoring, rules and limits (checked against the page)

- **A case passes only if all three hold** (no partial credit):
  1. **Outcome**: the bank ledger is exactly right (outcome, reason, promises with product, amount and date recorded once, notes, callbacks, transfers). A correct refusal also passes, e.g. a recorded dispute with no promise.
  2. **Policy**: a judge model reads the transcript and checks the call stayed inside the brief.
  3. **Honesty**: the agent never claims something was recorded when the tool call failed. Judged from the transcript.
- **Tie-breaks:** (1) total promised amount on passing cases, (2) shorter total build time from the traces, (3) earlier submission.
- **Rules:**
  - You must submit a builder; a hand-built agent is not a valid entry.
  - Phone agents must come out of the submitted commit with no manual edits.
  - The phone agent may call **only** the kit's tool API; calls to other services fail the case. Code steps and hooks inside the workflow are allowed and expected.
  - No probing or load-testing the platform. One Freya key per team.
  - After the hidden briefs open you may fix crashes, but you may not add any rule, value or name from them to code or prompts.
  - Synthetic data only.
  - One trace per hidden brief; entries without traces are not ranked.
- **Limits:**
  - Builder run: **30 min per brief, including self-tests**.
  - 200 workflows per workspace: update in place with `freya.save_workflow(slot, …)`.
  - The phone agent model is fixed in `freya.py` (`AGENT_LLM`); do not change it and leave `agent_config` out.
  - Builder models: any.
  - Practice simulations run one at a time per workspace (a 10-case run takes 3-11 min).
- **Deliverables (by Sun 20:00 UTC):**
  - Repo with the builder, runnable as one command (e.g. `python3 builder/build.py <brief> <tool_api>`).
  - One exported workflow per hidden brief (`freya.export_workflow`).
  - One plain-text trace per hidden brief: start and end time, each model call (model plus a one-line purpose), what was created on Freya (workflow id, agent id, step and tool counts), self-tests and their results, with API keys removed.
  - Submission form: team, repo, commit, run command, file paths.
  - Optional: coding-agent session logs.
- **Verification:** for the top 10, organizers **clone the commit, rerun the builder on the same briefs, and compare with the trace**. A reviewer agent checks traces against the code and the agent. An entry whose rerun scores clearly below its claim is removed. **So the builder itself must be reproducible, not only the agent.**

---

## 3. Decisions and how they fit the scenario

Status: ✅ required or clearly fits · ⚠️ allowed but limited or uncertain · ❌ not available in the final.

| # | Decision | Why | Fit |
|---|---|---|---|
| D1 | Builder = LLM understands the brief; **deterministic code** generates the workflow from templates. Node prompts are also templated: facts carry an `agent_instruction` written during extraction, and no LLM call happens at generate time (see C4). The builder calls the Anthropic API directly with explicit inputs; it is not a file-system agent (C9). | Same graph quality every run; graph hardened on A/B; reproducible for the top-10 rerun; no contamination. | ✅ builder plus no manual edits plus rerun check |
| D2 | **Tool definitions generated from the given OpenAPI file** (fields, enums, URL). | Hidden tool APIs change fields and values. | ✅ required |
| D3 | **No brief values in builder code or prompts.** Templates hold placeholders filled from the spec. No few-shot examples carrying Brief A values (they leak defaults). | Rule: nothing from hidden briefs; generalization. | ✅ required |
| D4 | **Two-stage Extract:** (1a) atomic facts with source quote, doc date, effective date, kind (decision or discussion), stage, scope, conditions, operator, plus a separate **conflicts list**; (1b) **code** resolves conflicts (newer dated decision wins, effective date respected, discussion never counts, unresolved goes to a safe default plus a trace note), then fills the schema from facts. | The raw brief has a memo that changes the policy. LLMs answer conflicts one-sidedly. | ✅ required for the raw-material brief |
| D5 | **Verify:** enum and field checks against OpenAPI; every spec field links to a governing decision fact; fact coverage; brief-sentence coverage; numbers and operators re-parsed from quotes in code; one re-extract on failure; optionally 2-3 parallel extractions compared. | Extraction is where errors start; relations and operators are the weak spot. | ✅ fits the 30-min budget (parallel) |
| D6 | **Graph outside the LLM:** code nodes and hooks write progress flags (`identity_verified`, `debt_stated`, `promise_confirmed`, …); routing on variables. The LLM interprets customer intent in extraction, code owns control and the **close outcome**. | Pass^3 needs determinism (PolicyGuide, STAGE). | ✅ code steps are allowed and expected |
| D7 | **Node-scoped prompts:** each node gets only the facts of its stage (fixed template plus that stage's `agent_instruction`s); the global `system_prompt` holds identity, language and tone only. Required sentences are copied verbatim. | STAGE ablation; the judge checks exact sentences. | ✅ |
| D8 | **Date and amount math in code** (deadline, business days, holidays, "this/next weekday", floor, last business day of the week) from the `now` variable; results reach prompts as text (`{{date_facts}}`). | Hidden cases run on several calendar days; the agent model must not count days. | ✅ required |
| D9 | **Guards before every write:** check date window, business day, amount bounds and product before `create_promise`; time window before `schedule_callback`; reason enum before `add_note`; queue before `transfer_to_agent`; and check `close_call`. On a violation, route back with a reason the model can recover from. **A code node cannot block a tool the model calls (C1).** **Target G2:** a code node validates the agreed values held in variables, then an `api_request` node writes with baked values; numbers are sent with `{{x:json}}`. **Fallback G3:** model tool plus strong prompt plus `date_facts` plus post-hook. **G1** (aborting pre-hook) is undocumented: P2. Spikes S3/S6 decide between G2 and G3. Never redirect a request to another host. Callback, note, transfer and close are engine-run nodes after code validation. | Outcome check is ledger-exact, and the bank mock does **not** enforce the brief (it records promises on holidays or past the deadline). Guards beat prompt policy (ToolGuards, PCAS). | ✅ (mechanism decided by spike) |
| D10 | **Pre-close check** in `wrap_up`: every required note, callback and transfer done exactly once, no notes on transfer (Brief B rule); outcome and reason chosen by code. | Guards cannot catch an action that never happened (PolicyGuide). | ✅ |
| D11 | **Honesty:** post-hooks write `tool_status = OK|FAILED`; routing branches on it; `ok:true` with a missing expected id counts as FAILED; retry once, then say it failed (Brief A rule 37). | The honesty check is one of three pass conditions. | ✅ required |
| D12 | **Multi-product** support in the skeleton (loop per product, per-product deadline and attempt counter, one combined read-back, `add_note` for unpromised products). | Hidden customers have 1-3 products. | ✅ required |
| D13 | **Normalization in hooks** (boolean "True"/"true", field aliases, date vs datetime). | Cheap robustness. The page does not mention defective APIs, so the full defect catalog is low priority. | ⚠️ keep it cheap |
| D14 | **Local static tests** (seconds): run snippets with `exec` on several `now` dates; check invariants; give hooks malformed responses; check there is no `{{`/`}}` in code and every prompt `{{var}}` is set; `validate_workflow` dry run; **test-first** (one compliant and one violating example per fact). | Hidden briefs have no practice cases; this is the strongest check available in the final. | ✅ no platform load |
| D15 | **Smoke test via `POST /api/v2/chat/message`** (2-3 turns; automated checks such as no forbidden words before identity and the first question matching the spec). | Organizers recommend it. | ✅ |
| D16 | **Full simulations** (`run_cases.py --reps 3 --style …`) in **development only**. | One at a time, 3-11 min each; practice customers are not available in the final. | ❌ in the final · ✅ in development |
| D17 | **Own case files** reusing PUB customers with new scripts (`run_cases.py --cases my.json`) to cover rules no PUB case tests. | `run_cases.py` opens the bank session by case id and builds the persona from `script`. | ⚠️ development only, low volume, not tested yet. An own case must **reuse a PUB id**, so the bank fixes `now` (Wed 2026-10-14), products, identity and faults. Third-party scripts need `"family": "Third party"`. "Fails twice" and other calendar days can only be covered by static tests. |
| D18 | **Freya unit-test API and chat fork-at-anchor** (found in docs.freyavoice.ai, not in the kit or on the page). | Could test hidden briefs without practice customers. | ⚠️ unverified on staging; use lightly; skip if in doubt (no-probing rule) |
| D19 | **Trace** = required fields plus resolved conflicts, safe defaults chosen, test results. Write it from the start. | Required; the reviewer compares the trace with the code. | ✅ required |
| D20 | **Reproducibility:** deterministic generation, conflict resolution in code, optional multi-run extraction agreement, recorded builder model and version. Never submit a lucky run. | The top-10 rerun removes entries that score clearly below their claim. | ✅ required by verification |
| D21 | **Tie-breaks:** follow the brief's order exactly (full amount first, then the floor), never offer less than the brief allows. Keep the final build short: no simulations, parallel LLM calls. | Promised amount and build time are tie-breaks. | ✅ |
| D22 | **Dev isolation:** the builder's LLM sees only the brief, the tool API and its own outputs; this file, `DEV_GUIDE.md`, gold specs and tests stay out of reach. | Avoids contamination and leaking Brief A answers. | ✅ |
| D23 | **Dev loop discipline:** measure the baselines first (`examples/base-agent.json`: 2/13 in the README's run, 0/10 on A in our run in `results/log.jsonl`; reuse the existing `base` slot; and the example builder); compare 2-3 skeleton variants with `--reps 3`; keep `issues.json` (stable id, status, evidence, fix history) and re-run fixed issues; **never relax a failing test to match the agent**. | τ^τ-Bench lessons; pass^3 punishes flakiness. | ✅ (time is limited by one simulation at a time) |

---

## 3b. Corrections made on 2026-10-10 (details in DEV_PLAN.md §1)

- C1: a code node cannot block a tool the model calls → guard options G1/G2/G3 (see D9).
- C2: the extraction `date` type resolves relative dates against the **real clock**, not the call's `now`. Code builds the calendar from `now`; the agent reads back absolute dates; values that feed writes come as absolute ISO strings or from structured parts that code resolves.
- C3: extracted variables persist across turns. Consume intents in a code node and reset them.
- C4: node prompts are templated (no build-time LLM prompt writing).
- C5: Opus 5.5 has no temperature control. Use structured outputs, code resolution and optional 3-way voting for reproducibility.
- C6: `chat/message` may skip a first code node, so the initial node is a conversation node. Smoke tests stop before any tool call.
- C7: generate one close `api_request` node per outcome-table row, with a literal body and **no `reason` leaf** where the table has none (the scorer compares the reason with `None`). Do not use a model tool (an unset `{{reason}}` gets invented) or a lifecycle tool (an unresolved parameter gets an LLM fill; the base agent got `(None, None)`). Spike S5 decides whether the goodbye is said before the close. `end_call` uses `none`.
- C8: the Freya unit-test API and chat fork are optional P2.
- C9: the builder uses the Anthropic API directly, not a file-system agent.
- C10: hidden briefs may name call variables differently; the spec captures the call-variable table.
- C11: in a node where the model must call a tool, never add an `always` or self-transition. Leave only on per-step tool flags or on exit enums that exclude the normal answer. Routing runs before the dialogue model.
- C12: global nodes never fire from a node that has an `always` transition. Handle answer-and-continue interrupts in prompts and action interrupts with exit enums routed to code.
- C13: `current_turns` resets on every transition, so count turns in code where a cap matters.
- C14: inject constants into snippets as `json.loads(repr(json.dumps(obj, indent=1)))`. JSON `true`/`null` break Python silently, and nested braces produce `}}`. Static tests assert outputs.
- Also from the review: never route on raw flattened tool keys (they persist across steps); write extraction descriptions as "latest customer message only"; the `close_call` reason has no OpenAPI enum, so it comes from the brief's table.

## 3a. SECURITY: keys in git history (2026-10-10)

Commit `c2e5c12` added `.env` with non-empty `FREYA_API_KEY` and `FREYA_BANK_TEAM_KEY`. It was pushed to GitHub (`sercan-dev`, merged into `master` via PR #1). The fix is a user action (DEV_PLAN T0.0): rotate the Freya key, pick a new team key, purge `.env` from history and force-push.

## 3c. Verified platform facts (DEV_PLAN Phase 1 spikes)

All verified 2026-10-10 23:00-23:30 UTC with `dev/spikes/make_spike1.py` (slot `spike`, 16 nodes) driven turn by turn through `POST /api/v2/chat/message` against PUB-10 practice sessions (`dev/spikes/chatdrive.py`; runs saved as `dev/spikes/spike1_run{1,2,3}.json`, call events read with `freya.get_call`). Plus the PUB-10/PUB-08 calls of the base-agent run in `results/base-a.json`.

| Id | Finding | Consequence |
|---|---|---|
| S1 | `pre_process_code` and `post_process_code` run on a `pre_actions` api_call in an `api_request` node. Both read and write `vars`; a later code node reads them. The pre-hook's `config['body']` holds the substituted body and **changes to it reach the wire**. **The post-hook does not run on a failed call** (HTTP 500 → `function_call_error`). | G2 status flags come from the post-hook; a failure is detected by resetting the flag before the node and routing on `flag != ok`, or on `<node>_failure_count`. |
| S2 | `response_mapping` of a list (`data.products` → `products`) gives **`None` in `vars`**; scalars map fine. Flattened keys exist and are named after the **node** for `pre_actions` (`load_account_response.data.products.0.product_id`, not `get_account_response…`). A post-hook can `json.dumps` the list into a variable, and code reads it back. | `account_facts` reads the post-hook JSON first, flattened `<node>_response.data.products.N.*` keys second. |
| S3 | Extraction **sees assistant turns** ("yes, that works" after a tts proposal gave the proposed date; the proposed amount was not re-extracted). A `date` value anchors relative words on the **real clock** ("tomorrow" said on 2026-10-10 with `now` 2026-10-14 → 2026-10-11). Absolute dates in words parse well (`twenty-third of February nineteen eighty-nine` → 1989-02-23). `float` parses words (`four hundred and twenty` → 420.0, `three hundred` → 300.0). **`{{var}}` does not resolve in an extraction `description`** (the literal `{{now}}` came back). | C2 stands: capture date **parts** and resolve in code against `now`. No variables in extraction descriptions. |
| S4 | After a code node set `intent = 'none'`, a neutral next message in a node with the same schema did **not** re-produce the old value (extraction wrote `none` again; `s4_hits` stayed 1). | C3 reset pattern works; "latest message only" descriptions are enough. |
| S5 | A close `api_request` node with `on_enter` tts emits the line **after** `function_call_start` and before `function_call_complete`: not safe for "goodbye before close_call". Mechanism (ii) works: conversation node `goodbye` (tts goodbye, no tools, single `always` transition) → the customer's reply → silent per-outcome close node (literal body) → `end_call` with `message_mode none`. Transcript order: goodbye, customer reply, close_call, end. Ledger: `promise` with reason `None`. The end is "deferred" in chat (a further message gets 504). | C7 + goodbye node; `endedReason` in chat was `assistant-ended-call`, not the terminal function name. |
| S6 | `{{p_amount:json}}` baked into a `number` field was sent as the **string** `"365.0"` (the mock still recorded 365). A pre-hook `b['amount'] = float(b['amount'])` sends a real number. Baked `product_id` and `date` from code variables reach the bank unchanged. | **G2 confirmed**: code validates, `api_request` writes with baked body, pre-hook coerces numeric types. |
| S7 | PUB-10's first `create_promise` is an **HTTP 500** with body `{"ok": false, "error": "service unavailable, nothing was recorded"}` → event `function_call_error`, `<node>_failure_count` = 1, `<node>_response.error` = `HTTP 500`, no `_response.data.*`, no post-hook. `<node>_success_count` is unset until a success. The mock rejects a free-text close reason with `ok:false` ("this outcome needs one of these reasons: …") and the ledger then has `(None, None)`. | Retry loop: `promise_guard`-set flag, `do_promise` → `promise_result` (code counts attempts, re-enters once). Close reasons must be literal table values. |
| S8 | code → api → code re-entering the same `api_request` node works (`do_promise` ran twice; the second call succeeded). | Per-product write and note loops are feasible. |
| S9 | A code node right after a conversation node **runs in `chat/message`**, and the following conversation node's `on_enter` tts is returned as the reply. But in chat the **initial node's `on_enter` is never spoken** and the **first turn's routing is suppressed** ("Missing prior assistant message"). An empty message is rejected (400). | Smoke test: send "Hello?" first; check the model's reply (the opening node's `task_message` must tell the model to say the opening if not yet said). First-turn transitions cannot be smoke-tested. |
| S10 | Chat turns with tiny prompts took 2-5 s (code and api nodes add about 1 s each). | Measure again on the MVP. |
| extra | A conversation node re-entered through its own `always` self-transition **replays `on_enter` tts** instead of a model reply unless `on_enter_first_entry_only: true`. `current_turns` resets on that self-transition (C13). The dialogue model freely claims actions ("I have scheduled that for you", "I have recorded your details") with no tool: prompts must forbid claiming any recording. | Every conversation node with a self-transition sets `on_enter_first_entry_only`. |

**Decisions taken from the spikes (2026-10-10 23:30 UTC):**
- **Guard = G2** (D9): `promise_guard` (code) validates the agreed values, `do_promise` (`api_request`, baked body, pre-hook float coercion, `maxRetries: 0`), `promise_result` (code: per-step flag, one retry).
- **Goodbye = mechanism (ii)** (C7): `wrap_up` sets `close_key`, `goodbye` (conversation, tts, `always` → `close_router`?) No: `goodbye` carries one deterministic transition per outcome row (`close_key equals <row>` → `close_<row>`) and nothing else, so the customer's reply closes the call; `close_<row>` is silent with a literal body; `end_<row>` uses `message_mode none`.
- **Date capture = parts** (C2): `day_ref` {today, tomorrow, day_after_tomorrow, weekday, day_of_month, vague, none}, `weekday`, `week_ref` {this, next, none}, `day_of_month` (int), `month` (enum), `vague_kind`; code resolves against `now`. `date`-typed extraction is not used for payment or callback dates. Identity answers stay model-filled tool arguments (the dialogue model converts the DOB; the prompt carries the number-order rule).

## 4. Pipeline (builder run, one brief)

1. **Extract (LLM, reasoning model, high effort):** read the whole brief at once, with no search or chunking. (1a) facts plus conflicts list, then (1b) code-based resolution and schema fill (`spec.json`). Structured output; every field cites a fact id.
2. **Verify (code + LLM):** OpenAPI enum and field checks; date and band sanity; facts → spec coverage; brief sentences → facts coverage; numeric and operator re-parse; on errors, one re-extract with feedback.
3. **Generate (code only, no LLM):** tools from OpenAPI; fixed parametric skeleton; snippet templates filled from the spec; guards; hooks with normalization and `tool_status`; templated node-scoped prompts filled with the facts' `agent_instruction`s.
4. **Static tests (local, seconds):** see D14.
5. **Save + smoke:** `freya.save_workflow(slot, wf)` (publishes), then 2-3 chat turns with automated checks.
6. **Simulation:** development only (see D16, D17).
7. **Export + trace:** `freya.export_workflow(id, "<brief>.workflow.json")` and `<brief>.trace.txt`.

Rough budget: Extract about 2.5 min, Verify about 3 min, Generate about 1 min, Static tests under 0.5 min, Save and smoke about 0.5 min. Measure these yourself.

## 5. Two kinds of Python (do not confuse them)

- **Builder code** runs on our machine once per brief (e.g. `builder/build.py`, `templates.py`, `generate.py`).
- **Workflow snippets** are strings inside `workflow.json` (code nodes, pre/post hooks). They run on Freya's sandbox in every call.
  - Only `json`, `re` and `datetime` are verified to work there.
  - Read inputs with `vars.get(...)` and write outputs to `vars[...]`.
  - Never write `{{` or `}}` in a snippet (use lists, not nested dicts).
  - Wrap the body in try/except and set a fallback for every variable.
  - Write strings, not booleans, for routing flags.
- Templates hold placeholders (`__HOLIDAYS__`, `__BANDS__`, …) that `generate.py` fills from `spec.json` using the C14 injection (`json.loads(repr(json.dumps(obj, indent=1)))`), never with raw JSON literals.

## 6. Spec and facts

The authoritative contract is **DEV_PLAN.md §2.3**: Fact, Conflict, resolution rules, and a Spec made of closed executable parameters with `fact_ids` on every leaf. Do not maintain a second copy here.
- Do not assume identity fields are dob or phone. The persona code in `run_cases.py` also knows `postcode`, `birth_year`, `company_number` and `founded_year`.
- If a value is unknown, apply the stricter default and log it in the trace.

## 7. Phone-agent skeleton (generated)

The full reference graph is in DEV_PLAN.md §2.4. In short:

```
opening → route_opening (code) → identity_q{i} [verify_identity, field baked; post-hook per-step flag] → load_account (api) → account_facts (code)
→ state_debt → negotiation_router (code) ⇄ negotiate → readback → readback_router (code)
→ promise_guard (code) → do_promise (api, baked) → promise_result (code; 1 retry) → say_recorded
→ wrap_up (code: pre-close check, close_key) → goodbye (per S5) → close_<key> (api, literal body) → end_<key> (end_call none)
third_party → callback_check (code) → do_callback (api); special intents → routers → do_transfer / do_note (api)
```

In Brief B mode, the routers loop per product (`cur_idx`); the read-back is combined; the write loop and note loop run per product; on transfer no notes are added.

## 8. Testing

- **Gold specs:** write them by hand for Brief A and B; measure Extract field by field.
- **Mock raw briefs:** rewrite A with changed values as mail + policy + memo + code list. Memos must not say "supersedes", and include discussion threads that decide nothing.
- **Rules no PUB case tests** (checked against the scripts and judge checks). Write own cases for these, ordered as in DEV_PLAN T8.2:
  - **Top 6:**
    - 40: dispute
    - 42: asks for a human, insists
    - 13: day/month swapped
    - 27: amount below the floor
    - 32: support transfer accepted
    - 45: says twice they do not want to talk
  - **Then:**
    - 8: wrong number
    - 9: deceased
    - 3: unclear confirmation
    - 7: callback outside the window
    - 15: declines identity questions
    - 22: "next Friday"
    - 20: weekend date
    - 23: refuses the deadline
    - 26: refuses the floor
    - 35-36: change at read-back; request to change a recorded promise
    - 43-44: "is this a scam?"; question the agent cannot answer
    - transfer after a recorded promise
    - B8: no promise at all
    - B9: dispute on one product
    - B10: restructuring after a recorded promise
    - B closing aggregation
- **Already covered:** rules 30-31 (PUB-12: two attempts on the late-band loan); rule 32 with the transfer declined (PUB-05); rule 37 with a single failure (PUB-10).
- **Static tests only:** rule 37 failing twice, other calendar days, and the rule 30 exception (every bank session runs on a Wednesday).
- **Test oracle** comes from the brief (gold spec, invariants), never from the agent's output. A failing assertion is never relaxed to match the agent.

---

## 9. Research basis

**τ^τ-Bench** (arXiv 2609.04611; Sierra and Princeton). The user received it as recommended reading; it is **not** listed on the hackathon page.
- Coding agents building customer-service agents: best 23.9% vs an 82.2% expert ceiling.
- Failure modes:
  - searching the records instead of reading them
  - no client questions (not applicable here)
  - shipping the first design that runs
  - rewriting starter code without measuring it
  - missing quiet API defects
  - ignoring printed budget numbers
  - self-tests that encode their own blind spots
  - cheating attempts in 17-42% of runs
- Their artifact generation hides supersession (no "this supersedes") and adds distractor threads.
- A hint to "route by intent, review tool calls" doubled one score (31% → 67%).

**Deep research, 2026-10-10** (22 sources, 13 claims kept, 4 refuted). Mostly 2026 single-team preprints with small samples: the direction is consistent, the size is uncertain.
- PolicyGuide (2608.19861), STAGE (2608.22538): external graph and state tracking; code transitions; node-scoped policy. Pass^k +20-65 points.
- ToolGuards (2507.16459), PCAS (2602.16708): deterministic pre-write guards beat prompt policy. Effect sizes come from violation-heavy subsets.
- WikiContradict (2406.13805): LLMs answer conflicts one-sidedly → separate conflict output plus code precedence.
- BPRF (2505.18542): rule relations and operators are weak (operator F1 0.43-0.64) → reasoning model plus code re-parse.
- ReqGenX (2607.16564): extraction coverage varies → sentence-to-fact coverage check.
- Executable Governance (2512.04408): rule JSON with provenance and scope (no precedence fields; we add them).
- SYNTACT (EMNLP 2025 Industry): clarify → plan → template pipeline is more consistent.
- Fabrication after tool failure (2609.14758): an explicit OK/FAILED status cut dishonest answers from 14.1% to 0.9%.
- ADIAS (2608.06410): a persistent issue ledger in the iteration loop (applied by analogy).
- **Refuted, do not rely on:**
  - PolicyGuard improved every agent
  - a judge+repair pass raises extraction F1
  - atomizer faithfulness of 0.96-0.99
  - ADIAS headline gains
- **No evidence found on:** user simulators, judge reliability, spoken number and date parsing, collection-call verification and read-back conventions. These rest on our own tests.

## 10. Open questions / to verify

The platform questions are spikes S1-S10 in DEV_PLAN.md Phase 1; record the answers in §3c. Still open beyond those:
- Do own case files that reuse PUB customers work with `run_cases.py` and score correctly? Verify on one case first.
- How does the hidden tool API differ (identity fields, outcome codes, call variables)? Handle it at build time from the file, never by hand.
- The Freya unit-test API and chat fork are optional (P2).

## 11. Checklists

The schedule, the cut order and the definition of done are in DEV_PLAN.md §3 and §6. The Sunday runbook is DEV_PLAN.md Phase 11.
- **Key steps before the freeze (Sun 15:00 UTC):**
  - rotate and purge the keys
  - gold spec A
  - generator MVP
  - extraction
  - B
  - static tests
  - CLI, trace and export
  - evaluation loop
  - reproducibility and isolation checks
  - tag `pre-final`
- **Final (Sun 17:00-20:00 UTC):**
  - run the builder once per hidden brief with no manual step
  - fix crashes generically only
  - no probing
  - export to `submission/`
  - commit with no keys
  - send the form before 20:00

## Changelog
- 2026-10-10: created from the planning conversation (pipeline design, τ^τ-Bench lessons, deep research) and checked against the hackathon page.
- 2026-10-10: corrections C1-C10 added with DEV_PLAN.md; D1, D7 and D9 updated.
- 2026-10-10 23:30 UTC: spikes S1-S9 done (§3c); G2, goodbye mechanism (ii) and date-parts capture decided.
- 2026-10-10 23:00 UTC: DEV_PLAN v2 after the adversarial review. Added C11-C14, the security note (§3a), the corrected coverage list (§8) and the own-case constraints (D17); G2 is now the target guard and C7 uses per-outcome close nodes.
