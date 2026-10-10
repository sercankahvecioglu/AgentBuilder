#!/usr/bin/env bash
# Track B eval loop: extract A, A+B and the raw mock, then score each against its gold and run verify.
# Needs ANTHROPIC_API_KEY (or a Claude login) in the environment. Run from the repo root:
#   source .env; bash dev/run_extract_eval.sh [effort]
set -uo pipefail
PY=${PY:-/opt/anaconda3/envs/freyahackathon/bin/python}
EFFORT=${1:-high}
mkdir -p out
run() {  # name, gold, extra verify inputs..., -- inputs...
  local name=$1 gold=$2; shift 2
  echo "=== $name"
  $PY -m builder.extract "$@" --out "out/$name" --effort "$EFFORT" 2>/dev/null || { echo "extract $name FAILED (see out/$name.trace.txt)"; return; }
  $PY dev/eval_extract.py "$gold" "out/$name.spec.json" --json "out/$name.eval.json" | head -40
  api=${@: -1}
  texts=("${@:1:$#-1}")
  $PY -m builder.verify "out/$name.spec.json" "out/$name.facts.json" "out/$name.resolution.json" "$api" "${texts[@]}" | tail -15
}
run brief-a  dev/gold/brief-a.spec.json  briefs/brief-a.md tools/openapi.json
run brief-ab dev/gold/brief-ab.spec.json briefs/brief-a.md briefs/brief-b.md tools/openapi.json
R=dev/mock_briefs/raw1
run raw1 $R/gold.spec.json $R/01_request_mail.eml $R/02_policy_extract.md $R/03_memo_q4.md $R/04_code_list.csv $R/05_thread.eml $R/tools.json
