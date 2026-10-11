# final.md: the plan from now to submission

For the agent that runs overnight (and for the user on Sunday). Written 2026-10-11 05:50 UTC by the Track A agent.
Read first: `whatisdone.md` (what exists and the numbers), then `memory.md` §3b-§3d (corrections, platform facts, file
ownership), then this file. `DEV_PLAN.md` is the original plan; this file supersedes its schedule.

Times are UTC. **Freeze: Sunday 15:00. Hidden briefs: Sunday 17:00. Submission: Sunday 20:00.**

## 0. Hard rules (unchanged, do not bend)

- No brief value, name, sentence, date or outcome code in `builder/` (code, templates, prompts). Brief A/B values live only in `dev/`.
- The builder never reads `memory.md`, `DEV_PLAN.md`, `DEV_GUIDE.md`, `whatisdone.md`, `final.md` or `dev/`. Never create `CLAUDE.md` or `AGENTS.md`.
- Never hand-edit a workflow on the platform. Change templates or code, rebuild, re-save with the same slot.
- Reuse slots: `brief-a`, `brief-ab`, `mock`, `ext-a`, `e2e-a`, `spike`, `base`; for the dry run `final-dry`; for the hidden briefs `final-1`, `final-2`. Never create a slot per run.
- One simulation at a time. Low volume. No probing. Chat (`chat/message`) is cheap and queue-free; simulations are not.
- Never relax a failing test to match the agent. Log every failing case in `dev/issues.json` with evidence (call id).
- Secrets only from `.env`; never in files, traces or commits. Commit small increments on `sercan-dev` with clear messages; never commit `.env`, `out/`, `.freya-agents.json`, `.personas.json`, `results/`.
- Subscription backend: `BUILDER_BACKEND=agent` with `ANTHROPIC_API_KEY` unset. A full extraction costs 2-3 large calls and 6-12 min; about seven extractions exhaust the claude.ai session window (resets 03:00 UTC). Spend them only where this file says.
- After Sunday 17:00: no value, name or rule from a hidden brief enters code, prompts, templates, memory or issues. Crash fixes only, generic.

## 1. How to run things (copy-paste)

```bash
cd /Users/sercankahvecioglu/Desktop/build-the-builder
set -a && source .env && set +a && unset ANTHROPIC_API_KEY && export BUILDER_BACKEND=agent
P=/opt/anaconda3/envs/freyahackathon/bin/python

# build from the gold spec (no model calls), local suites
$P builder/build.py --spec dev/gold/brief-a.spec.json  tools/openapi.json --slot brief-a  --no-save --out out/gold --submission out/gold
$P builder/build.py --spec dev/gold/brief-ab.spec.json tools/openapi.json --slot brief-ab --no-save --out out/gold --submission out/gold
$P dev/cases/flows_a.py out/gold/brief-a.workflow.json; $P dev/cases/flows_b.py out/gold/brief-ab.workflow.json; $P dev/cases/flows_own.py out/gold/brief-a.workflow.json
$P -m builder.static_tests out/gold/brief-a.workflow.json dev/gold/brief-a.spec.json
$P dev/audit_grep.py

# save a built workflow to a slot (publishes; version increases)
$P -c "import json,sys; sys.path.insert(0,'.'); from builder import freya_io; print(freya_io.save('brief-a', json.load(open('out/gold/brief-a.workflow.json'))))"

# agent ids
$P -c "import json; print(json.load(open('.freya-agents.json')))"

# practice runs (append 'exit $?' so a watcher can detect the end; -u so the log fills while running)
$P -u tools/run_cases.py <agent_id> --brief A --reps 3 --out results/<name>.json > results/<name>.log 2>&1; echo "exit $?" >> results/<name>.log
$P -u tools/run_cases.py <agent_id> --brief A --style talkative --out results/<name>.json > results/<name>.log 2>&1
$P -u tools/run_cases.py <agent_id> --cases dev/cases/own_a.json --out results/<name>.json > results/<name>.log 2>&1

# inspect a failed call: transcript + extraction values + router lines (adapt the ids)
#   see dev/spikes/chatdrive.py for the event-dump code; freya.get_call(call_id)["messages"]; route_evaluated carries variable_table

# watchdog for a simulation stuck at "running" after its calls ended (ISS-005); keep it running during evaluation
nohup $P dev/unstick.py >> results/unstick.log 2>&1 &

# full one-command build from brief files (extraction via the subscription backend; 6-12 min)
$P builder/build.py briefs/brief-a.md tools/openapi.json --slot e2e-a
$P builder/build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json --slot e2e-ab
```

Always run from the repo root. Run `git status` before committing and never add `.env`.

## 2. Step-by-step plan

Work the steps in order. Each has a done-check. Record numbers in `memory.md` changelog and fixes in `dev/issues.json`.

### Step 1: close the measurement that is in flight
DONE 06:13 UTC: brief-a v5 A 9/10 at reps 3 (only the 'recorded' judge trap); brief-ab v7 **B 3/3 at reps 3**; mock asks_back 10/10; talkative closed as a simulator artefact (ISS-010). The final build (brief-a v6, brief-ab v8) is on the real slots; its confirmation chain is running (results/a-reps3-6.log, a-asks_back-6, a-pieces-6, a-in_words-6, b-reps3-6). Original text of the step follows for reference.
1. Read `results/a-reps3-5.log` (brief-a v5, A at reps 3), `results/b-reps3-3.log` (brief-ab v6, B at reps 3),
   `results/mock-talkative-1.log` and `results/mock-asks_back-1.log` (the "paused" build on slot `mock`).
2. If a log never gets its `exit` line and the simulation shows `running` with all calls ended for over 20 min, the watchdog releases it; if the watchdog is not running, start it.
3. Done-check: every log has a final line. Write the four numbers into `memory.md` changelog.

### Step 2: decide whether the latest build goes to the real slots
State at 05:55: brief-a v5 scored A 9/10 at reps 3 (only PUB-10, the judge's "recorded" trap, failed and only in 2 of 3 reps); the extracted-spec agent `e2e-a` scored 9/10 with the same single miss. The 3 s reply pause did NOT stop the talkative cut-offs (turns were still cut 5 s before the agent spoke) and was removed. The build now on slot `mock` (commit "[xtrack] 1b guidance: recording disclosure...") has instead: inactivity monitor off on every conversation node, the opening sentence phrased "We are recording this call" (generic 1b rule: active voice for the recording disclosure, "recorded" reserved for the promise), and a router fix (an acceptance after two non-answers no longer lands in the model node with an empty instruction). A talkative run on `mock` is queued as `results/mock-talkative-2.log`.
- If `mock` talkative-2 ≥ 8/10 with no transcript cut mid-sentence after the agent's turn, and asks_back ≥ 9/10: save `out/gold/brief-a.workflow.json` to `brief-a` and `out/gold/brief-ab.workflow.json` to `brief-ab`, then run A reps 3 and B reps 3 on them (step 3).
- DONE 06:12 UTC: customer turns are still cut whatever the agent does (tts, streamed lines, pause, monitor off): platform or persona artefact (ISS-010, status accepted-platform). Do not spend more runs on talkative. The latest build (all fixes, fixed tts lines) is saved as brief-a v6 and brief-ab v8; the confirmation chain (A reps 3, asks_back, pieces, in_words, B reps 3) is queued as results/*-6.log and results/b-reps3-6.log.
- Done-check: `.freya-agents.json` shows a new version for both slots and `git log` has the commit that produced it.

### Step 3: fix loop until the targets hold on the real slots
State 06:15: read the *-6 logs first. Expected: A 9-10/10 (PUB-10 may still trip the judge's literal 'recorded' check even with the new wording; if it does, accept it as ISS-009), asks_back/pieces/in_words ≥ 9/10, B 3/3. Only a real regression (a case that passed at reps 3 before and now fails on a code path) justifies another round.
Targets: A 10/10 at reps 3, B 3/3 at reps 3, own cases 6/6, pieces/in_words ≥ 9/10, asks_back ≥ 9/10, talkative ≥ 8/10.
Loop (at most three rounds, stop at 11:00 UTC whatever the state):
1. Run in one background chain: A reps 3, B reps 3, own cases, then the four styles at reps 1.
2. For every FAIL: fetch the call (transcript, extraction values with confidence, router `nego_say`/hints, ledger). Decide:
   extraction miss (fix the enum description in `generate.py`), router logic (fix the snippet in `builder/templates/snippets/`),
   prompt (fix the task text in `generate.py`), platform or persona artefact or judge dispute (log it, do not fix).
   Known non-fixes: ISS-009 (judge faults the mandated "This call is recorded" sentence), ISS-013 (persona leaked its reasoning), ISS-003 (platform filler).
3. After a fix: regenerate both gold builds, run the three local flow suites and both static test runs (must stay 100%), `dev/audit_grep.py` must stay clean, commit, save to the slots, rerun only the affected runs plus one A reps 3 at the end of the round.
4. Done-check: a reps-3 run of A and of B on the final build with the targets met, or 11:00 UTC reached. Record the final numbers and the agent versions in `memory.md`.

### Step 4: validate the real pipeline output (not the gold spec)
1. Run the practice customers on the `e2e-a` agent (slot `e2e-a`, workflow `988d11cc…`, built from `briefs/brief-a.md` by extraction at 05:36-05:43): `--brief A` at reps 1, then reps 3 if 10/10.
   If the current real slots carry a newer generator than e2e-a, rebuild e2e-a from its saved spec without a new extraction:
   `$P builder/build.py --spec out/e2e-a.spec.json tools/openapi.json --slot e2e-a` (no model calls).
2. Compare the two independent extractions of Brief A: `$P dev/eval_extract.py out/brief-a2.spec.json out/e2e-a.spec.json` and
   `$P dev/eval_extract.py dev/gold/brief-a.spec.json out/e2e-a.spec.json`. Record both scores. Any code-relevant leaf (numbers, dates, enums, outcomes) that differs between the two runs goes into `memory.md` as a reproducibility risk with the field path.
3. DONE 05:54 UTC (`e2e-ab`: 490 s, 708 static checks, smoke passed, B 3/3 at reps 1). Build A+B once from the brief files: `$P builder/build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json --slot e2e-ab` (one extraction, 2-3 calls). Run `--brief B` reps 1 on it. Done-check: the trace is complete (start, model calls, created, tests, end), build time under 15 min, B ≥ 2/3.
4. Only if quota allows (count the model calls in today's traces; stay under about 12 large calls before 15:00): one `--votes 3` build of Brief A into slot `e2e-a` to see whether the three code-relevant field sets agree (DEV_PLAN T3.5). If they do not, note the disputed fields; do not change the default to votes 3.

### Step 5: Sunday runbook dry run on the raw-material mock
DONE 06:03 UTC: exit 0, 521 s, 2 model calls, verify 0 errors / 4 warnings, 651 static checks, smoke passed, export written, every fixed line in the mock's words (Nordlys Bank, postcode question, SMS sentence, mock outcome rows). Repeat only if the generator changes substantially.
1. `$P builder/build.py dev/mock_briefs/raw1/01_request_mail.eml dev/mock_briefs/raw1/02_policy_extract.md dev/mock_briefs/raw1/03_memo_q4.md dev/mock_briefs/raw1/04_code_list.csv dev/mock_briefs/raw1/05_thread.eml dev/mock_briefs/raw1/tools.json --slot final-dry`
   (this is the exact shape of the hidden raw brief: several files, own tool API, other identity fields and queues).
2. Done-check: exit code 0, `submission/final-dry.trace.txt` complete, static tests passed, smoke test passed, export written, the spoken lines in `out/final-dry.workflow.json` use the mock's words (open the `opening`, `state_debt`, `say_recorded` nodes and read them; nothing from Brief A may appear).
3. If it crashes: fix generically (a parser or schema edge case), commit, rerun. Do not add mock values anywhere in `builder/`.

### Step 6: freeze preparation (by 14:30)
1. `git status` clean except `out/`, `results/`, state files. `git log --all -- .env` empty. `grep -rn "fak_\|sk-ant-" submission/ builder/ dev/` empty.
2. Isolation check: `grep -rn 'memory\.md\|DEV_PLAN\|DEV_GUIDE\|"dev/\|public-test-set\|briefs/' builder/*.py builder/templates/snippets/*.py` shows docstrings only, no file reads.
3. `dev/audit_grep.py` clean. Local suites green. `python -m pytest dev/tests -q` green (Track B's tests).
4. Confirm `requirements.txt` installs into a fresh venv and `python3 builder/build.py --spec dev/gold/brief-a.spec.json tools/openapi.json --slot brief-a --no-save` works from that venv (README section "Our builder").
5. Update `memory.md`: final numbers, agent versions per slot, open issues, the decisions D1-D23 that changed (D7: fixed spoken lines; D9: G2 confirmed; C7: goodbye node). Update `whatisdone.md` §1 numbers.
6. `git tag pre-final && git push AgentBuilder sercan-dev --tags` (ask the user before pushing if pushing was not already approved today; the tag itself is harmless).
7. Stop all background runners and the watchdog. Nothing may be running on the workspace at 15:00.

### Step 7: Sunday 17:00-20:00 (the user must be present)
1. Put each hidden brief's files and its tool API in `final_inputs/<brief-1>/` and `final_inputs/<brief-2>/` (any text files; the API file last on the command line). Do not paste their content anywhere else.
2. Check the subscription window is fresh (two builds need 4-6 large calls). Fallback: `ANTHROPIC_API_KEY` in `.env` with `BUILDER_BACKEND=api`.
3. Build, one brief at a time, in the background with a log, and watch the trace:
   `$P builder/build.py final_inputs/<brief-1>/* --slot final-1` (list the text files explicitly, the `.json`/`.yaml` tool file last) and the same for `final-2`.
   Expected: 7-13 min each, exit 0, `submission/final-1.workflow.json`, `submission/final-1.trace.txt`.
4. Read the trace: static test failures and smoke warnings are allowed but read them; if the static tests report a crash or the smoke reply lacks the opening elements, open `out/final-1.workflow.json`, find the cause, fix generically in `builder/`, commit, rebuild from scratch (new extraction) or with `--spec out/final-1.spec.json` if the spec was fine.
5. No hand edits on the platform. No practice simulations on the hidden agents (there are no practice customers for them); the chat smoke test inside the build is the only live check.
6. Commit: code, `submission/final-1.*`, `submission/final-2.*`, `requirements.txt`. No `.env`, no `final_inputs/` needed. Record the commit hash.
7. Send the form before 20:00: team, repo URL, commit hash, run command (`python3 builder/build.py <brief files> <tool_api.json> --slot final-N`), workflow paths, trace paths; mention that the builder runs on a Claude login (subscription) or an API key.

## 3. What to do when something goes wrong

- A simulation stays "running" for 20+ min after its calls ended: `PUT /api/v2/simulations/{id}` with `{"status": "completed"}` (the watchdog does it), then rerun what was queued. Never force it earlier: the judge verdicts come late and forcing gives "inconclusive".
- run_cases prints nothing for a long time: it is polling; check `results/<name>.log` (with `-u`) and the simulation status via the API before killing anything.
- A build crashes in extraction: `builder/extract.py` has `--facts out/<slot>.facts.json` to resume stage 1b from saved facts (saves one large call).
- Subscription "session limit": wait for the reset or set `ANTHROPIC_API_KEY` and `BUILDER_BACKEND=api`.
- A generated line reads like an instruction ("Say that you are..."): the spec field came back as an instruction; the generator falls back to a model-written line, but check Track B's 1b prompt wording for `first_sentence`, `intro_sentence`, `success_sentence`, `confirm_question`, `first_question`.
- Static test failure on a hidden brief: read the message; a failing invariant means the spec has an unexpected value (for example a band gap) or the generator met a shape it has not seen. Fix generically; the build still saves an agent and exits 0.

## 4. Definition of done (DEV_PLAN §6, updated)
- [ ] A 10/10 and B 3/3 at reps 3 on the final build; own cases 6/6; styles at the targets above
- [ ] e2e-a (real extraction) ≥ 9/10 at reps 1; A+B from brief files builds in < 15 min with a complete trace
- [ ] raw-mock runbook dry run exits 0 with a complete trace and mock-only wording
- [ ] audit clean; isolation clean; no secrets; tag `pre-final`
- [ ] memory.md and whatisdone.md updated with the final numbers
