# DEV_GUIDE: navigation map for the build-the-builder kit

Working notes for developing the builder. Written 2026-10-10 against **kit version 3** (`VERSION` = `3`).
Re-check `VERSION` and the README changelog when the kit is updated, since line numbers below may move.

> **Do not let the builder read this file.** It contains Brief A answers (deadlines, expected outcomes).
> `examples/agent_builder.py` runs Claude with `cwd=KIT`, `setting_sources=["project"]` and Read/Glob/Grep, so anything in this
> folder is reachable. This is NOT named `CLAUDE.md` on purpose (that would be auto-loaded into the builder). Before a final run,
> move this file out of the kit folder, or deny it in the builder's tool permissions.

---

## 0. Status snapshot (2026-10-10)

| Item | State |
|---|---|
| Git | **The kit folder is not its own repo.** The enclosing git root is the home directory (`~`), on `master` with no commits. `git status` lists the whole home dir. Run `git init` inside the kit before relying on git. |
| Python | Default `python3` is **3.9.23** (`/opt/anaconda3/envs/repo`). The README requires **3.10+**. Available: `/opt/homebrew/bin/python3` (3.14.6), conda env **`freyahackathon`** (3.14.2, probably meant for this), `/opt/anaconda3/bin/python3` (3.13.5). |
| `claude-agent-sdk` | Not installed in any interpreter. Needed only for `examples/agent_builder.py`. |
| Env vars | No `FREYA_*` / `ANTHROPIC_*` set in the shell. No `env.sh` yet (copy it from `env.example`). |
| Generated state | None yet: no `.freya-agents.json`, `.personas.json`, `results/`, `traces/` or `out/`. No `.gitignore`. |

---

## 1. What this project is

A hackathon ("Build the Builder"). We write a **builder**: a program that takes a bank's brief (markdown) and a tool API file
(OpenAPI), then **automatically** creates a **phone agent** (a Freya workflow JSON) on the Freya platform.
The organisers run that phone agent against simulated customers.

- **Score** = share of customers handled. No partial credit.
- A customer is handled only when all three of these hold:
  1. **Outcome**: the bank ledger is exactly right (outcome, reason, promises, notes, callbacks, transfers).
  2. **Policy**: the conversation stayed inside the brief.
  3. **Honesty**: the agent never claims something it did not do.
  Item 1 is checked by `tools/score.py` logic. Items 2 and 3 are checked by a judge LLM against the case's `checks`.
- **Tie-breaks:** total promised amount on passed customers, then shorter build time, then earlier submission. So full-amount promises matter.
- **Final round:** two unseen briefs, published Sunday. One is a clean specification. The other is raw bank material (a mail, a policy extract, an amending memo, a code list).
  - Each comes with its own `openapi.json`. The **7 tool names stay the same**, but fields and enums can change.
  - Customers have up to 3 products and are tested on several calendar days, **3 runs each, all 3 must pass**.
  - Customers talk like humans: numbers in pieces, self-corrections, chatter, questions back, numbers in words.
- **The builder must be generic.** After the final briefs open, only bug fixes are allowed. Nothing from a final brief (rule, value, name, holiday) may go into builder code or prompts.

### Hard rules (README "Rules")
- No manual step. Never hand-edit an agent on the platform.
- The phone agent runs on `freya.AGENT_LLM` (`experimental-5`). **Do not change it.** The builder itself may use any model.
- The phone agent may call only the bank tool API. Code nodes and hooks inside the workflow are allowed and expected.
- A workspace holds at most **200 workflows**. Use `save_workflow` (update in place).
- **One simulation at a time per workspace.** A 10-customer run takes 3–11 min. A second `run_cases.py` waits for the first.
- **A builder run on one brief may take 30 min maximum**, including its own tests. In practice that leaves about 2 test cycles.
- **Trace is mandatory** for each run: start and end time, each model call (model plus a one-line purpose), what was created on Freya, and the tests run. Plain text.
- Submit `freya.export_workflow(workflow_id, "<brief>.workflow.json")`. The organisers load the exported file into their own workspace.

---

## 2. File map

| Path | Size | Role | Guide section |
|---|---|---|---|
| `README.md` | 9.6 KB | Rules, scoring, quick start, troubleshooting | §1, §15 |
| `VERSION` | `3` | Kit version | |
| `env.example` | | `FREYA_API_KEY`, `FREYA_API_URL`, `FREYA_BANK_TEAM_KEY` | §4 |
| `freya.py` | 107 lines | Stdlib Freya API client (save, publish, export, simulate) | §5 |
| `tools/run_cases.py` | 121 lines | Runs practice customers, scores them, prints PASS/FAIL | §6 |
| `tools/score.py` | 39 lines | Ledger-based scoring and bank-mock HTTP helper | §7 |
| `tools/openapi.json` | 472 lines | Bank tool API (7 tools). **Changes per final brief.** | §10 |
| `public-test-set.json` | 13 cases | Practice customers: PUB-01..10 (Brief A), PUB-11..13 (Brief B) | §13 |
| `briefs/brief-a.md` | 47 rules | Single-product collections spec | §11 |
| `briefs/brief-b.md` | 11 rules + closing | Multi-product deltas on top of A | §12 |
| `examples/base-agent.json` | 2 nodes | Minimal valid workflow (passed 2/13). It is a pattern, not the answer. | §9 |
| `examples/agent_builder.py` | 52 lines | Example builder (Claude Agent SDK, one skill) | §8 |
| `.claude/skills/build-phone-agent/SKILL.md` | | The example builder's only skill | §8 |
| `docs/workflow-format.md` | 860 lines | Workflow JSON reference | §14 |
| `docs/tools-and-code.md` | 588 lines | Tools, `api_call`, code nodes, hooks, mappings | §14 |
| `docs/api.md` | 350 lines | REST API | §14 |

Generated at run time (all relative to **CWD**, or to ROOT where noted):
- `.freya-agents.json`: slot → {workflow_id, agent_id, version}. Written by `save_workflow`, relative to **CWD**.
- `.personas.json`: persona cache. Written by `run_cases.py`, under **ROOT**.
- `results/log.jsonl`: one line per `run_cases.py` invocation, under ROOT.
- `results/<out>.json`: the `--out` file.
- `traces/<YYYYmmdd-HHMMSS>.jsonl`: SDK message trace from `agent_builder.py`, under KIT.
- `out/<slot>.workflow.json`: where the skill tells Claude to write the workflow.

---

## 3. Architecture and data flow

```text
                 BUILD TIME                                         TEST TIME
 briefs/*.md + tools/openapi.json
          │
          ▼
   [ builder ] ──(LLM + code)──► workflow JSON (out/<slot>.workflow.json)
          │
          ▼
   freya.save_workflow(slot, wf) ──► Freya API: POST /api/v2/workflow (first time)
                                      or PUT + fix agent_config + publish (later)
                                      → {workflow_id, agent_id}
                                                                        tools/run_cases.py <agent_id>
                                                                          │ 1. bank mock POST /v1/practice/sessions {"case": id}
                                                                          │    → variables {customer_id, first_name, last_name, title, now}
                                                                          │ 2. Freya POST /api/v2/personas (cached by hash)
                                                                          │ 3. Freya POST /api/v2/simulations (mode chat)
                                                                          ▼
     Freya simulation: persona LLM (gemini-3-flash-preview) ⇄ phone agent (experimental-5)
                                                       │ api_call tools
                                                       ▼
                         bank mock https://freya-bank-mock.freyavoice.workers.dev/v1/<tool>
                                                       │ writes ledger
                                                       ▼
     run_cases: GET /v1/practice/ledger/<customer_id> → score_ledger()   (outcome check)
                + judge verdict from iteration runs (outcome == "pass")  (policy and honesty)
                → PASS/FAIL per case, slowest-turn stats, results/log.jsonl
```

---

## 4. External services and auth

| Service | Base | Auth | Used by |
|---|---|---|---|
| Freya API | `FREYA_API_URL` (default `https://staging-app.freyavoice.ai`) | `Authorization: Bearer fak_…` and a **browser-like User-Agent** (otherwise Cloudflare returns `error code: 1010`) | `freya.py` |
| Bank tools (7) | `https://freya-bank-mock.freyavoice.workers.dev/v1/<tool>` | **No key.** The `customer_id` in the body is the per-call secret. | The phone agent, through `api_call` |
| Bank practice endpoints | `FREYA_BANK_HOST` (default the same mock host) | Header `x-team-key: $FREYA_BANK_TEAM_KEY` (16+ chars, team-chosen, always the same) and UA `freya-bank-scorer/0.1` | `tools/score.py` `http()` |

Practice endpoints (from the code, not documented elsewhere):
- `POST /v1/practice/sessions` with `{"case": "PUB-xx"}` → `{"variables": {customer_id, first_name, last_name, title, now, …}}`. Each run gets a **fresh customer_id**. The mock sets up identity, products and faults from the case id.
- `GET /v1/practice/ledger/<customer_id>` → `{outcome, reason, promises[], notes[], callbacks[], transfers[], calls[{tool, result, …}]}`.

Env vars:
- `FREYA_API_KEY`
- `FREYA_API_URL`
- `FREYA_WORKSPACE_ID` (optional override)
- `FREYA_BANK_TEAM_KEY`
- `FREYA_BANK_HOST`
- `FREYA_SIM_CONCURRENCY` (default 5)
- `FREYA_AGENT_PROVIDER` / `FREYA_AGENT_MODEL` (organisers only, do not touch)
- `BUILDER_MODEL` (agent_builder, default `claude-opus-5-5`)
- `ANTHROPIC_API_KEY`, or a Claude login

---

## 5. `freya.py`: client reference

| Function | Lines | What it does / gotchas |
|---|---|---|
| `api(method, path, body=None, **params)` | 12–20 | Query params come from kwargs. Returns `data.result` (falls back to the whole body). An HTTP error raises `RuntimeError("METHOD path -> code: body[:1500]")`. Timeout 120 s. |
| `workspace_id()` | 22–29 | Cached. `FREYA_WORKSPACE_ID` env, otherwise the first of `GET /api/v2/workspaces` (`workspaces` / `items`). **The query param name is `workspaceId`** (confirmed here; `docs/api.md` says unconfirmed). |
| `create_workflow(name, wf)` | 31–34 | `POST /api/v2/workflow`. Returns `{workflow_id, agent_id}`. ⚠ It does **not** run the agent_config model fix or publish. Presumably v1 is live, but chat turns may fail until one update (see `update_workflow`). |
| `save_workflow(slot, wf, state_file=".freya-agents.json")` | 36–47 | Creates on the first use of `slot` (name `"<slot> MMDD-HHMMSS"`), then updates in place. **The state file is relative to CWD**, so always run from the kit root, or the same slot creates a new workflow. Returns `{workflow_id, agent_id[, version]}`. |
| `validate_workflow(name, wf)` | 48 | `POST …/workflow?dryRun=true`. Silently strips misplaced fields. |
| `update_workflow(workflow_id, wf)` | 49–64 | (1) PUT the full definition. (2) GET it back (`result.workflow.workflow` is the definition). (3) If `agent_config.llmConfig` ≠ `AGENT_LLM`, patch it and PUT again (otherwise chat and real calls cannot start; simulations still work because of the overrides). (4) List versions and publish the newest if it is unpublished. Returns `versionNumber`. |
| `export_workflow(workflow_id, path)` | 65–68 | Writes `{workflow_id, agent_id, updated_at, workflow}`. **This is the submission artifact.** |
| `create_personas(personas)` | 69 | `POST /api/v2/personas`. |
| `get_iteration(sim_id, it_id)` | 70–78 | Pages with `limit=100` until a short page. |
| `get_call(call_id)` | 79–81 | `result.call`. `messages` holds the transcript and system events (`node_enter`, `function_call_*`, `route_evaluated`, `error`). |
| `AGENT_LLM` | 84 | `{"provider": "experimental-5", "model": "experimental-5"}`. **Frozen.** |
| `SIM_LLM` | 85 | `google / gemini-3-flash-preview` (persona and judge). |
| `run_simulation(agent_id, name, vars_by_persona, max_seconds=420, concurrency=5)` | 87–106 | Retries every 30 s while the error contains `"concurrent simulations"`. Polls every 10 s until `completed/failed/paused`. ⚠ The docstring says it returns 2 values; **it actually returns 3**: `(sim_id, iteration_id, status)`. Passes all 3 agent overrides and `runsPerPersona: 1`. |

---

## 6. `tools/run_cases.py`: practice runner

```bash
python3 tools/run_cases.py <agent_id> [--brief A|B] [--cases public-test-set.json] [--only PUB-01,PUB-04] \
        [--out results/run.json] [--reps 3] [--style pieces|corrects|talkative|asks_back|in_words] [--rerun-if-slow N]
```
- Needs `FREYA_API_KEY` and `FREYA_BANK_TEAM_KEY`.
- `--brief` filters on `case["brief"]`. Brief B cases are only PUB-11..13. **`--brief B` does not include A cases.**
- `--reps N`: a case passes only if **all N** runs pass, matching the final's rule (N=3). Each rep is a whole new simulation, about 3–11 min.
- `--rerun-if-slow N`: organiser option. It discards runs whose median slowest turn is above 10 s and waits 5 min before repeating.

**Persona construction** (`PERSONA` L13–24, `persona_for` L35–47):
- The template rules: speak only words; 1–2 sentences per turn; answer only what is asked; give numbers and dates in one turn; invent nothing; say **"Yes, I confirm."** on a matching read-back; say **"Thank you, goodbye."** on the agent's goodbye.
- Third party (family `"Third party"` or `case.third_party`): "You are NOT {name}…", and the persona will not give security answers.
- Otherwise identity lines come from `case.identity`. Known keys are `date_of_birth` ("say it in words"), `phone_last4`, `postcode`, `birth_year`, `company_number` and `founded_year`. Other keys are said generically. ⇒ **The final briefs may ask other identity questions** (postcode, birth year, company number, founded year…).
- `STYLES` L27–33 are appended to the prompt. `talkative` mentions a **cousin's wedding on the 30th**, which is a distractor and never a payment date.
- `successCriteria` = `"All of these are true:\n- " + checks`.
- Tags: `["hackathon", "brief-X"]`.
- Personas are cached in ROOT `.personas.json`, keyed by `"<id>:<sha1(spec)[:10]>"`. They are recreated when the text or style changes.

**`run_once`** (L84–119):
1. One practice session per case. Its `variables` become the simulation's `customerVariablesMap`.
2. `run_simulation`.
3. Judge runs are mapped by `personaId`.
4. Per case: `score_ledger(case, ledger)`. If the judge outcome is not `"pass"`, it appends `"conversation: <reason[:400]>"`.
5. Prints `PASS|FAIL id level family | tool > tool …` (with `verify` / `promise` abbreviations), then the failure reasons (260 chars).
6. Latency: per call it takes the max gap between a user message and the next non-user message. It prints the median and worst, plus the number of failed calls whose `endedReason == "customer-ended-call"`. It warns when the median is above 10 s.

Outputs:
- `results/log.jsonl`: `{at, agent_id, brief, runs, passed, total, seconds, failed[]}`.
- `--out` JSON: `{agent_id, simulation_id, iteration_id, seconds, passed, total, runs, final[], rows (last rep), all_rows}`.
- Each row is `{id, level, family, pass, failed[], call_id, tools[], customer_id, slowest_turn_s, ended}`.

---

## 7. `tools/score.py`: exactly what the ledger must look like

`score_ledger(case, led)` (L17–34). Every mismatch below fails the case:

| Check | Comparison | Implication for the agent |
|---|---|---|
| Outcome | `(led.outcome, led.reason) == (exp.outcome, exp.reason)` | For `promise` / `paid` the expected reason is `null`, so **the ledger reason must be absent/None**. Sending `""` or any string fails. The base agent strips `reason` in `pre_process_code` for promise/paid. |
| Promises | sorted multiset of `(product_id, round(amount,2), date)` | A duplicate `create_promise` (for example an over-eager retry after success) fails. The date must be `YYYY-MM-DD`. The amount must be exact. |
| Notes | sorted multiset of `(product_id, reason)` | `text` is ignored. Brief A expects **no** notes. |
| Callbacks | sorted multiset of `(date, time)` | The time string must match exactly, e.g. `"11:00"` (HH:MM, zero-padded). |
| Transfers | sorted list of `queue` | |
| Last call | `calls[-1].tool == "close_call"` | `close_call` must be the **last** tool call, and it must exist. |
| Order | any `get_account`/`create_promise` whose result has `error == "identity not verified"` fails | Never call them before both answers verify. |
| Not reached | if expected outcome ∈ {`not_reached`, `no_contact`, `unreached`}, any `verify_identity`/`get_account` call fails | With a third party or wrong number, never start the identity check. (`no_contact` / `unreached` hint at outcome names that final briefs might use.) |

CLI: `python3 tools/score.py <case_id> <customer_id>` re-scores a past session.

---

## 8. Example builder and skill

`examples/agent_builder.py`:
- `ClaudeAgentOptions` settings:
  - `cwd=KIT`, `model=$BUILDER_MODEL or claude-opus-5-5`, `skills=["build-phone-agent"]`, `setting_sources=["project"]`
  - `allowed_tools=[Read, Write, Edit, Glob, Grep, Bash]`, `permission_mode="dontAsk"`, `max_turns=150`
  - env `BASH_DEFAULT_TIMEOUT_MS=900000`, `BASH_MAX_TIMEOUT_MS=1200000`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (the test must run in the foreground; the builder stops when Claude ends its turn)
- Prompt: `"Use the build-phone-agent skill to build a phone agent for: <briefs>"`.
- Trace: `traces/<start>.jsonl`. The first line is `{start, briefs, model}`, then every SDK message serialized with `dataclasses.asdict`. The final `ResultMessage` gives turns, duration and cost.
- ⚠ The trace has no explicit **end time** line or "what was created on Freya" summary. The README requires both. Add them in our builder.
- README v3: on Brief A this builder reached 10/10 in one run (not reproducible proof).

`.claude/skills/build-phone-agent/SKILL.md` steps:
1. Read briefs and `tools/openapi.json`.
2. Read the docs.
3. Use `base-agent.json` as a pattern.
4. Write `out/<slot>.workflow.json`: one step per call stage, identity first, **move on tool results, not on what the customer says**, fields and enums from openapi, no `agent_config`.
5. Save with `save_workflow(<slot>, …)`.
6. `run_cases.py <agent_id> --brief A|B` in the foreground.
7. Fix and re-test, **at most 3 times**.
8. Print workflow_id, agent_id and the pass count.

Rules: no hand edits; honesty on tool failure; "prefer rules in routes and code over rules in prompts".

---

## 9. `examples/base-agent.json`: anatomy and weaknesses

It is a platform export (it has `position`, `assertions`, `mode: "exact"`, `interruptible`, `return_to_previous_on_interrupt`, and `null`s). It was accepted by `save_workflow` per the README, even though the docs say `null` fails validation. **Avoid `null` in our own output.**

- `initial_node: "identity"` (conversation node).
  - `on_enter` tts: "Hello, this is the digital assistant of Freya Bank. Am I speaking with {{title}} {{last_name}}?" (⚠ the brief also requires saying the call is **recorded**, which this misses).
  - Tools: `verify_identity` (model fills `field` (enum) and `answer`; `customer_id` baked) and `end_call`.
  - Transition: `verify_identity_response.data.all_verified` equals `"true"` OR `"True"` → `collection`. This is the flattened-key routing pattern.
- `collection` node (conversation).
  - tts: "Thank you, that's verified. I'm calling about your Freya Bank account…".
  - Tools: `get_account`, `create_promise` (model fills `product_id`, `amount`, `date`) and `end_call`. **No transitions.**
  - Prompt includes `Now: {{now}}`.
- `end_call` as a model tool with `message_mode: none`, `interruptible: true`, `trigger_pattern: "Have a good day|have a good day"` (⚠ not documented in the docs, which only list `trigger_pattern_both`), `trigger_timeout: 3` and `trigger_pattern_both: "goodbye|bye|…"`. Its description says "the phrase 'Have a good day.' ends the call by itself".
- **`close_call` is a workflow-level lifecycle tool**, `alwaysRunsAt: ["end_of_call"]`.
  - `outcome` / `reason` default to `{{outcome}}` / `{{reason}}`. Nothing sets them, so **one LLM call after the call fills them** from the conversation.
  - `pre_process_code` pops `reason` when outcome ∈ {promise, paid}.
  - ⚠ The enum lacks `paid` and `transferred`, and the reason description covers only a few reasons.
- `test_variables` lack `customer_id`.

Why it gets only 2/13: it has no `transfer_to_agent`, `schedule_callback` or `add_note`; no date or deadline logic; no third-party handling; the "recorded" disclosure is missing; and the outcome is guessed by the LLM.

Useful patterns to keep:
- The lifecycle `close_call` guarantees it is the last ledger call.
- The `pre_process_code` reason strip.
- Flattened `_response.data.*` routing with both boolean spellings.

---

## 10. Bank tool API (`tools/openapi.json`, v0.3-draft)

Server: `https://freya-bank-mock.freyavoice.workers.dev/v1`, all `POST` with a JSON body.

Shared response facts:
- Every tool returns 200 `{ok, error}`, where `ok=false` means not carried out.
- A 500 means the service failed and nothing was recorded; the call may be repeated.
- **The mock does not enforce the brief.** It records promises on holidays or past deadlines without complaint.

| Tool | Request (required*) | Response extras | Notes |
|---|---|---|---|
| `verify_identity` | `customer_id*`, `field*` ∈ {`date_of_birth`, `phone_last4`}, `answer*` | `verified`, `wrong_answers_left`, `all_verified`, `hint` ∈ {`day_month_swapped`} | DOB as `YYYY-MM-DD`. An unreadable value gives `ok=false` and does **not** count as wrong. 3 wrong in total ends the check. |
| `get_account` | `customer_id*` | `products[]`: `product_id` (`p1`, `p2`…), `type` ∈ {credit_card, personal_loan, car_loan}, `card_last4` (cards), `past_due`, `days_late`, `minimum_payment` (cards), `instalment_amount` (loans) | Refused (`error: "identity not verified"`) until both questions pass. |
| `create_promise` | `customer_id*`, `product_id*`, `amount*` (number), `date*` (date) | `promise_id` | One per product. PUB-10 injects `fail_first_n: 1`; whether that shows as 500 or `ok=false` is unknown, so handle both. |
| `add_note` | `customer_id*`, `product_id*`, `reason*` ∈ {refused, hardship, dispute, paid, service_error}, `text` | | Brief B only. |
| `schedule_callback` | `customer_id*`, `date*`, `time*` ("HH:MM") | | |
| `transfer_to_agent` | `customer_id*`, `queue*` ∈ {restructuring, general, support} | | |
| `close_call` | `customer_id*`, `outcome*` ∈ {promise, paid, transferred, no_promise, not_verified, not_reached}, `reason` | | The reason is required except for promise and paid. Always the last call; nothing is accepted after it. |

Raw `api_call` result envelope seen by hooks and mappings: `{status, data: <body above>, message, status_code, header}`.
Mapping paths start with `data.`. Auto-flattened variables are `<tool>_response.data.*`, `<tool>_args.*`, `<tool>_success_count` and `<tool>_failure_count`.

---

## 11. Brief A: rule index (single product)

Call variables: `customer_id`, `first_name`, `last_name`, `title` (Mr/Ms), `now` (e.g. `2026-10-14T11:00`, **always use this, never the clock**).

| § | Rule | Gist |
|---|---|---|
| Opening | 1 | First sentence: digital assistant calling from Freya Bank, **call is recorded**. No "collections / debt / payment / product" before verification (relatives included). |
| | 2 | "Am I speaking with {title} {last_name}?" |
| | 3 | Only yes / that's me / speaking / own name confirms. "Hello / go ahead / who is this" does not; ask again. Still unclear after the 2nd ask → `not_reached/unclear`. Answer a customer question first (rules 4, 43); the ask after that is the 2nd. |
| | 4 | "Robot/AI?" → "Freya Bank's digital assistant", then continue. |
| Third party | 5 | Say nothing beyond the opening; ask when the customer can be reached. |
| | 6 | Callback: **today or the next business day, 10:00–19:00 inclusive, later than `now`** → `schedule_callback`, then `not_reached/callback`. |
| | 7 | Outside the window → ask once for another time; outside again → `not_reached/no_callback` (no schedule). |
| | 8 | Not the customer's number → `not_reached/wrong_number`. |
| | 9 | Customer died → "I am sorry for your loss." Ask nothing → `not_reached/deceased`. |
| | 10 | A relative gets no security questions and no account info, even if offering to pay. |
| Identity | 11 | DOB first, then phone last 4, one at a time, each through `verify_identity`. DOB → `YYYY-MM-DD`. A numeric-only date is read **day, month, year**. |
| | 12 | Re-asking is allowed. **3 wrong in total** ends the check. |
| | 13 | `hint: day_month_swapped` → ask for the month as a word. That retry is not counted as wrong. |
| | 14 | 3 wrong → no debt info, refer to the mobile app or a branch → `not_verified/failed`. |
| | 15 | Refuses → explain once that the questions protect the account. Refuses again → `not_verified/declined`. Asking "what's this about" instead of answering counts as a refusal. |
| Debt | 16 | After both pass → `get_account`. |
| | 17 | Say collections team / late payment. Product in words: "credit card ending 4821", "personal loan", "car loan". Give the past-due amount and the days late. |
| Dates | — | Business days = Mon–Fri minus holidays 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01. |
| | 18 | `days_late` 1–7 = **early**: deadline = **12th** business day after today, **1** persuasion attempt. 8–45 = **late**: **7th** business day, **2** attempts. |
| | 19 | Promise date: ≥ today, a business day, ≤ deadline. |
| | 20 | Weekend/holiday on or before the deadline → offer the next business day. After the deadline → rule 23. |
| | 21 | Vague period → ask once for the exact day. Still none → propose the deadline. |
| | 22 | "next <weekday>" = following calendar week; "this <weekday>" = current week. |
| | 23 | After the deadline → say the deadline is the latest and offer it. Refused → flat refusal (rule 30). |
| Amounts | 24 | Ask the full past-due amount first. **Never ask "how much can you pay?"** The agent proposes every amount. |
| | 25 | Floor = `minimum_payment` (card) or `instalment_amount` (loans). |
| | 26 | "Too much" → offer the floor **once**, saying the rest stays overdue. Refused → flat refusal. Attempt 2 may name the floor again on the deadline. |
| | 27 | Customer amount in [floor, full] → accept. Below the floor → cannot record; offer the floor once; not accepted → flat refusal. |
| Promise | 28 | First ask: "Can you make this payment today?" |
| | 29 | A proposed date or amount is never a refusal. |
| | 30 | Flat refusal or non-answer = 1 attempt ("no to today" with no date or amount = flat refusal). **Attempt 1**: the last business day of this week (if today is that day → the last business day of next week), for the full amount, or the floor if "too much" was already said. **Attempt 2** (late band only): the floor on the deadline. |
| | 31 | Attempts used up → stop; never repeat a refused offer → `no_promise/refused`. |
| | 32 | Illness / death in the family / job loss → one sympathy sentence, **no persuasion**, offer the support team. Accept → `transfer_to_agent(support)` → `transferred/support`. Decline → `no_promise/hardship`. Takes priority over rules 30 and 41. If the customer still names a date or amount themselves → record it under §7–8. |
| | 33 | Never offer a discount, waiver, plan or any off-brief term. |
| Confirm | 34 | Read back product, amount and date, then "Do you confirm?" `create_promise` only after a clear yes. |
| | 35 | A change at read-back → re-validate and read back again. |
| | 36 | One promise per product. It cannot be changed in the call → mobile app. |
| | 37 | Say "recorded" only after `ok: true`. On failure retry once. Fails again → say it could not be recorded → `no_promise/service_error`. |
| | 38 | After recording: **"You will receive a text message confirming this promise."** |
| Other | 39 | "Already paid" → payments can take one business day to appear. No promise → `paid`. |
| | 40 | "Not mine" / "never had it" / "closed or paid off in the past" → don't argue → `no_promise/dispute`. |
| | 41 | New plan / lower instalments → don't describe a plan → `transfer_to_agent(restructuring)` → `transferred/restructuring`. |
| | 42 | Asks for a human → ask once if you can help. Insists → `transfer_to_agent(general)` → `transferred/human`. Applies before and after verification. |
| | 43 | "Scam?" → they can verify by phoning Freya Bank customer service, then continue. |
| | 44 | Unknown info → say you don't have it. Never invent. |
| | 45 | "Don't want to talk" twice → `no_promise/refused`. Before verification → `not_verified/declined`. |
| Close | 46 | Exactly one `close_call`, the last tool call. If a transfer follows a recorded promise → `transferred` with that transfer's reason. **Brief A never uses `add_note`.** |
| | 47 | Thank the customer and say goodbye **before** `close_call`. |

Outcome table:

| Outcome | Reasons |
|---|---|
| `promise` | none |
| `paid` | none |
| `transferred` | restructuring, human, support |
| `no_promise` | refused, hardship, dispute, service_error |
| `not_verified` | failed, declined |
| `not_reached` | callback, no_callback, wrong_number, deceased, unclear |

---

## 12. Brief B: deltas (up to 3 products)

1. `get_account` returns 1–3 products, each with its own `past_due`, `days_late` and floor.
2. State **every** late product, one sentence each, before asking anything.
3. Band and deadline are **per product**.
4. Ask "pay all today?" once. If not, go product by product **in `get_account` order**, without re-asking about today. Each product starts at attempt 1.
5. Persuasion attempts are counted per product.
6. One date for everything that exceeds one product's deadline → that product gets **its own deadline** (say so in the read-back); the others keep the named date.
7. **One combined read-back and one confirmation**, then one `create_promise` per product.
8. Each product without a promise → `add_note(product_id, reason ∈ refused|hardship|dispute|paid|service_error)`, even when no product got a promise.
9. Dispute or "already paid" on one product does not end the call. Note it and continue.
10. Restructuring → still transfer. Already-recorded promises stay; agreed but unrecorded ones are not recorded → `transferred/restructuring`. **On any transfer (restructuring, support, human), add no notes at all**, before or after.
11. One `create_promise` fails twice → keep the recorded ones; `add_note(service_error)` for the failed product.

Closing:
- With no promise recorded: all notes `paid` → `paid`. Otherwise `no_promise` with the reason of the **first product in `get_account` order whose note is not `paid`**.
- `promise` wins whenever at least one promise was recorded, except for rule 10 (transfer).

---

## 13. Public test set: what each case demands

All cases have `now = 2026-10-14T11:00` (**Wednesday**). Computed calendar:
- Late-band deadline (7th business day) = **Fri 2026-10-23**.
- Early-band deadline (12th business day, skipping the Mon 10-26 holiday) = **Mon 2026-11-02**.
- "Last business day of this week" = **Fri 2026-10-16**. Next business day = Thu 2026-10-15.

| Id | Brief | Family / level | Product(s) (`days_late` → band) | Behaviour | Expected ledger |
|---|---|---|---|---|---|
| PUB-01 | A | Happy path / easy | card 4821, 420.00, 6d (early), min 126 | Pays full today | `promise`; p1 420.0 @ 2026-10-14 |
| PUB-02 | A | Third party / medium | personal loan 310.5, 11d | Husband; asks why, offers to pay; Maria reachable tomorrow ~11 | `not_reached/callback`; callback 2026-10-15 11:00; **no verify or get_account** |
| PUB-03 | A | Identity / medium | card 0377 | 3 wrong DOBs (1991-07-12, 1992-08-21, 1990-07-21), then asks the amount | `not_verified/failed`; nothing disclosed; app/branch |
| PUB-04 | A | Dates / medium | car loan 1250, 14d (late), inst 400 | Wants 6 Nov (salary); asks "robot?"; accepts the latest date | `promise`; p1 1250.0 @ **2026-10-23** |
| PUB-05 | A | Hardship / medium | personal loan 780, 21d | Lost job; asks a discount; declines transfer | `no_promise/hardship`; no persuasion; support offered once |
| PUB-06 | A | Amounts / hard | card 1903, 2125.10, 12d (late), min 637.5 | Full is too much; "you tell me"; accepts the minimum this Friday | `promise`; p1 637.5 @ 2026-10-16 |
| PUB-07 | A | Dates / hard | personal loan 540, 5d (early) | "Week after next", then "Monday the 26th" (holiday); accepts the next business day | `promise`; p1 540.0 @ **2026-10-27** |
| PUB-08 | A | Already paid / medium | card 5512, 180 | Paid in the app this morning | `paid` (reason None) |
| PUB-09 | A | Restructuring / medium | personal loan 2100, 28d | Wants lower instalments | `transferred/restructuring`; transfer `restructuring` |
| PUB-10 | A | Tool failure / hard | card 7740, 365, 8d (late) | Can't pay today; full this Friday. **`create_promise` fails the first time** | `promise`; p1 365.0 @ 2026-10-16; exactly one promise; no "recorded" before success |
| PUB-11 | B | Multi / medium | card 220 (9d late), PL 640 (9d late), car 75 (3d early) | All three this Friday; confirms once | `promise`; p1/p2/p3 @ 2026-10-16 (220, 640, 75) |
| PUB-12 | B | Multi / hard | card 510 (16d), PL 1320 (16d), car 140 (7d early) | Phone 4401 then 4410 (re-ask the phone only); card tomorrow; refuses the rest | `promise`; p1 510.0 @ 2026-10-15; notes p2 refused, p3 refused; 2 attempts on PL, 1 on car |
| PUB-13 | B | Multi / hard | card 300 (4d early), PL 900 (20d late) | Both on 30 Oct; accepts the loan's earlier date | `promise`; p1 300 @ 2026-10-30, p2 900 @ 2026-10-23; read-back names both dates |

The identity answers for each case are in `public-test-set.json` → `identity`. The persona says the DOB in words.

---

## 14. Platform knowledge: condensed gotchas with doc pointers

**`docs/workflow-format.md`**
- L13–36: each turn makes 3 independent LLM calls: extraction → routing → dialogue. Routing never sees `task_message`. Deterministic conditions need no LLM.
- L38–66: top-level keys. **No `null`.** Omit `agent_config`. Body shape `{name, workflow}`.
- L68–84: node types `conversation` / `api_request` / `code` / `end_call`. `tools` survive only on conversation nodes, `pre_actions` only on api_request and code nodes, and both are **stripped silently** elsewhere.
- L86–113: node field table (`max_node_turns` default 10, `truncation_*`, `reasoning_override`, …).
- L117–164: prompt = `system_prompt` + `role_message` + "## Current Task" + `task_message`. `on_enter` types are llm, tts, silent and audio. `on_enter_first_entry_only`.
- L176–242: one global variable table. `{{var}}` and `{{var:json}}`. An unresolved var stays literal in prompts and tts. In engine-run calls a lone `"{{x}}"` field is **dropped** while a mixed string keeps the literal. System vars at L223–238. There is **no `{{current_date}}`**; use the `now` call variable.
- L244–277: `context_variables` was **lost on an API save (10 Oct)**. Don't use it.
- L279–311: operators `equals`, `not_equals`, `greater_than`, `less_than`, `contains` (case-insensitive), `is_set`, `is_not_set`, `always`, `matches_intent`.
- L313–368: variable conditions go in a top-level `{"logic": "or", conditions: […]}`. AND is nested inside the OR.
- L370–391: **never route on booleans** (`"True"` vs `"true"`). Use string flags or test both.
- L393–412: order: loop_condition → transitions in order (deterministic first) → global nodes → stay. Same-target transitions are merged into an OR. Routing re-runs after tool results (same turn).
- L414–460: `routing_prompt`, self-transition with `always`, `loop_condition` / `loop_prompt`, `is_tool_call` (`transition_to_<node>` tool).
- L462–484: passthrough nodes need `passthrough_default_transition` and a final `always` transition, or they **deadlock**. A code node can be `initial_node`.
- L486–526: global nodes: `condition`, `excluded_nodes`, `__previous__`.
- L528–609: `extraction_schema` types (`string`, `integer`, `float`, `boolean`, `date`, `datetime`, `name`, `phone_number`), `enum_values`, `validation_pattern`, **`min_confidence` default 0.95** (set it lower, e.g. 0.7). A custom `extraction_prompt` replaces everything and needs the `{{extractor.*}}` placeholders. Use `date` type for dates. Forking on an extracted enum beats competing intents.
- L611–656: `end_call` node. The farewell comes from `terminal` (`message_mode` custom / llm / none). **`endedReason` = `terminal.function.name`.** `interruptible` needs `trigger_pattern_both`.
- L658–674: `max_node_turns` does nothing without `max_turn_transition`. Truncation applies to dialogue only.
- L686–860: full clinic example.

**`docs/tools-and-code.md`**
- L7–76: tool shape. Handlers `api_call`, `code_exec`, `end_call`. `api_call` params are `url`, `method`, `headers`, `body` and `connect_retries`.
- L78–99: **`default` bakes, `const` never sends.** Baking happens at node entry. A `{{x}}` default with x unset → the model fills it. Model args land in `<tool>_args.<field>`. Don't name a model-filled field like an already-set variable.
- L101–109: body fields are leaves under `body.properties`, each with its own default, description and enum. Never a single `body.default` object.
- L111–118: unset var → field dropped; `""` → sent empty; in `code` → a literal `{{var}}` crashes Python.
- L120–141: constrain model-filled params with `enum`, or with an index number plus a hook.
- L143–209: `pre_actions` = engine-run on entry, `response_mapping` at **node** level. `tools` = model-run, `response_mapping` **on the tool**.
- L211–221: tool descriptions must be imperative triggers ("CALL it when…"). One tool per message; speak after each result. "The function X is not currently available" = a tool not listed in that node.
- L223–287: result envelope; **mapping paths start with `data.`**; auto-flattened keys; booleans arrive as strings; the exact form of mapped lists in `vars` is unclear, so read defensively.
- L289–345: routing on tool results fires the same turn. Counters `<node|tool>_success_count/_failure_count`. `suppress_tool_results`. Background tools (`interruptible:false`) need an `is_set` gate.
- L347–365: `timeoutMs`, `maxRetries` (**0 for writes**), `connect_retries` (a baked param, max 5), code `timeout_ms` 30000.
- L367–416: hooks (`api_call` only). `pre_process_code` gets `vars` and `config` (url, method, headers, body). `post_process_code` gets `result` (the **envelope**). The **`what_to_do_next`** injection pattern fixes silent agents and ignored failures. Wrap hooks in try/except. Hooks can read and write vars (seen 10 Oct).
- L418–508: code nodes run `code_exec` in `pre_actions`. Read and write through `vars`. **No `{{`/`}}` in code.** Never raise. Write string flags. `json`, `re` and `datetime` work. Automatic keys are named after the **node**. Use code for dates and arithmetic.
- L510–512: `code_exec` as a model tool is unverified.
- L514–564: lifecycle tools (`alwaysRunsAt` `start_of_call` / `end_of_call`; `each_turn` never fires). Unresolved params → one LLM fill. `end_of_call` gets no `response_mapping`. End-of-call order: analysis → end_of_call tools → judging. `{{call.analysis.summary}}` and friends are available.
- L566–575: an agent going silent after a tool result, or ignoring negative results, is fixed by the post-hook `what_to_do_next` plus a prompt rule.
- L577–588: checklist.

**`docs/api.md`**
- L9–46: base URL, auth, User-Agent, envelope `data.result`.
- L50–127: create, `dryRun`, **PUT replaces everything and does not publish**, publish through the versions route, `agentVersionNumber` on runs.
- L141–176: personas. L178–238: simulations (pass all 3 agent overrides; poll every 10 s).
- L240–252: **`POST /api/v2/chat/message`** `{workflowId, message, customerVariables}` → `{response, callId}`. Continue with the same `callId`; end with `POST /api/v2/chat/end`. It may skip a first code node. A 500 means the workflow cannot start. A 504 can happen on a long turn.
- L254–290: iterations and runs (`outcome`, `reason`, `callId`, `turnCount`; paged 30 by default, 100 max).
- L292–336: `GET /api/v2/call/{id}` → `messages` (role assistant/user/system), system events. **`route_evaluated` carries the branch results and `variable_table`.** `workflowSnapshot.variableTable`.
- L338–349: the minimal loop.

---

## 15. README troubleshooting (verbatim essentials)
- `error code: 1010` → missing browser UA (`freya.py` sets one).
- `Workspace plan limit reached` → too many workflows; update in place.
- The score doesn't move → the update was not published (`save_workflow` publishes; a plain PUT doesn't).
- Unknown failure → `freya.get_call(call_id)["messages"]`. `--out` saves the call ids.
- `customer-ended-call` early → the agent was too slow or silent. Check the median slowest turn. A busy model is not your fault.
- See what the agent says quickly → `POST /api/v2/chat/message`.
- `unknown product_id` → the model invented an id. Ids come from `get_account` (`p1`, `p2`, …); feed them through the result or fill them in with code.
- A simulation is stuck "running" with no call → the workflow cannot start. Try a chat turn. Leave `agent_config` out.
- Silent after a tool call → `tools-and-code.md` "Tool results and the next turn".

---

## 16. Discrepancies, risks and open questions noticed

1. `freya.run_simulation` docstring says 2 return values; it returns 3.
2. `save_workflow` state file is relative to CWD. Running from another dir creates a duplicate workflow and wastes the 200 quota.
3. `create_workflow` does not set the agent_config model or publish. The first chat turn after a fresh create may fail until one `update_workflow`. To be safe, call `save_workflow` twice on first creation, or call update right after create.
4. `base-agent.json` contains `null`s and undocumented fields (`trigger_pattern`, `assertions`, `mode`, `position`, `interruptible` on a node, `return_to_previous_on_interrupt`). The docs say `null` fails. Don't emit `null`.
5. `close_call` reason for promise/paid must be **absent** (None) in the ledger. Verify how the mock stores `""` vs missing. The base agent's pre-hook pop is the safe pattern.
6. `create_promise` fault injection (`faults.fail_first_n`) is either a 500 or `ok:false`, unknown which. `maxRetries` on the tool would auto-retry a 500. If it does, the brief's "try once more" is satisfied invisibly, but honesty and counting become murky. Prefer `maxRetries: 0` with an explicit retry policy driven by the counter or result.
7. With a `close_call` lifecycle tool whose outcome is unresolved, an LLM guesses the outcome after the call. A deterministic variable set during the call (`outcome`, `reason`) is safer: it is baked, so there is no LLM guess.
8. The judge (gemini-3-flash) reads the transcript against `checks`, so exact phrasing matters (for example the text-message sentence, "recorded", "digital assistant").
9. The agent model `experimental-5` can be slow. A long prompt, many tools or extra LLM turns add latency → customer hang-ups. A median above 10 s is a warning sign.
10. `scorer.not_reached` checks also mention the outcome names `no_contact` / `unreached`. Final briefs may rename outcomes, so take them from the brief and openapi.
11. `run_cases.persona_for` knows the identity fields `postcode`, `birth_year`, `company_number` and `founded_year`. **The finals may use different security questions** (even a company/business customer). Read the field enum from the final openapi.
12. Python 3.9 is the default here; use a 3.10+ interpreter (e.g. `conda activate freyahackathon`).
13. Brief A ambiguity to watch: a weekend or holiday attempt-1 date (e.g. a Friday holiday) means "last *business* day" of the week, so step back. If today *is* that day, use next week's.
14. Brief B rule 6 vs rule 4: "one date for everything" is given after the "all today?" ask. Products keep the named date unless it is past their own deadline.

---

## 17. Design implications for our builder (generalization)

Everything below must be **derived from the brief and openapi at build time**, never hardcoded:
- Holidays, business-day definition, band thresholds, deadline offsets, attempt counts, floor field names
- Identity questions, their order, date formats and the wrong-answer limit
- The callback window
- Outcome and reason names and the closing table; tool fields and enums; queue names
- Exact mandated sentences

The README warns that the final briefs may be **raw material** (mail plus policy extract plus an amending memo plus a code list). The builder must merge amendments, and later documents override earlier ones.

Patterns that look strongest given the docs:
- **Deterministic logic in code nodes or hooks:** business days, deadlines per product, attempt-1 date, floor, band and attempt budget, combined read-back text, and the final outcome/reason computation. Feed the LLM finished facts (`date_facts`-style multi-line strings).
- **Inject `what_to_do_next` via post-hooks** on every bank tool. Strip `header`. Expose product ids from `get_account` so the model never invents them.
- **Route on tool results** (flattened `_response.data.*` keys, string flags), not on customer speech.
- **`close_call` stays last**: either a lifecycle `end_of_call` tool with baked `{{outcome}}`/`{{reason}}` set during the call, or an explicit in-call tool followed by an `end_call` node. Strip `reason` for promise/paid.
- **Honesty:** the agent says "recorded" only after `ok:true`. Retry once and note `service_error`.
- **Test with `--style`** variants and `--reps 3`. One green run is only a hint.
- **Builder budget:** 30 min including tests. A full 13-case run takes 3–11 min, and only one simulation runs per workspace. Use `chat/message` for fast smoke tests, and `--only` subsets.
- **The trace must include:** start and end time, every model call with its purpose, workflows created or updated (ids and versions), and test runs with results.
- **Submission:** `freya.export_workflow(wf_id, "<brief>.workflow.json")`.

---

## 18. Command cheat sheet

```bash
cd ~/Desktop/build-the-builder            # ALWAYS run from here (save_workflow state is CWD-relative)
conda activate freyahackathon             # Python 3.10+; or use /opt/homebrew/bin/python3
cp env.example env.sh && $EDITOR env.sh && source env.sh

# save / update + publish a workflow file under a slot
python3 -c "import freya,json,sys; print(json.dumps(freya.save_workflow(sys.argv[1], json.load(open(sys.argv[2])))))" brief-a out/brief-a.workflow.json

# validate only
python3 -c "import freya,json,sys; print(freya.validate_workflow('x', json.load(open(sys.argv[1]))))" out/brief-a.workflow.json

# run practice customers
python3 tools/run_cases.py <agent_id> --brief A --out results/a.json
python3 tools/run_cases.py <agent_id> --only PUB-10,PUB-07 --style corrects
python3 tools/run_cases.py <agent_id> --brief B --reps 3

# inspect a failed call
python3 -c "import freya,json,sys; c=freya.get_call(sys.argv[1]); print(c['endedReason']); [print(m['role'], m.get('nodeId'), m['message'][:300]) for m in c['messages']]" <call_id>

# re-score a session from the ledger
python3 tools/score.py PUB-04 <customer_id>

# export for submission
python3 -c "import freya; freya.export_workflow('<workflow_id>', 'brief-a.workflow.json')"

# example builder
pip install claude-agent-sdk && python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md
```
