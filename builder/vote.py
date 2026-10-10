"""Field-wise majority over several independent extractions (DEV_PLAN T3.5, `--votes 3`).

vote(specs) -> (merged Spec dict, disputes)
- Leaves are compared by dotted path; list items of the spec's keyed lists (bands, questions, intents, outcome rows,
  ...) are aligned by their key (same keys as dev/eval_extract.py), unkeyed lists of strings are merged by item majority.
- Majority wins. Without a majority (every vote differs) the stricter value is taken: the smaller number, False for a
  permission-like boolean (names starting with allowed_/offer_/continue_), True for a constraint-like boolean (the rest),
  the lexicographically first string (stable). Every disagreement is logged as a dispute for the trace.
- `fact_ids` of the winning vote are kept; when values tie, fact ids are unioned.
Code-relevant disputes are expected to be settled afterwards by verify's quote re-parse (T4.1).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel

LIST_KEYS = {
    "call_variables": lambda o: o.get("name", ""),
    "identity.questions": lambda o: o.get("api_field", ""),
    "bands": lambda o: str(o.get("days_late_min", "")),
    "debt_statement.product_labels": lambda o: o.get("product_type", ""),
    "amounts.floor_field_by_type": lambda o: o.get("product_type", ""),
    "negotiation.attempts": lambda o: str(o.get("n", "")),
    "closing.outcome_table": lambda o: f"{o.get('outcome','')}/{o.get('reason','')}",
    "closing.aggregation.all_noted_as": lambda o: o.get("reason", ""),
    "required_phrases": lambda o: re.sub(r"[^a-z0-9{}]", "", str(o.get("text", "")).lower()),
    "special_intents": lambda o: o.get("key", ""),
    "behaviour_rules": lambda o: re.sub(r"[^a-z0-9]", "", str(o.get("agent_instruction", "")).lower())[:60],
    "unresolved": lambda o: o.get("topic", ""),
    "date_conditional": lambda o: f"{o.get('field_path','')}@{o.get('effective_from','')}",
}
PERMISSIVE_BOOL = re.compile(r"(^|\.)(allowed_|offer_|continue_|enabled$|wrong_may_retry$|proposal_is_not_refusal$)")


class Dispute(BaseModel):
    path: str
    votes: list[Any]
    chosen: Any
    how: str


def _bare(path: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", path)


def _stricter(path: str, values: list[Any]) -> tuple[Any, str]:
    v0 = values[0]
    if isinstance(v0, bool):
        strict = False if PERMISSIVE_BOOL.search(path) else True
        return strict, "no majority: stricter boolean"
    if isinstance(v0, (int, float)):
        return min(values), "no majority: smallest number"
    if isinstance(v0, str):
        return sorted(values)[0], "no majority: first string in sort order"
    return v0, "no majority: first vote"


def _majority(path: str, values: list[Any], disputes: list[Dispute]) -> Any:
    keyed = [json.dumps(v, sort_keys=True) for v in values]
    counts = Counter(keyed)
    top, n = counts.most_common(1)[0]
    if n == len(values):
        return values[0]
    if n > len(values) / 2:
        chosen = json.loads(top)
        disputes.append(Dispute(path=path, votes=values, chosen=chosen, how=f"majority {n}/{len(values)}"))
        return chosen
    chosen, how = _stricter(path, values)
    disputes.append(Dispute(path=path, votes=values, chosen=chosen, how=how))
    return chosen


def _merge(path: str, nodes: list[Any], disputes: list[Dispute]) -> Any:
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return None
    first = nodes[0]
    if isinstance(first, dict):
        if "fact_ids" in first and set(first) <= {"value", "fact_ids"}:
            vals = [n.get("value") for n in nodes]
            chosen = _majority(path, vals, disputes)
            ids = _ids_for(nodes, "value", chosen)
            return {"value": chosen, "fact_ids": ids}
        if "fact_ids" in first and set(first) <= {"values", "fact_ids"}:
            chosen = _merge_string_list(path, [n.get("values", []) for n in nodes], disputes)
            return {"values": chosen, "fact_ids": _union_ids(nodes)}
        out = {}
        for k in first:
            if k == "fact_ids":
                continue
            out[k] = _merge(f"{path}.{k}" if path else k, [n.get(k) for n in nodes if isinstance(n, dict)], disputes)
        if "fact_ids" in first:
            out["fact_ids"] = _union_ids(nodes)
        return out
    if isinstance(first, list):
        keyfn = LIST_KEYS.get(_bare(path))
        if keyfn is None:
            if all(isinstance(x, str) for n in nodes for x in n):
                return _merge_string_list(path, nodes, disputes)
            return _majority(path, nodes, disputes)
        # keyed list: keep items present in a majority of votes, merge each by key
        buckets: dict[str, list[dict]] = {}
        order: list[str] = []
        for n in nodes:
            seen = set()
            for item in n:
                k = keyfn(item)
                if k in seen:
                    continue
                seen.add(k)
                if k not in buckets:
                    buckets[k] = []
                    order.append(k)
                buckets[k].append(item)
        out = []
        for k in order:
            items = buckets[k]
            if len(items) * 2 > len(nodes) or len(nodes) == 1:
                out.append(_merge(f"{path}[{k}]", items, disputes))
            else:
                disputes.append(Dispute(path=f"{path}[{k}]", votes=[len(items), len(nodes)], chosen=None,
                                        how=f"item present in {len(items)}/{len(nodes)} votes: dropped"))
        return out
    return _majority(path, nodes, disputes)


def _merge_string_list(path: str, lists: list[list[str]], disputes: list[Dispute]) -> list[str]:
    counts: Counter = Counter()
    order: list[str] = []
    for lst in lists:
        for x in dict.fromkeys(lst):
            if x not in counts:
                order.append(x)
            counts[x] += 1
    out = [x for x in order if counts[x] * 2 > len(lists) or len(lists) == 1]
    dropped = [x for x in order if x not in out]
    if dropped:
        disputes.append(Dispute(path=path, votes=lists, chosen=out, how=f"items without majority dropped: {dropped}"))
    return out


def _ids_for(nodes: list[dict], key: str, chosen: Any) -> list[str]:
    ids: list[str] = []
    for n in nodes:
        if n.get(key) == chosen:
            for i in n.get("fact_ids", []):
                if i not in ids:
                    ids.append(i)
    return ids or _union_ids(nodes)


def _union_ids(nodes: list[dict]) -> list[str]:
    ids: list[str] = []
    for n in nodes:
        for i in n.get("fact_ids", []) if isinstance(n, dict) else []:
            if i not in ids:
                ids.append(i)
    return ids


def vote(specs: list[dict]) -> tuple[dict, list[Dispute]]:
    """Merge N spec dicts (same schema) into one by field-wise majority."""
    if not specs:
        raise ValueError("no specs to vote on")
    disputes: list[Dispute] = []
    merged = _merge("", specs, disputes)
    return merged, disputes
