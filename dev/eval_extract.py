"""Compare an extracted spec with a gold spec, leaf by leaf (DEV_PLAN T2.3).

    python dev/eval_extract.py dev/gold/brief-a.spec.json out/brief-a.spec.json [--json misses.json] [-v]

Scoring classes (every gold leaf falls in exactly one):
  exact  closed values: bools, ints, enums, dates, times, codes, outcome/reason, lists of codes.
         Normalized exact match (lists: every gold item has a fuzzy-equal candidate item).
  text   free-text instructions (ask_text, trigger_description, say_text, ...): token overlap.
  soft   behaviour_rules: each gold rule must have a candidate rule in the same stage with token overlap.
fact_ids are never compared. `multi_product.*` other than `enabled` is skipped when gold `enabled` is false.
The headline number is `exact`; the T3.4 target (>= 95%) applies to it. gold vs gold gives 100% in every class.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict

TEXT_FIELDS = {
    "when", "trigger_description", "meaning", "ask_text", "agent_instruction", "intro_instruction",
    "say_text", "instruction", "explain_once_text", "fail_message", "failure_say",
    "change_after_record_text", "robot_question_reply", "agent_self_description", "note",
    "default_applied", "template", "first_sentence", "ask_once_text",
}
# list-of-object alignment keys by path (regex on the dotted path without indices)
LIST_KEYS = {
    r"^call_variables$": lambda o: norm(o.get("name")),
    r"^identity\.questions$": lambda o: norm(o.get("api_field")),
    r"^bands$": lambda o: str(o.get("days_late_min")),
    r"^debt_statement\.product_labels$": lambda o: norm(o.get("product_type")),
    r"^amounts\.floor_field_by_type$": lambda o: norm(o.get("product_type")),
    r"^negotiation\.attempts$": lambda o: str(o.get("n")),
    r"^closing\.outcome_table$": lambda o: f"{norm(o.get('outcome'))}/{norm(o.get('reason'))}",
    r"^closing\.aggregation\.all_noted_as$": lambda o: norm(o.get("reason")),
    r"^required_phrases$": lambda o: norm_phrase(o.get("text")),
    r"^special_intents$": lambda o: intent_key(o),
    r"^unresolved$": lambda o: norm(o.get("topic")),
    r"^date_conditional$": lambda o: f"{norm(o.get('field_path'))}@{norm(o.get('effective_from'))}",
}
INTENT_SYNONYMS = {
    "paid": "already_paid", "already_paid_claim": "already_paid", "claims_paid": "already_paid",
    "human": "wants_human", "human_request": "wants_human", "request_human": "wants_human", "asks_for_human": "wants_human",
    "plan": "wants_plan", "payment_plan": "wants_plan", "restructuring": "wants_plan", "new_payment_plan": "wants_plan",
    "scam": "scam_question", "is_this_a_scam": "scam_question",
    "robot": "robot_question", "ai_question": "robot_question", "robot_or_ai": "robot_question", "are_you_a_robot": "robot_question",
    "does_not_want_to_talk": "not_talk", "not_want_to_talk": "not_talk", "refuses_to_talk": "not_talk", "no_talk": "not_talk",
    "unknown": "unknown_question", "cannot_answer": "unknown_question", "unanswerable_question": "unknown_question",
    "question_cannot_answer": "unknown_question",
    "debt_not_mine": "dispute", "disputes": "dispute", "not_mine": "dispute",
    "illness_death_job_loss": "hardship",
}


def norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip().lower()
    s = re.sub(r"\{\{\s*(\w+)\s*\}\}|\{\s*(\w+)\s*\}|\[\s*(\w+)\s*\]|<\s*(\w+)\s*>", lambda m: "{" + next(g for g in m.groups() if g) + "}", s)
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" .;:,'\"")
    s = re.sub(r"^(\d{1,2}):(\d{2}):00$", r"\1:\2", s)  # 10:00:00 -> 10:00
    s = re.sub(r"^(\d):(\d{2})$", r"0\1:\2", s)  # 9:00 -> 09:00
    return LANG.get(s, s)


LANG = {"en": "english", "en-gb": "english", "en-us": "english", "de": "german", "fr": "french", "es": "spanish", "nl": "dutch",
        "it": "italian", "pt": "portuguese", "sv": "swedish", "no": "norwegian", "da": "danish", "fi": "finnish", "pl": "polish"}


def norm_phrase(v) -> str:
    s = norm(v)
    return re.sub(r"[^a-z0-9{} ]", "", s)


def tokens(v) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", norm(v)) if t not in STOP}


STOP = set("the a an and or of to in on for with that this is are be it its as at by from if they them their you your not do does".split())


def intent_key(o) -> str:
    k = norm(o.get("key")).replace(" ", "_").replace("-", "_")
    return INTENT_SYNONYMS.get(k, k)


def intent_signature(o) -> str:
    return "|".join(norm(o.get(f)) for f in ("action_kind", "action_queue", "close_outcome", "close_reason", "declined_close_reason"))


def fuzzy_eq(a: str, b: str) -> bool:
    """Normalized equality, or containment, or high token overlap (for list items and enum-like strings)."""
    a, b = norm(a), norm(b)
    if a == b:
        return True
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.6


def text_eq(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    if a == b:
        return True
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta:
        return False
    return len(ta & tb) / len(ta) >= 0.4  # recall of gold tokens


def list_key(path: str):
    bare = re.sub(r"\[[^\]]*\]", "", path)
    for pat, fn in LIST_KEYS.items():
        if re.search(pat, bare):
            return fn
    return None


class Eval:
    def __init__(self, gold: dict, cand: dict, verbose: bool = False):
        self.gold, self.cand, self.verbose = gold, cand, verbose
        self.rows: list[dict] = []  # {path, cls, ok, gold, got}
        self.extras: list[str] = []
        self.multi_enabled = bool(gold.get("multi_product", {}).get("enabled", {}).get("value", False))

    # ---- walking --------------------------------------------------------
    def run(self):
        self.walk(self.gold, self.cand, "")
        self.precedence_order()
        return self

    def precedence_order(self):
        """Precedence is ordinal: every gold pair 'a before b' (strictly lower number) must hold in the candidate."""
        g = {intent_key(o): o.get("precedence", 0) for o in self.gold.get("special_intents", []) if isinstance(o, dict)}
        c = {intent_key(o): o.get("precedence", 0) for o in (self.cand.get("special_intents") or []) if isinstance(o, dict)}
        bad = []
        for a, pa in g.items():
            for b_, pb in g.items():
                if pa < pb and a in c and b_ in c and not (c[a] < c[b_]):
                    bad.append(f"{a}<{b_}")
        self.add("special_intents.precedence_order", "exact", not bad, "gold order", bad or "same order")

    def add(self, path, cls, ok, g, c):
        self.rows.append({"path": path, "class": cls, "ok": bool(ok), "gold": g, "got": c})

    def skip(self, path) -> bool:
        if path.startswith("multi_product.") and not self.multi_enabled and path != "multi_product.enabled":
            return True
        return False

    def walk(self, g, c, path):
        if path == "behaviour_rules":
            return self.behaviour_rules(g, c)
        if self.skip(path):
            return
        if isinstance(g, dict):
            if "fact_ids" in g and set(g) <= {"value", "fact_ids"}:
                field = path.rsplit(".", 1)[-1]
                return self.leaf(path, g["value"], (c or {}).get("value") if isinstance(c, dict) else None, field)
            if "fact_ids" in g and set(g) <= {"values", "fact_ids"}:
                return self.leaf(path, g["values"], (c or {}).get("values") if isinstance(c, dict) else None, "values")
            for k, v in g.items():
                if k == "fact_ids":
                    continue
                sub = f"{path}.{k}" if path else k
                cv = c.get(k) if isinstance(c, dict) else None
                if isinstance(v, (dict, list)):
                    self.walk(v, cv, sub)
                else:
                    self.leaf(sub, v, cv, k)
            return
        if isinstance(g, list):
            keyfn = list_key(path)
            if keyfn is None:
                return self.leaf(path, g, c, path.rsplit(".", 1)[-1])
            cl = c if isinstance(c, list) else []
            cmap = {}
            for o in cl:
                if isinstance(o, dict):
                    cmap.setdefault(keyfn(o), o)
            if path == "special_intents":
                sig = {intent_signature(o): o for o in cl if isinstance(o, dict)}
            for o in g:
                k = keyfn(o)
                match = cmap.get(k)
                if match is None and path == "special_intents":
                    match = sig.get(intent_signature(o))
                if match is None and path == "required_phrases":
                    match = next((x for x in cl if isinstance(x, dict) and fuzzy_eq(norm_phrase(x.get("text")), k)), None)
                if match is None:
                    self.add(f"{path}[{k}]", "exact", False, "(present)", "(missing item)")
                    # count the item's leaves as misses too, so a missing row weighs its size
                    self.walk(o, {}, f"{path}[{k}]")
                else:
                    self.walk(o, match, f"{path}[{k}]")
            gkeys = {keyfn(o) for o in g}
            for o in cl:
                if isinstance(o, dict) and keyfn(o) not in gkeys:
                    self.extras.append(f"{path}[{keyfn(o)}]")
            return
        self.leaf(path, g, c, path.rsplit(".", 1)[-1])

    def leaf(self, path, g, c, field):
        if self.skip(path):
            return
        if path.startswith("special_intents") and field == "key":
            return self.add(path, "exact", intent_key({"key": g}) == intent_key({"key": c}), g, c)
        if path.startswith("special_intents") and field == "precedence":
            return  # ordinal: scored once for the whole list in precedence_order()
        if field in TEXT_FIELDS and isinstance(g, str):
            if g == "":
                ok = norm(c) == ""
            else:
                ok = text_eq(g, c or "")
            return self.add(path, "text", ok, g, c)
        if isinstance(g, list):
            cl = c if isinstance(c, list) else []
            if not g:
                ok = not cl
            else:
                ok = all(any(fuzzy_eq(str(x), str(y)) for y in cl) for x in g)
            return self.add(path, "exact", ok, g, c)
        if isinstance(g, bool):
            return self.add(path, "exact", isinstance(c, bool) and c == g or norm(c) == norm(g), g, c)
        if isinstance(g, int):
            try:
                ok = int(c) == g
            except (TypeError, ValueError):
                ok = False
            return self.add(path, "exact", ok, g, c)
        gs, cs = norm(g), norm(c)
        if gs == "":
            ok = cs == ""
        elif re.fullmatch(r"[a-z0-9_]+", gs):  # enum-like token: candidate must contain it
            ok = gs == cs or re.search(rf"(^|[^a-z0-9_]){re.escape(gs)}([^a-z0-9_]|$)", cs) is not None
        else:
            ok = fuzzy_eq(gs, cs)
        self.add(path, "exact", ok, g, c)

    def behaviour_rules(self, g, c):
        cl = [r for r in (c or []) if isinstance(r, dict)]
        for r in g:
            same_stage = [x for x in cl if norm(x.get("stage")) == norm(r.get("stage"))]
            pool = same_stage or cl
            best = max((overlap(r["agent_instruction"], x.get("agent_instruction", "")) for x in pool), default=0.0)
            self.add(f"behaviour_rules[{','.join(r.get('fact_ids', []))}]", "soft", best >= 0.35, r["agent_instruction"], f"best overlap {best:.2f}")

    # ---- reporting ------------------------------------------------------
    def summary(self) -> dict:
        out = {}
        for cls in ("exact", "text", "soft"):
            rows = [r for r in self.rows if r["class"] == cls]
            ok = sum(r["ok"] for r in rows)
            out[cls] = {"ok": ok, "total": len(rows), "pct": (100.0 * ok / len(rows)) if rows else 100.0}
        rows = self.rows
        out["all"] = {"ok": sum(r["ok"] for r in rows), "total": len(rows), "pct": 100.0 * sum(r["ok"] for r in rows) / len(rows) if rows else 100.0}
        return out

    def by_section(self) -> dict:
        sec = defaultdict(lambda: [0, 0])
        for r in self.rows:
            if r["class"] == "soft":
                continue
            s = r["path"].split(".")[0].split("[")[0]
            sec[s][1] += 1
            sec[s][0] += r["ok"]
        return dict(sec)

    def misses(self) -> list[dict]:
        return [r for r in self.rows if not r["ok"]]

    def report(self) -> str:
        lines = []
        summ = self.summary()
        lines.append(f"exact {summ['exact']['ok']}/{summ['exact']['total']} = {summ['exact']['pct']:.1f}%   "
                     f"text {summ['text']['ok']}/{summ['text']['total']} = {summ['text']['pct']:.1f}%   "
                     f"soft(behaviour_rules) {summ['soft']['ok']}/{summ['soft']['total']} = {summ['soft']['pct']:.1f}%   "
                     f"all {summ['all']['pct']:.1f}%")
        lines.append("")
        lines.append(f"{'section':<20}{'ok/total':>10}")
        for s, (ok, tot) in sorted(self.by_section().items()):
            flag = "" if ok == tot else "  <--"
            lines.append(f"{s:<20}{ok:>4}/{tot:<5}{flag}")
        m = self.misses()
        if m:
            lines.append("")
            lines.append(f"MISSES ({len(m)}):")
            for r in m:
                lines.append(f"  [{r['class']}] {r['path']}\n      gold: {short(r['gold'])}\n      got:  {short(r['got'])}")
        if self.extras:
            lines.append("")
            lines.append(f"extra candidate items not in gold ({len(self.extras)}): " + ", ".join(self.extras))
        return "\n".join(lines)


def overlap(a, b) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta) if ta else 0.0


def short(v, n=110) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 3] + "..."


def evaluate(gold_path: str, cand_path: str, verbose: bool = False) -> Eval:
    with open(gold_path, encoding="utf-8") as f:
        gold = json.load(f)
    with open(cand_path, encoding="utf-8") as f:
        cand = json.load(f)
    return Eval(gold, cand, verbose).run()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gold")
    ap.add_argument("candidate")
    ap.add_argument("--json", help="write misses + summary to this file")
    ap.add_argument("--min", type=float, default=None, help="exit 1 if exact %% is below this")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    ev = evaluate(a.gold, a.candidate, a.verbose)
    print(ev.report())
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"summary": ev.summary(), "by_section": ev.by_section(), "misses": ev.misses(), "extras": ev.extras}, f, indent=1, ensure_ascii=False)
    if a.min is not None and ev.summary()["exact"]["pct"] < a.min:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
