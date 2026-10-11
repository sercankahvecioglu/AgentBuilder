# What is done: Track B (extraction + verify)

Written 2026-10-11 by the Track B agent. Branch `sercan-dev`, last Track B commit `8eb4182`.
Track B is the half of the builder that reads the bank's material and turns it into `spec.json`
(the contract in DEV_PLAN.md §2.3) which Track A's generator turns into the phone agent.

## 1. Results

Extraction scores against the hand-written gold specs (`dev/eval_extract.py`, exact-class leaves):

| Brief | First run | Final | Target (T3.4) |
|---|---|---|---|
| Brief A | 96.0% | **99.7%** (354/355) | ≥ 95% |
| Brief A+B | 90.7% | **99.7%** (369/370) | ≥ 95% |
| Raw-material mock (`dev/mock_briefs/raw1`) | 94.7% | **99.4%** (356/358) | ≥ 90% |

On the raw mock the conflict handling did what the hidden raw brief will need: the memo's three silent changes
(band range, deadline, callback window) won over the older policy, the window change took effect as a
date-conditional value from its effective date, the added holiday was merged, and the discussion thread was ignored.
Verify caught one wrong value in each Brief A run and the automatic re-extract fixed it.

All 30 unit tests pass (`python -m pytest dev/tests -q`). The literal audit (`dev/audit_grep.py`) is clean on Track B files.

## 2. What was built

### Contract and gold (Phase 2)
- `builder/schema.py`: pydantic `Fact`, `Conflict`, `Document`, `Extraction` (stage 1a) and `Spec` (~370 leaves, every leaf
  with `fact_ids`). The JSON Schema compiles under the structured-output limits (checked live: `python -m builder.llm --schema-check`).
- `dev/gold/brief-a.spec.json`, `dev/gold/brief-ab.spec.json` (built by `dev/gold/make_gold.py`): every Brief A rule 1-47 and
  Brief B item 1-11 + closing maps to a field; coverage table in `dev/gold/README.md`. `dev/gold/*.facts.json` hold one gold fact per rule.
- `dev/eval_extract.py`: leaf-by-leaf comparison in three classes (exact values, free text, behaviour rules), list items
  aligned by key with intent synonyms, precedence scored as an order. Gold vs gold = 100%.
- `dev/mock_briefs/raw1/`: a raw-material rewrite of Brief A (request mail, dated policy extract, later memo that changes
  three values without saying "supersedes", code list, discussion thread), a mock tool API with other identity fields and
  queues, and its gold spec.

### Extraction (Phase 3)
- `builder/llm.py`: one structured-output call contract with two backends. `api` = Anthropic Messages API
  (`ANTHROPIC_API_KEY`); `agent` = Claude Agent SDK using the machine's Claude login (claude.ai subscription), the same
  route as the kit's example builder. Model `claude-opus-5-5`, explicit effort, no temperature / budget / forced tool
  choice, `stop_reason` checked, one retry on truncation or invalid JSON, one trace line per call.
- `builder/trace.py`: incremental plain-text trace (start/end, model calls with tokens and request id, created objects,
  tests), secrets redacted.
- `builder/inputs.py`: concatenates any text inputs with document labels; parses the OpenAPI file into an operation/field/enum summary.
- `builder/extract.py`: stage 1a prompt (atomic facts with verbatim quotes, document metadata, conflicts listed but not
  resolved), stage 1b prompt (fill the spec from governing facts only, closed vocabulary, tool names from the API),
  pipeline with `--votes N`, verify + one re-extract on errors, and `--facts` to resume from saved stage-1a output.
  The prompts carry no brief values.
- `builder/resolve.py`: deterministic conflict resolution. Discussion never governs; a document that declares it amends
  another wins; else the later date wins (an `effective_from` gives a date-conditional pair); else memo beats policy;
  else the stricter value with a logged unresolved entry. Same-document facts are never rivals, set members (holidays,
  codes) add up, restatements and verbatim wording are never displaced.
- `builder/vote.py`: field-wise majority over N extractions, stricter value without a majority, disputes logged.

### Verify (Phase 4)
- `builder/verify.py`: enums against the tool API (identity fields, queues, note reasons, outcomes, product types,
  account fields), every close pair a row of the outcome table, formats (ISO dates, HH:MM, contiguous bands, attempt
  vocabulary), provenance (every leaf cites an existing governing fact), numbers and times re-parsed from the cited
  quotes (digits and number words), required phrases verbatim in the inputs, unused governing facts warned.

## 3. How to run

From the repo root, with the conda env `freyahackathon`:

    python -m builder.extract <brief files...> <tool_api.json> --out out/<slot> [--effort high] [--votes 3] [--facts out/<slot>.facts.json]
    python dev/eval_extract.py dev/gold/brief-a.spec.json out/<slot>.spec.json
    bash dev/run_extract_eval.sh        # A, A+B and the raw mock: extract, score, verify

In code (used by Track A's `build.py`):
`builder.extract.extract(brief_text, api_summary, trace, effort, votes=, verify_inputs_text=)` → `(facts, resolution, spec, issues)`.

## 4. Timing and quota (subscription backend, effort high)

Stage 1a 200-360 s (29-53k output tokens), stage 1b 150-200 s (21-28k), re-extract +150 s; a full extraction is 6-12 min
and reads ~180k cached input tokens per call. Seven extractions in 35 minutes exhausted the claude.ai session window
(reset at 11pm America/New_York). The final build (two briefs, 2-3 calls each) fits; run dev loops one brief at a time and
use `--facts` to resume. `ANTHROPIC_API_KEY` with `BUILDER_BACKEND=api` is the fallback.

## 5. Not closed

- **T3.5 acceptance** ("three runs on A give identical code-relevant fields") was not run live: a 3-vote build costs three
  full extractions and the quota was exhausted. Run-to-run variance exists (two A runs: 146 vs 131 facts, 98.3% vs 99.7%),
  so a `--votes 3` measurement is the next step, ideally on the API key.
- **Reproducibility for the organizers' rerun** (DEV_PLAN T10.1) depends on the point above.
- Left out per the cut list: LLM sentence coverage (T4.2b), the P2 mock briefs (b-d).
- For Track A: `builder/flowsim.py` carries brief/API literals flagged by `dev/audit_grep.py` (noted in memory.md §3d).

## 6. Coordination notes

File ownership between the tracks is in memory.md §3d. Track B wrote `builder/trace.py` and `builder/inputs.py`
(now Track A's and Track B's respectively). A parallel agent committed gold specs to the same paths minutes before
Track B's first commit; Track B's version superseded them with the same layout, and Track A's later schema
additions (`opening.first_sentence`, `debt_statement.intro_sentence`, `SpecialIntent.ask_once_text`) are covered by the gold and the eval.

---

# What is done: Track A (platform, generator, tests, CLI, evaluation)

Written 2026-10-11 05:45 UTC by the Track A agent. Branch `sercan-dev`, 52 commits. Everything below is committed.
Track A is the half of the builder that turns `spec.json` into the Freya phone agent, tests it, saves it, and runs the
development evaluation loop against the practice customers.

## 1. Results (final build, 06:30 UTC: brief-a v6 = agent 566c6109, brief-ab v8 = agent 6b530080)

| Run | Result | Where |
|---|---|---|
| Brief A, reps 3 (a customer counts only at 3/3) | **10/10** on the final build (v5 before the wording fix: 9/10, PUB-10 on the judge's literal "recorded" check) | `results/a-reps3-6.log`, `results/a-reps3-5.log` |
| Brief B, reps 3 | **3/3** on the final build (and on v7); v6: 2/3 once (PUB-12 scope miss, fixed as ISS-016) | `results/b-reps3-6.log`, `results/b-reps3-5.log` |
| Own cases for the six untested Brief A rules | **6/6** on the final build | `results/own-a-2.log` |
| Styles at reps 1 on the final build: pieces / in_words / asks_back | **10/10 / 10/10 / 10/10**; talkative 4-8/10, closed as a simulator artefact (the chatty customer's turn is cut mid-sentence whatever the agent does; ISS-010) | `results/a-*-3.log`, `results/mock-asks_back-2.log`, `results/mock-talkative-*.log` |
| Agent built from Track B's extracted Brief A spec (slot `ext-a`) | 8/10 before the last fixes (both misses since addressed) | `results/ext-a-1.log` |
| Full one-command build of Brief A from `briefs/brief-a.md` (slot `e2e-a`) | 419 s to a saved, smoke-tested, exported agent; extraction 100% exact vs gold; **9/10** at reps 1 (same PUB-10 judge miss) | `results/e2e-a-build.log`, `results/e2e-a-1.log` |
| Full one-command build of A+B from the brief files (slot `e2e-ab`) | 490 s; **B 3/3** at reps 1 | `results/e2e-ab-build.log`, `results/e2e-ab-1.log` |
| Sunday runbook dry run on the raw-material mock (5 files + its own tool API, slot `final-dry`) | 521 s, exit 0, smoke passed, every fixed line in the mock's words | `results/final-dry-build.log`, `submission/final-dry.trace.txt` |
| Reproducibility: two independent extractions of Brief A | 97.4% exact leaves identical; no number, date, enum or outcome differs | memory.md changelog 05:55 |
| Local suites (seconds) | static tests 649 (A) / 706 (A+B) passed; flows 10/10, 3/3, own 6/6; raw-mock specs pass with their own tool API | `builder/static_tests.py`, `dev/cases/flows_*.py` |

Baseline for comparison: the kit's base agent scored 0/10 on A (`dev/baselines.md`).

## 2. What was built

### Platform knowledge (Phase 1 spikes, memory.md §3c)
Nine spikes in one scripted chat session against practice sessions (`dev/spikes/`). Key facts: hooks run on engine-run
calls but not on a failed call; mapped lists arrive as None (post-hook JSON instead); flattened keys and counters are
named after the node; `{{x:json}}` sends strings (pre-hook coercion sends numbers); the close node's `on_enter` line comes
after the request starts (so a goodbye node precedes a silent close); extraction sees assistant turns, anchors relative
dates on the real clock, does not resolve `{{var}}`; chat/message never speaks the initial `on_enter` and suppresses
first-turn routing; a code write to an extraction-declared variable can be lost in the same turn; `time.sleep` works in
the sandbox; a simulation can stay "running" after its calls ended (watchdog `dev/unstick.py`).

### Generator (`builder/generate.py`, `builder/openapi_tools.py`, `builder/templates/snippets/*.py`)
- Code only, no model call at generate time. Byte-identical output for the same spec.
- Tools from the OpenAPI file (url, fields, enums, numeric coercion in pre-hooks, `maxRetries 0` on writes, post-hooks that
  write per-step status flags and a `what_to_do_next` line).
- 69-node graph: opening → opening router → identity question nodes (model tool with the field baked, post-hook status,
  decline/purpose/why/chatter routing) → account load → account facts (bands, deadlines, floors, speakable debt lines)
  → debt statement (fixed line) → negotiation router (the policy engine: amounts, dates, attempts, special intents,
  multi-product scope, deadline-adjusted dates) → fixed-line proposal node or model node for questions → read-back
  (fixed line, strict confirm) → guard → engine-run `create_promise` with one retry → recorded line → notes loop (B) →
  wrap-up (aggregation, close row) → goodbye (fixed line or model) → optional transfer → one close node per outcome
  row (literal body, no reason leaf where the table has none) → end_call.
- Every spoken amount and date is built in code from the `now` call variable: business days, holidays, nth business day,
  last business day of the week, this/next/week-after-next weekday, day-of-month resolution, callback window.
- Honesty: the agent says "recorded" only from a fixed line after `ok: true`; failures are retried once then stated.
- Robustness learned from the runs: cut-off customer turns get one clarification before counting as a non-answer;
  a named date or amount overrides "accepts the offer"; number fragments are not amounts; a question asked in the
  same breath as an answer is answered before the fixed line; a 3 s pause before replying (talkative customers were
  being cut off); turn caps on every conversation node that route to a close; the model never claims a failed check.
- Generic by construction: hidden-brief vocabulary comes from the spec and the tool API (identity fields, queues,
  outcomes, reasons, product labels, holidays, bands, attempts, sentences). The literal audit is clean.

### Local testing
- `builder/flowsim.py`: a local engine that walks the generated graph, execs the real code nodes and hooks against a
  fake bank (shape from the tool API), with scripted extraction values. `dev/cases/flows_a.py`, `flows_b.py`,
  `flows_own.py` replay the 13 practice customers and the 6 own cases in under a second.
- `builder/static_tests.py` (Phase 6): workflow lint (nulls, braces, targets, passthrough `always`, C11 on tool nodes,
  min_confidence, retries, reachability, placeholder data flow), and invariants derived from the spec on 17 `now` dates
  (deadlines, attempt-1 date, non-business days, after-deadline, exhausted attempts, guard, double write failure,
  callback window, identity failure, B aggregation).
- `dev/cases/own_a.json`: six own cases reusing practice customers with new scripts and brief-derived expectations.
- `dev/issues.json`: 13 issues with evidence (call ids), status and fix history.

### CLI, trace, smoke, export (Phase 7, `builder/build.py`, `builder/smoke.py`, `builder/freya_io.py`)
`python3 builder/build.py <brief files...> <tool_api.json> --slot NAME [--votes 3] [--skip-smoke] [--spec x.json]`
→ extract (Track B) → generate → static tests → dry run → save and publish (slot reused, state file absolute) →
two-turn chat smoke test → export `submission/<slot>.workflow.json` → `submission/<slot>.trace.txt` (start/end,
every model call, created objects, tests, secrets redacted). Exit code non-zero only if no agent was saved. README has
the run instructions.

### Evaluation tooling
`tools/run_cases.py` (kit) driven in background chains; `dev/spikes/chatdrive.py` walks a scripted conversation through
chat/message against a practice session and dumps events, variables and the ledger; `dev/unstick.py` watchdog.

## 3. Platform slots
`base` (kit agent), `spike`, `brief-a` (gold A), `brief-ab` (gold A+B), `mock` (latest build under test), `ext-a`
(Track B extracted spec), `e2e-a` (full one-command build). Slots are reused; never create new ones for reruns.

## 4. Not closed (see final.md)
- The Sunday runbook (final.md step 7) needs the user: hidden briefs in `final_inputs/`, two builds, commit, form.
- Judge dispute ISS-009 (the mandated "This call is recorded" opening trips a literal check) is accepted, not fixed.
- Platform filler "Bir saniye lütfen." on slow turns (ISS-003) cannot be controlled from the workflow.
