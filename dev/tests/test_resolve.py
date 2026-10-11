"""Unit tests for builder/resolve.py (DEV_PLAN T3.3 AC). Run: python -m pytest dev/tests -q"""
from builder.resolve import auto_conflicts, numbers_in, resolve, stricter
from builder.schema import Conflict, Document, Extraction, Fact


def Ex(facts, conflicts=(), documents=()):
    return Extraction(documents=list(documents), facts=facts, conflicts=list(conflicts))


def doc(label, kind="policy", date="", amends=""):
    return Document(label=label, date=date, kind=kind, amends=amends, note="")


def fact(id, value, *, kind="decision", doc_label="policy.md", doc_date="", effective_from="", topic="callback_to",
         operator="<=", stage="third_party", scope="", conditions="", text=None, value_kind="parameter"):
    return Fact(id=id, text=text or f"callback window ends at {value}", agent_instruction="", source_quote=f"... {value} ...",
                doc_label=doc_label, doc_date=doc_date, effective_from=effective_from, kind=kind, stage=stage,
                topic=topic, scope=scope, conditions=conditions, exceptions="", operator=operator, value=value, value_kind=value_kind)


def test_newer_memo_wins():
    ex = Ex(facts=[fact("F1", "19:00", doc_date="2026-01-10"), fact("F2", "18:00", doc_label="memo.eml", doc_date="2026-03-01")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert r.governing_ids == ["F2"]
    assert r.overrides[0].winner == "F2" and r.overrides[0].loser == "F1"
    assert not r.unresolved and not r.date_conditional


def test_discussion_is_ignored():
    ex = Ex(facts=[fact("F1", "19:00", doc_date="2026-01-10"),
                           fact("F2", "21:00", kind="discussion", doc_label="thread.eml", doc_date="2026-04-01")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert r.governing_ids == ["F1"]
    assert r.dropped_discussion == ["F2"]
    assert not r.overrides and not r.unresolved


def test_equal_date_unknown_kind_is_unresolved_with_stricter_default():
    ex = Ex(facts=[fact("F1", "19:00", doc_label="doc1", doc_date="2026-01-10"),
                           fact("F2", "18:00", doc_label="doc2", doc_date="2026-01-10")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert len(r.unresolved) == 1
    assert r.unresolved[0].chosen_id == "F2"  # smaller cap under '<='
    assert r.governing_ids == ["F2"]


def test_equal_date_memo_beats_policy():
    ex = Ex(facts=[fact("F1", "18:00", doc_label="policy extract"), fact("F2", "19:00", doc_label="memo 12")],
                    conflicts=[Conflict(topic="callback_to", fact_ids=["F1", "F2"], note="")])
    r = resolve(ex)
    assert r.governing_ids == ["F2"]
    assert r.overrides[0].rule.startswith("amendment/memo")


def test_effective_from_gives_date_conditional_pair():
    ex = Ex(facts=[fact("F1", "7", topic="deadline_days", operator="nth_business_day", doc_date="2026-01-01"),
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


def test_auto_conflict_detection_across_documents():
    fs = [fact("F1", "19:00", doc_label="policy.md", doc_date="2026-01-01"), fact("F2", "18:00", doc_label="memo.md", doc_date="2026-02-01")]
    cs = auto_conflicts(fs)
    assert len(cs) == 1 and sorted(cs[0].fact_ids) == ["F1", "F2"]
    r = resolve(Ex(facts=fs, conflicts=[]))  # no LLM conflict list, still resolved
    assert r.governing_ids == ["F2"]


def test_same_document_same_topic_is_not_a_conflict():
    # the two ends of a window, or a list of accepted phrases, share a topic inside one document
    fs = [fact("F1", "10:00", operator=">=", topic="callback_window"), fact("F2", "19:00", operator="<=", topic="callback_window"),
          fact("F3", "yes", operator="", topic="confirm_phrases"), fact("F4", "speaking", operator="", topic="confirm_phrases")]
    assert auto_conflicts(fs) == []
    r = resolve(Ex(facts=fs, conflicts=[]))
    assert sorted(r.governing_ids) == ["F1", "F2", "F3", "F4"] and not r.unresolved


def test_numbers_in_words_and_ordinals():
    assert numbers_in("the 12th business day") == [12.0]
    assert numbers_in("three wrong answers in total") == [3.0]
    assert numbers_in("the twelfth business day after today") == [12.0]
    assert numbers_in("from 10:00 to 19:00") == [10.0, 0.0, 19.0, 0.0]
    assert 21.0 in numbers_in("twenty-one days") and 250.0 in numbers_in("two hundred and fifty euros")
    assert numbers_in("ask once") == [1.0]


def test_set_members_are_additive_even_when_listed_as_a_conflict():
    hol = [fact(f"F{i}", d, topic="holiday", operator="", value_kind="set_member", doc_date="2026-06-15") for i, d in
           enumerate(["2026-12-24", "2026-12-25", "2026-12-31"], 1)]
    memo = fact("F9", "2026-11-02", topic="holiday", operator="", value_kind="set_member", doc_label="memo.md", doc_date="2026-09-20")
    ex = Ex(facts=hol + [memo], conflicts=[Conflict(topic="holiday", fact_ids=["F1", "F2", "F3", "F9"], note="memo adds a holiday")])
    r = resolve(ex)
    assert sorted(r.governing_ids) == ["F1", "F2", "F3", "F9"] and not r.unresolved and not r.overrides


def test_same_document_facts_in_one_conflict_win_or_lose_together():
    pol1 = fact("F1", "60", topic="band_max", operator="<=", doc_date="2026-06-15")
    pol2 = fact("F2", "6", topic="band_deadline", operator="nth_business_day", doc_date="2026-06-15")
    memo1 = fact("F3", "75", topic="band_max", operator="<=", doc_label="memo.md", doc_date="2026-09-20")
    memo2 = fact("F4", "field team beyond day 75", topic="band_max", operator="", doc_label="memo.md", doc_date="2026-09-20")
    ex = Ex(facts=[pol1, pol2, memo1, memo2], conflicts=[Conflict(topic="band_max", fact_ids=["F1", "F3", "F4"], note="")])
    r = resolve(ex)
    assert sorted(r.governing_ids) == ["F2", "F3", "F4"]  # memo block wins; F3 and F4 never fight each other
    assert not r.unresolved


def test_declared_amendment_wins_without_dates():
    a = fact("F1", "no notes", topic="notes", operator="", doc_label="brief-a.md")
    b = fact("F2", "note each unpromised product", topic="notes", operator="", doc_label="brief-b.md")
    docs = [doc("brief-a.md", "policy"), doc("brief-b.md", "amendment", amends="brief-a.md")]
    r = resolve(Ex([a, b], [Conflict(topic="notes", fact_ids=["F1", "F2"], note="")], docs))
    assert r.governing_ids == ["F2"] and r.overrides[0].rule == "declared amendment wins" and not r.unresolved


def test_later_input_document_breaks_a_tie():
    a = fact("F1", "yes", topic="x", operator="", doc_label="one.md")
    b = fact("F2", "no", topic="x", operator="", doc_label="two.md")
    r = resolve(Ex([a, b], [Conflict(topic="x", fact_ids=["F1", "F2"], note="")], [doc("one.md", "other"), doc("two.md", "other")]))
    assert r.governing_ids == ["F2"] and r.unresolved[0].how.startswith("later document")
