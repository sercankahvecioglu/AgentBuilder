# Baselines (T0.2)

| Agent | Slot | Brief | Reps | Result | Source |
|---|---|---|---|---|---|
| `examples/base-agent.json` | `base` (agent 08805a4b…) | A | 1 | **0 / 10** (478 s) | `results/log.jsonl`, `results/base-a.json`, 2026-10-10 18:18 |
| same | organisers' run | A+B | 1 | 2 / 13 | README v3 |
| `examples/agent_builder.py` | — | A | 1 | 10 / 10 (one run, not reproduced) | README v3 |

Failure modes of the base agent on A (from `results/base-a.json`): missing text-message sentence (01), no third-party handling (02), outcome guessed by the lifecycle LLM fill (03, 05, 08, 09, 10), dates not validated (04, 07), floor offer without "rest stays overdue" (06). Our builder must beat 0/10 at reps 1 and target 10/10 at reps 3.
