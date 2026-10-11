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
