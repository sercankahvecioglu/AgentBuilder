import copy
import json

from builder.schema import Spec
from builder.vote import vote

GOLD = json.load(open("dev/gold/brief-a.spec.json"))


def test_identical_votes_merge_to_the_same_spec():
    merged, disputes = vote([copy.deepcopy(GOLD) for _ in range(3)])
    assert disputes == []
    assert Spec.model_validate(merged).model_dump() == Spec.model_validate(GOLD).model_dump()


def test_majority_wins_and_is_logged():
    a, b, c = (copy.deepcopy(GOLD) for _ in range(3))
    c["bands"][1]["deadline_business_days"] = 9  # one outlier
    c["identity"]["max_wrong_total"]["value"] = 4
    merged, disputes = vote([a, b, c])
    assert merged["bands"][1]["deadline_business_days"] == 7
    assert merged["identity"]["max_wrong_total"]["value"] == 3
    paths = {d.path for d in disputes}
    assert "bands[8].deadline_business_days" in paths and "identity.max_wrong_total" in paths


def test_no_majority_takes_the_stricter_value():
    a, b, c = (copy.deepcopy(GOLD) for _ in range(3))
    a["opening"]["max_confirm_asks"]["value"] = 2
    b["opening"]["max_confirm_asks"]["value"] = 3
    c["opening"]["max_confirm_asks"]["value"] = 4
    a["amounts"]["too_much"]["offer_floor_once"]["value"] = True
    b["amounts"]["too_much"]["offer_floor_once"]["value"] = False
    # bool can't be 3-way; make the string leaf 3-way instead
    a["calendar"]["next_weekday"]["value"] = "following_calendar_week"
    b["calendar"]["next_weekday"]["value"] = "next_occurrence"
    c["calendar"]["next_weekday"]["value"] = "zzz"
    merged, disputes = vote([a, b, c])
    assert merged["opening"]["max_confirm_asks"]["value"] == 2
    assert merged["calendar"]["next_weekday"]["value"] == "following_calendar_week"
    assert merged["amounts"]["too_much"]["offer_floor_once"]["value"] is True  # 2/3 majority


def test_list_items_need_a_majority():
    a, b, c = (copy.deepcopy(GOLD) for _ in range(3))
    c["special_intents"].append({**c["special_intents"][0], "key": "invented_intent"})
    c["calendar"]["holidays"]["values"].append("2027-05-01")
    merged, disputes = vote([a, b, c])
    assert all(i["key"] != "invented_intent" for i in merged["special_intents"])
    assert "2027-05-01" not in merged["calendar"]["holidays"]["values"]
    assert Spec.model_validate(merged)
