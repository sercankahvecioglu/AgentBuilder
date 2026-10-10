"""Gold facts for Brief A and A+B: one Fact per fact id used in the gold specs, with the brief's own text as quote.

Dev material. Used to test builder/verify.py (provenance, number re-parse, phrase check) against the gold spec and as
a reference shape for stage 1a output. Run from the repo root: python dev/gold/make_gold_facts.py
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())
from builder.resolve import resolve  # noqa: E402
from builder.schema import Extraction, Fact, dump_model  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

STAGE_BY_SECTION = {
    "1": "global", "2": "global", "3": "opening", "4": "third_party", "5": "identity", "6": "debt_statement",
    "7": "negotiation", "8": "negotiation", "9": "negotiation", "10": "confirmation", "11": "special", "12": "closing",
}
B_STAGE = {1: "debt_statement", 2: "debt_statement", 3: "negotiation", 4: "negotiation", 5: "negotiation", 6: "confirmation",
           7: "confirmation", 8: "closing", 9: "special", 10: "special", 11: "recording"}


def parse_brief_a(text: str) -> dict[str, tuple[str, str]]:
    """fact id -> (quote, stage)"""
    out: dict[str, tuple[str, str]] = {}
    section = "1"
    sec_text: dict[str, list[str]] = {}
    rule_re = re.compile(r"^(\d{1,2})\. (.*)")
    lines = text.splitlines()
    cur_rule = None
    for ln in lines:
        m = re.match(r"^## (\d+)\.", ln)
        if m:
            section = m.group(1)
            cur_rule = None
            continue
        m = rule_re.match(ln)
        if m:
            cur_rule = f"A-R{m.group(1)}"
            out[cur_rule] = (m.group(2).strip(), STAGE_BY_SECTION[section])
            continue
        if cur_rule and (ln.startswith("    ") or ln.startswith("|")):
            q, st = out[cur_rule]
            out[cur_rule] = (q + "\n" + ln.strip(), st)
            continue
        sec_text.setdefault(section, []).append(ln)
        if ln.startswith("|") or ln.startswith("Business days") or ln.startswith("If a transfer") or ln.startswith("Brief A never") or ln.startswith("Freya Bank calls"):
            cur_rule = None
    for sec in ("1", "2", "7", "12"):
        body = "\n".join(l for l in sec_text.get(sec, []) if l.strip() and not l.startswith("#"))
        out[f"A-S{sec}"] = (body, STAGE_BY_SECTION[sec])
    out["IMPL"] = ("(implied by the document as a whole)", "global")
    return out


def parse_brief_b(text: str) -> dict[str, tuple[str, str]]:
    out = {}
    closing = False
    for ln in text.splitlines():
        if ln.startswith("## Closing"):
            closing = True
            continue
        m = re.match(r"^(\d{1,2})\. (.*)", ln)
        if m and not closing:
            n = int(m.group(1))
            out[f"B-{n}"] = (m.group(2).strip(), B_STAGE[n])
        elif closing and ln.strip():
            out["B-CLOSE"] = (out.get("B-CLOSE", ("", "closing"))[0] + ln.strip() + " ", "closing")
    out["B-CLOSE"] = (out["B-CLOSE"][0].strip(), "closing")
    return out


def facts_from(parsed: dict[str, tuple[str, str]], doc_label: str) -> list[Fact]:
    facts = []
    for fid, (quote, stage) in parsed.items():
        facts.append(Fact(id=fid, text=quote.split("\n")[0][:200], agent_instruction="", source_quote=quote, doc_label=doc_label,
                          doc_date="", effective_from="", kind="definition" if fid in ("A-S1", "A-S2", "IMPL") else "decision",
                          stage=stage, topic=fid.lower().replace("-", "_"), scope="", conditions="", exceptions="", operator="", value=""))
    return facts


def main() -> None:
    a = parse_brief_a(open(os.path.join(ROOT, "briefs", "brief-a.md"), encoding="utf-8").read())
    b = parse_brief_b(open(os.path.join(ROOT, "briefs", "brief-b.md"), encoding="utf-8").read())
    for name, parsed_sets in (("brief-a", [(a, "brief-a.md")]), ("brief-ab", [(a, "brief-a.md"), (b, "brief-b.md")])):
        facts = []
        for parsed, label in parsed_sets:
            facts += facts_from(parsed, label)
        ex = Extraction(facts=facts, conflicts=[])
        res = resolve(ex)
        with open(os.path.join(HERE, f"{name}.facts.json"), "w", encoding="utf-8") as f:
            f.write(dump_model(ex) + "\n")
        with open(os.path.join(HERE, f"{name}.resolution.json"), "w", encoding="utf-8") as f:
            f.write(dump_model(res) + "\n")
        print(name, len(facts), "facts")
    # sanity: every fact id used by the gold specs exists
    for name in ("brief-a", "brief-ab"):
        spec = json.load(open(os.path.join(HERE, f"{name}.spec.json")))
        facts = {f["id"] for f in json.load(open(os.path.join(HERE, f"{name}.facts.json")))["facts"]}
        used = set(re.findall(r'"fact_ids": \[([^\]]*)\]', json.dumps(spec, indent=0)))
        ids = {x.strip().strip('"') for u in used for x in u.split(",") if x.strip()}
        print(name, "missing fact ids:", sorted(ids - facts))


if __name__ == "__main__":
    main()
