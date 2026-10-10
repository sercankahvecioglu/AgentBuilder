"""builder/verify.py against the gold spec + gold facts (DEV_PLAN T4.1 AC: seeded wrong values are caught)."""
import copy
import json

import pytest

from builder.inputs import api_summary, load_api, load_text_inputs
from builder.resolve import Resolution
from builder.schema import Extraction, Spec
from builder.verify import errors, verify

GOLD = "dev/gold/brief-a.spec.json"


@pytest.fixture(scope="module")
def ctx():
    spec = json.load(open(GOLD))
    ex = Extraction.model_validate(json.load(open("dev/gold/brief-a.facts.json")))
    res = Resolution.model_validate(json.load(open("dev/gold/brief-a.resolution.json")))
    api = api_summary(load_api("tools/openapi.json"))
    text = load_text_inputs(["briefs/brief-a.md"])
    return spec, ex, res, api, text


def run(ctx, spec_dict):
    _, ex, res, api, text = ctx
    return verify(Spec.model_validate(spec_dict), ex.facts, res, api, text)


def test_gold_is_clean(ctx):
    issues = run(ctx, ctx[0])
    assert errors(issues) == [], [str(i) for i in errors(issues)]


def seeded(ctx, mutate):
    c = copy.deepcopy(ctx[0])
    mutate(c)
    return [str(i) for i in errors(run(ctx, c))]


def test_wrong_number_vs_quote(ctx):
    def m(c): c["bands"][1]["deadline_business_days"] = 10  # quote says 7th
    out = seeded(ctx, m)
    assert any("bands" in e and "10" in e for e in out), out


def test_wrong_count_leaf(ctx):
    def m(c): c["identity"]["max_wrong_total"]["value"] = 4  # quote says three
    assert any("max_wrong_total" in e for e in seeded(ctx, m))


def test_identity_field_not_in_enum(ctx):
    def m(c): c["identity"]["questions"][1]["api_field"] = "phone_last_four"
    assert any("api_field" in e for e in seeded(ctx, m))


def test_queue_not_in_enum(ctx):
    def m(c):
        it = next(i for i in c["special_intents"] if i["key"] == "wants_human")
        it["action_queue"] = "humans"
    assert any("action_queue" in e for e in seeded(ctx, m))


def test_close_pair_not_in_table(ctx):
    def m(c): c["identity"]["fail_close"]["reason"] = "wrong"
    assert any("fail_close" in e for e in seeded(ctx, m))


def test_bad_holiday_and_time(ctx):
    def m(c):
        c["calendar"]["holidays"]["values"][0] = "2026-13-01"
        c["third_party"]["callback"]["to_time"]["value"] = "7pm"
    out = seeded(ctx, m)
    assert any("holidays" in e for e in out) and any("to_time" in e for e in out)


def test_non_contiguous_bands(ctx):
    def m(c): c["bands"][1]["days_late_min"] = 9
    assert any("contiguous" in e for e in seeded(ctx, m))


def test_required_phrase_must_be_verbatim(ctx):
    def m(c): c["required_phrases"][4]["text"] = "You will get a text message confirming this promise."
    assert any("required_phrases[4]" in e for e in seeded(ctx, m))


def test_unknown_and_discussion_fact_ids(ctx):
    spec, ex, res, api, text = ctx
    c = copy.deepcopy(spec)
    c["opening"]["max_confirm_asks"]["fact_ids"] = ["F999"]
    out = [str(i) for i in errors(verify(Spec.model_validate(c), ex.facts, res, api, text))]
    assert any("unknown fact id F999" in e for e in out)
    # a discussion fact cited by a leaf
    ex2 = copy.deepcopy(ex)
    ex2.facts[0].kind = "discussion"
    fid = ex2.facts[0].id
    res2 = Resolution.model_validate({**res.model_dump(), "governing_ids": [g for g in res.governing_ids if g != fid]})
    out = [str(i) for i in errors(verify(Spec.model_validate(spec), ex2.facts, res2, api, text))]
    assert any(f"discussion fact {fid}" in e for e in out)


def test_unused_governing_fact_is_warned(ctx):
    spec, ex, res, api, text = ctx
    ex2 = copy.deepcopy(ex)
    ex2.facts.append(copy.deepcopy(ex.facts[0]))
    ex2.facts[-1].id = "A-R99"
    res2 = Resolution.model_validate({**res.model_dump(), "governing_ids": res.governing_ids + ["A-R99"]})
    issues = verify(Spec.model_validate(spec), ex2.facts, res2, api, text)
    assert any(i.severity == "warn" and "A-R99" in i.message for i in issues)
