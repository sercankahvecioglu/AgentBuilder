"""Print the rule → spec-field coverage table for dev/gold/README.md (run from the repo root)."""
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def paths(o, prefix, acc):
    if isinstance(o, dict):
        if "fact_ids" in o:
            for fid in o["fact_ids"]:
                acc[fid].append(prefix)
        for k, v in o.items():
            if k != "fact_ids":
                paths(v, f"{prefix}.{k}" if prefix else k, acc)
    elif isinstance(o, list):
        for n, v in enumerate(o):
            key = v.get("key") or v.get("label") or v.get("api_field") or v.get("product_type") or v.get("name") if isinstance(v, dict) else None
            if isinstance(v, dict) and "outcome" in v and "when" in v:
                key = f"{v['outcome']}/{v['reason'] or '-'}"
            if isinstance(v, dict) and "n" in v:
                key = f"n{v['n']}"
            paths(v, f"{prefix}[{key if key else n}]", acc)
    return acc


def table(path, ids):
    acc = paths(json.load(open(path)), "", defaultdict(list))
    rows = ["| Rule | Spec fields (dotted paths; `behaviour_rules[...]` = prompt instruction) |", "|---|---|"]
    for fid in ids:
        ps = acc.get(fid, [])
        short = [p for p in ps if not p.startswith("behaviour_rules")]
        nbr = sum(1 for p in ps if p.startswith("behaviour_rules"))
        cell = ", ".join(f"`{p}`" for p in short) + (f" + {nbr} behaviour rule(s)" if nbr else "")
        rows.append(f"| {fid} | {cell or '**MISSING**'} |")
    return "\n".join(rows)


if __name__ == "__main__":
    a_ids = ["A-S1", "A-S2", "A-S7", "A-S12"] + [f"A-R{n}" for n in range(1, 48)]
    b_ids = [f"B-{n}" for n in range(1, 12)] + ["B-CLOSE"]
    print("### Brief A → `brief-a.spec.json`\n")
    print(table(os.path.join(HERE, "brief-a.spec.json"), a_ids))
    print("\n### Brief B → `brief-ab.spec.json` (B items only; A rules map as above)\n")
    print(table(os.path.join(HERE, "brief-ab.spec.json"), b_ids))
