"""Deterministic conflict resolution between extracted facts (DEV_PLAN §2.3 Resolution, D4).

Precedence, applied in order to each conflict:
 1. Discussion never governs (kind == discussion is dropped from the governing set).
 2. The later `doc_date` wins. If the winner has an `effective_from` later than the loser's,
    both are kept as a date-conditional pair: code picks the one in force at the call's `now`.
 3. With equal or unknown dates, an amendment or memo beats a policy extract.
 4. Otherwise the conflict is unresolved: the stricter fact is applied as the default and logged.

"Stricter" is decided by the operator and numeric value when possible (a smaller cap, a larger
minimum, a shorter window), else by document kind, else by fact id order (stable, logged).
Conflicts come from the LLM's conflict list plus an automatic scan of decision facts that share
topic, stage, scope and conditions but carry different values.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from pydantic import BaseModel

from builder.schema import Conflict, Extraction, Fact

AMENDMENT_RE = re.compile(r"memo|amend|update|change|revis|errat|correct|addend|notice|mail|e-?mail|circular|bulletin", re.I)
POLICY_RE = re.compile(r"policy|manual|handbook|procedure|standard|spec|guideline|extract|rulebook", re.I)
UPPER_OPS = {"<=", "<", "max", "not_after", "before", "at_most", "up_to", "within", "no_later_than", "until"}
LOWER_OPS = {">=", ">", "min", "not_before", "after", "at_least", "from", "no_earlier_than"}

_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "twentieth": 20, "thirtieth": 30, "once": 1, "twice": 2, "single": 1, "both": 2,
}


def numbers_in(text: str) -> list[float]:
    """All numbers in a text: digits (incl. 1,250.50 and 12th) and number words (incl. 'twenty-one')."""
    out: list[float] = []
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    toks = re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())
    i = 0
    while i < len(toks):
        tok = toks[i]
        parts = tok.split("-")
        val = None
        if all(p in _WORDS for p in parts):
            val = sum(_WORDS[p] for p in parts) if len(parts) > 1 else _WORDS[parts[0]]
            # "twenty one" / "one hundred" / "two hundred and fifty"
            j = i + 1
            acc = val
            while j < len(toks) and toks[j] in _WORDS or (j < len(toks) and toks[j] == "and" and j + 1 < len(toks) and toks[j + 1] in _WORDS):
                if toks[j] == "and":
                    j += 1
                    continue
                w = _WORDS[toks[j]]
                if w in (100, 1000):
                    acc = (acc or 1) * w
                else:
                    acc += w
                j += 1
            val = acc
            i = j
            out.append(float(val))
            continue
        i += 1
    return out


def _parse_date(s: str) -> date | None:
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _doc_kind(f: Fact) -> str:
    label = f"{f.doc_label} {f.scope}"
    if AMENDMENT_RE.search(label):
        return "amendment"
    if POLICY_RE.search(label):
        return "policy"
    return "unknown"


def _first_number(f: Fact) -> float | None:
    nums = numbers_in(f.value) or numbers_in(f.text)
    return nums[0] if nums else None


def stricter(a: Fact, b: Fact) -> tuple[Fact, str]:
    """Pick the stricter of two facts. Returns (fact, how)."""
    na, nb = _first_number(a), _first_number(b)
    op = (a.operator or b.operator or "").strip().lower()
    if na is not None and nb is not None and na != nb:
        if op in UPPER_OPS:
            return (a if na < nb else b), f"numeric: smaller cap under operator '{op}'"
        if op in LOWER_OPS:
            return (a if na > nb else b), f"numeric: larger minimum under operator '{op}'"
        # unknown operator: a smaller number is the usual stricter reading (fewer attempts, fewer days, shorter window)
        return (a if na < nb else b), "numeric: smaller value (operator unknown)"
    ka, kb = _doc_kind(a), _doc_kind(b)
    if ka != kb and "amendment" in (ka, kb):
        return (a if ka == "amendment" else b), "document kind: amendment over policy"
    return (a if a.id < b.id else b), "fact id order (no other criterion)"


class Override(BaseModel):
    topic: str
    winner: str
    loser: str
    rule: str


class DateConditionalPair(BaseModel):
    topic: str
    before_id: str
    from_date: str
    after_id: str


class UnresolvedConflict(BaseModel):
    topic: str
    fact_ids: list[str]
    chosen_id: str
    how: str
    note: str


class Resolution(BaseModel):
    governing_ids: list[str]
    dropped_discussion: list[str]
    overrides: list[Override]
    date_conditional: list[DateConditionalPair]
    unresolved: list[UnresolvedConflict]
    notes: list[str]

    def governing(self, facts: Iterable[Fact]) -> list[Fact]:
        ids = set(self.governing_ids)
        return [f for f in facts if f.id in ids]


def auto_conflicts(facts: list[Fact]) -> list[Conflict]:
    """Decision facts from DIFFERENT documents with the same topic, stage, scope, conditions and operator but a
    different value. Within one document, same-topic facts with different values are complementary (a list of
    examples, the two ends of a window), never a conflict; cross-document conflicts are the raw-material case (D4).
    Conflicts inside one document can only come from the LLM's own conflict list."""
    groups: dict[tuple, list[Fact]] = {}
    for f in facts:
        if f.kind != "decision" or not f.value.strip():
            continue
        if f.value_kind == "set_member":
            continue  # list items add up across documents; never an automatic conflict
        key = (f.topic.strip().lower(), f.stage, f.scope.strip().lower(), f.conditions.strip().lower(), f.operator.strip().lower())
        groups.setdefault(key, []).append(f)
    out = []
    for key, fs in groups.items():
        docs = {(f.doc_label.strip().lower(), f.doc_date.strip()) for f in fs}
        vals = {f.value.strip().lower() for f in fs}
        if len(vals) > 1 and len(docs) > 1:
            # one representative per document, so a list inside one document is never split
            per_doc: dict[tuple, Fact] = {}
            for f in fs:
                per_doc.setdefault((f.doc_label.strip().lower(), f.doc_date.strip()), f)
            reps = list(per_doc.values())
            if len({f.value.strip().lower() for f in reps}) > 1:
                out.append(Conflict(topic=key[0], fact_ids=[f.id for f in reps], note="auto: same topic/scope/conditions/operator in different documents, different value"))
    return out


class _Docs:
    """Document metadata from the extraction: kind, order and declared amendment links."""

    def __init__(self, ex: Extraction):
        self.by_label = {d.label.strip().lower(): d for d in ex.documents}
        self.order = {d.label.strip().lower(): n for n, d in enumerate(ex.documents)}

    def _key(self, f: Fact) -> str:
        return f.doc_label.strip().lower()

    def amends(self, a: Fact, b: Fact) -> bool:
        """True if a's document declares (directly or through a chain) that it amends b's document."""
        cur, target, seen = self._key(a), self._key(b), set()
        while cur and cur not in seen:
            seen.add(cur)
            d = self.by_label.get(cur)
            if not d or not d.amends:
                return False
            cur = d.amends.strip().lower()
            if cur == target:
                return True
        return False

    def kind(self, f: Fact) -> str:
        d = self.by_label.get(self._key(f))
        if d and d.kind in ("amendment", "policy"):
            return d.kind
        return _doc_kind(f)

    def position(self, f: Fact) -> int:
        return self.order.get(self._key(f), -1)


def resolve(ex: Extraction) -> Resolution:
    by_id = {f.id: f for f in ex.facts}
    docs = _Docs(ex)
    dropped = [f.id for f in ex.facts if f.kind == "discussion"]
    losers: set[str] = set()
    overrides: list[Override] = []
    datecond: list[DateConditionalPair] = []
    unresolved: list[UnresolvedConflict] = []
    notes: list[str] = []

    conflicts = list(ex.conflicts)
    seen = {tuple(sorted(c.fact_ids)) for c in conflicts}
    for c in auto_conflicts(ex.facts):
        if tuple(sorted(c.fact_ids)) not in seen:
            conflicts.append(c)

    for c in conflicts:
        cands = [by_id[i] for i in c.fact_ids if i in by_id]
        missing = [i for i in c.fact_ids if i not in by_id]
        if missing:
            notes.append(f"conflict '{c.topic}': unknown fact ids {missing} ignored")
        cands = [f for f in cands if f.kind != "discussion"]  # rule 1
        if len(cands) < 2:
            if cands:
                notes.append(f"conflict '{c.topic}': only {cands[0].id} is a decision; it governs")
            continue
        # set members (one holiday, one phrase, one code) from several documents add up; they never replace each other
        if all(f.value_kind == "set_member" for f in cands):
            notes.append(f"conflict '{c.topic}': all facts are set members; additive, all govern ({', '.join(f.id for f in cands)})")
            continue
        # facts from the same document never fight each other: one representative per document, the block wins or loses together
        blocks: dict[tuple, list[Fact]] = {}
        for f in sorted(cands, key=lambda f: f.id):
            blocks.setdefault((f.doc_label.strip().lower(), f.doc_date.strip()), []).append(f)
        if len(blocks) < 2:
            notes.append(f"conflict '{c.topic}': all facts come from one document; they are complementary, all govern")
            continue
        reps = [fs[0] for fs in blocks.values()]
        reps.sort(key=lambda f: f.id)
        winner = reps[0]
        for other in reps[1:]:
            if _compatible(winner, other):
                notes.append(f"conflict '{c.topic}': {winner.id} and {other.id} are compatible (restatement or addition); both govern")
                continue
            winner, note = _beat(winner, other, c.topic, overrides, datecond, unresolved, losers, docs)
            if note:
                notes.append(note)
        # a losing representative takes its document's parameter facts in this conflict down with it; set members stay
        for key, fs in blocks.items():
            if fs[0].id in losers:
                for f in fs[1:]:
                    if f.value_kind != "set_member":
                        losers.add(f.id)
    governing = [f.id for f in ex.facts if f.kind != "discussion" and f.id not in losers]
    return Resolution(governing_ids=governing, dropped_discussion=dropped, overrides=overrides,
                      date_conditional=datecond, unresolved=unresolved, notes=notes)


def _norm_val(v: str) -> str:
    return re.sub(r"\s+", " ", v.strip().lower()).strip(" .;,")


def _is_phrase(f: Fact) -> bool:
    """A verbatim sentence or question the agent must say: several words that end like a sentence or are quoted in the source."""
    v = f.value.strip()
    if len(v.split()) < 3:
        return False
    return v[-1] in "?!." or f'"{v}"' in f.source_quote or f"\u201c{v}\u201d" in f.source_quote


def _compatible(a: Fact, b: Fact) -> bool:
    """Two facts listed as a conflict that can both be true: the same value (a restatement), a set member
    (one holiday, one code) next to a list or another member (an addition), or wording next to a non-wording
    rule (a later rule that changes how often or for how many items something is asked does not replace the
    sentence to say)."""
    if _norm_val(a.value) and _norm_val(a.value) == _norm_val(b.value):
        return True
    if "set_member" in (a.value_kind, b.value_kind):
        return True
    if _is_phrase(a) != _is_phrase(b):
        return True
    return False


def _beat(a: Fact, b: Fact, topic: str, overrides, datecond, unresolved, losers, docs: "_Docs | None" = None) -> tuple[Fact, str]:
    if docs is not None:  # rule 0: a document that declares it amends the other wins, dates or not
        for w, l in ((a, b), (b, a)):
            if docs.amends(w, l) and not docs.amends(l, w):
                ew, el = _parse_date(w.effective_from), _parse_date(l.effective_from)
                if ew and (el is None or ew > el):
                    datecond.append(DateConditionalPair(topic=topic, before_id=l.id, from_date=w.effective_from, after_id=w.id))
                    return w, f"conflict '{topic}': {w.id} (declared amendment) applies from {w.effective_from}; {l.id} before that"
                losers.add(l.id)
                overrides.append(Override(topic=topic, winner=w.id, loser=l.id, rule="declared amendment wins"))
                return w, f"conflict '{topic}': {w.id} overrides {l.id} ({w.doc_label} declares it amends {l.doc_label})"
    da, db = _parse_date(a.doc_date), _parse_date(b.doc_date)
    if da and db and da != db:  # rule 2
        w, l = (a, b) if da > db else (b, a)
        ew, el = _parse_date(w.effective_from), _parse_date(l.effective_from)
        if ew and (el is None or ew > el):
            datecond.append(DateConditionalPair(topic=topic, before_id=l.id, from_date=w.effective_from, after_id=w.id))
            # both stay governing; 1b gets the pair and `date_conditional` carries the switch
            return w, f"conflict '{topic}': {w.id} (dated {w.doc_date}) applies from {w.effective_from}; {l.id} applies before that"
        losers.add(l.id)
        overrides.append(Override(topic=topic, winner=w.id, loser=l.id, rule="later doc_date wins"))
        return w, f"conflict '{topic}': {w.id} (dated {w.doc_date}) overrides {l.id} (dated {l.doc_date})"
    ka, kb = (docs.kind(a), docs.kind(b)) if docs is not None else (_doc_kind(a), _doc_kind(b))
    if ka != kb and "amendment" in (ka, kb) and "policy" in (ka, kb):  # rule 3
        w, l = (a, b) if ka == "amendment" else (b, a)
        losers.add(l.id)
        overrides.append(Override(topic=topic, winner=w.id, loser=l.id, rule="amendment/memo beats policy extract of equal or unknown date"))
        return w, f"conflict '{topic}': memo {w.id} overrides policy {l.id} (dates equal or unknown)"
    w, how = stricter(a, b)  # rule 4
    if how.startswith("fact id order") and docs is not None and docs.position(a) != docs.position(b) and -1 not in (docs.position(a), docs.position(b)):
        # no other criterion: the document that comes later in the input pack is taken as the later material
        w = a if docs.position(a) > docs.position(b) else b
        how = "later document in the input order (no other criterion)"
    l = b if w is a else a
    losers.add(l.id)
    unresolved.append(UnresolvedConflict(topic=topic, fact_ids=[a.id, b.id], chosen_id=w.id, how=how,
                                         note=f"unresolved conflict; stricter default {w.id} applied over {l.id}"))
    return w, f"conflict '{topic}': UNRESOLVED, stricter default {w.id} applied ({how}); {l.id} set aside"
