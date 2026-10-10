"""Unit tests for builder/resolve.py (DEV_PLAN T3.3 AC). Run: python -m pytest dev/tests -q"""
from builder.resolve import auto_conflicts, numbers_in, resolve, stricter
from builder.schema import Conflict, Extraction, Fact


def fact(id, value, *, kind="decision", doc_label="policy.md", doc_date="", effective_from="", topic="callback_to",
         operator="<=", stage="third_party", scope="", conditions="", text=None):
    return Fact(id=id, text=text or f"callback window ends at {value}", agent_instruction="", source_quote=f"... {value} ...",
                doc_label=doc_label, doc_date=doc_date, effective_from=effective_from, kind=kind, stage=stage,
                topic=topic, scope=scope, conditions=conditions, exceptions="", operator=operator, value=value)


def test_newer_memo_wins():
    ex = Extraction(facts=[fact("F1", "19:00", doc_date="2026-01-10"), fact("F2", "18:00", doc_label="memo.eml", doc_date="2026-03-01")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert r.governing_ids == ["F2"]
    assert r.overrides[0].winner == "F2" and r.overrides[0].loser == "F1"
    assert not r.unresolved and not r.date_conditional


def test_discussion_is_ignored():
    ex = Extraction(facts=[fact("F1", "19:00", doc_date="2026-01-10"),
                           fact("F2", "21:00", kind="discussion", doc_label="thread.eml", doc_date="2026-04-01")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert r.governing_ids == ["F1"]
    assert r.dropped_discussion == ["F2"]
    assert not r.overrides and not r.unresolved


def test_equal_date_unknown_kind_is_unresolved_with_stricter_default():
    ex = Extraction(facts=[fact("F1", "19:00", doc_label="doc1", doc_date="2026-01-10"),
                           fact("F2", "18:00", doc_label="doc2", doc_date="2026-01-10")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert len(r.unresolved) == 1
    assert r.unresolved[0].chosen_id == "F2"  # smaller cap under '<='
    assert r.governing_ids == ["F2"]


def test_equal_date_memo_beats_policy():
    ex = Extraction(facts=[fact("F1", "18:00", doc_label="policy extract"), fact("F2", "19:00", doc_label="memo 12")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert r.governing_ids == ["F2"]
    assert r.overrides[0].rule.startswith("amendment/memo")


def test_effective_from_gives_date_conditional_pair():
    ex = Extraction(facts=[fact("F1", "7", topic="deadline_days", operator="nth_business_day", doc_date="2026-01-01"),
                           fact("F2", "5", topic="deadline_days", operator="nth_business_day", doc_label="memo", doc_date="2026-09-01",
                                effective_from="2026-11-01")],
                    conflicts=[Conflict(topic="deadline_days", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert sorted(r.governing_ids) == ["F1", "F2"]  # both stay; code switches at runtime
    assert r.date_conditional == [type(r.date_conditional[0])(topic="deadline_days", before_id="F1", from_date="2026-11-01", after_id="F2")]
    assert not r.unresolved


def test_stricter_minimum_is_larger():
    a, b = fact("F1", "3", operator=">="), fact("F2", "5", operator=">=")
    assert stricter(a, b)[0].id == "F2"


def test_auto_conflict_detection():
    fs = [fact("F1", "19:00", doc_date="2026-01-01"), fact("F2", "18:00", doc_date="2026-02-01")]
    cs = auto_conflicts(fs)
    assert len(cs) == 1 and sorted(cs[0].fact_ids) == ["F1", "F2"]
    r = resolve(Extraction(facts=fs, conflicts=[]))  # no LLM conflict list, still resolved
    assert r.governing_ids == ["F2"]


def test_numbers_in_words_and_ordinals():
    assert numbers_in("the 12th business day") == [12.0]
    assert numbers_in("three wrong answers in total") == [3.0]
    assert numbers_in("the twelfth business day after today") == [12.0]
    assert numbers_in("from 10:00 to 19:00") == [10.0, 0.0, 19.0, 0.0]
    assert 21.0 in numbers_in("twenty-one days") and 250.0 in numbers_in("two hundred and fifty euros")
    assert numbers_in("ask once") == [1.0]
