# Final-case handoff (Team SK) — state at 18:10 UTC, 11 Oct 2026

Deadline: 20:00 UTC (23:00 Istanbul). Send by e-mail (reply to "the final case is open", yavuz@freyavoice.ai) three files:
`submission/submission.json`, `submission/final.workflow.json`, `submission/final.trace.txt` (optionally `submission/final.agent.jsonl`, the Claude session log).

## What exists
- Mock (deployed, keep it up): https://freya-final-mock.sarperkahvecioglu1.workers.dev  (`mock/`, Cloudflare account of sarperkahvecioglu1; `wrangler deploy` from `mock/` redeploys).
  Serves the 7 contract services under `/voice/v1/`, exact answers of test-customers.json, `GET /openapi.json`.
- Builder: `python3 builder/build.py final_inputs/final-case https://freya-final-mock.sarperkahvecioglu1.workers.dev --mode agent --slot final`
  (agent mode: Claude writes the workflow from the documents, `builder/validate.py` + dry run check it; needs a Claude login or ANTHROPIC_API_KEY, FREYA_API_KEY in .env).
- Case folder: `final_inputs/final-case/` (git-ignored; zip from the Drive folder in the mail).
- Dev tools: `dev/sim_drive.py <agent_id> '<vars json>' "<persona prompt>"` runs one simulated customer against an agent and prints the transcript; `dev/chat_drive.py` for chat turns.

## Builds
| run | commit of the code | slot / agent | result |
|---|---|---|---|
| 1 | 767daf3 (files committed there) | final v1, agent 9a8ecca7… | examples 1,2+5,3,4 all judged pass; only gap: example 4 lacks the "only the latest statement can be sent" sentence |
| 2 | (skill with borderline wording) | final v2 | fixed the sentence but FAILED example 1 (cut-off "Teşekkürler, başka bir…" → card selection) — do not submit |
| 3 | 267f851 (clean skill) | final-b v1, agent 223af102… | built 18:07; sims 1 and 4 running (results/run3-sim-*.log) |

Decision rule: submit run 3 if sims 1 and 4 both pass cleanly; otherwise run 1.

## How to submit run 1 (fallback)
```
git checkout 767daf3 -- submission/final.workflow.json submission/final.trace.txt submission/final.agent.jsonl traces/final.agent.jsonl
```
then set `"commit": "767daf3"` in submission/submission.json, commit, push, e-mail the three files.

## How to submit run 3
Copy `submission/final-b.workflow.json` → `submission/final.workflow.json`, `submission/final-b.trace.txt` → `submission/final.trace.txt`,
`traces/final-b.agent.jsonl` → `submission/final.agent.jsonl` (renames only, no edits), commit + push, put that commit's hash in submission.json
(run_command as above but `--slot final-b`), e-mail.

## Rules to keep
No hand edits to any workflow; nothing from the case into `builder/`; mock must stay deployed until results are out.
