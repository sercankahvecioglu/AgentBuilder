# Mock raw-material brief `raw1` (DEV_PLAN T2.4a)

A rewrite of Brief A as bank material with other values: Nordlys Bank, other call variables (`given_name`,
`family_name`, `salutation`, `call_time`), other identity questions (`postcode`, `birth_year`), other queues
(`payment_plans`, `agents`, `care`), other reasons (`disputed`, `plan`, `agent`, `care`), other phrases, holidays, bands and windows.

| File | Date | Role |
|---|---|---|
| `01_request_mail.eml` | 2026-09-02 | call variables, opening, identity questions, goodbye rule |
| `02_policy_extract.md` | 2026-06-15 | the rules (A.1 ... I.1), holidays, bands |
| `03_memo_q4.md` | 2026-09-20 | changes three values **without saying "supersedes"** and adds a holiday |
| `04_code_list.csv` | - | outcomes, reasons, queues |
| `05_thread.eml` | 2026-09-10/11 | discussion that decides nothing (Saturday callbacks, half-minimum floor) |
| `tools.json` | - | mock tool API (same 7 tools; `verify_identity.field` and `transfer_to_agent.queue` enums changed, no `hint`) |
| `gold.spec.json` | - | expected spec (`make_gold.py`) |

Expected resolution (checked by `eval_extract` against `gold.spec.json`):
- memo 2 vs policy D.1: overdue band 11-60 → **11-75** (later `doc_date` wins)
- memo 3 vs policy D.1: fresh deadline 10th → **8th** business day (later `doc_date` wins)
- memo 1 vs policy A.2: callback closes 18:00 → 17:00 **from 2026-10-01**: `to_time` stays `18:00`, `date_conditional` carries `17:00` from `2026-10-01`
- memo 4: holiday `2026-11-02` added (no conflict, union)
- memo 5: no change (restates E.3)
- thread: `discussion`, never applied (no Saturday window, no half floor)

Run (from the repo root):

    python -m builder.extract dev/mock_briefs/raw1/01_request_mail.eml dev/mock_briefs/raw1/02_policy_extract.md dev/mock_briefs/raw1/03_memo_q4.md dev/mock_briefs/raw1/04_code_list.csv dev/mock_briefs/raw1/05_thread.eml dev/mock_briefs/raw1/tools.json --out out/raw1
    python dev/eval_extract.py dev/mock_briefs/raw1/gold.spec.json out/raw1.spec.json

Target (T3.4): exact ≥ 90%.
