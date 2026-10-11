"""Local flow simulator for a generated workflow (static tests, Phase 6).

Walks the graph like the engine would: code nodes are exec'd with a `vars` dict, api_request nodes call a fake bank
through the tool's hooks, conversation nodes take scripted turns (extraction values and/or a model tool call).
Nothing here knows any brief: the fake bank only mimics the tool API's shape (ok/error envelopes).
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Optional


class FakeBank:
    """Minimal stand-in for the bank mock: identity answers, products, fault injection, ledger."""

    def __init__(self, identity: Dict[str, str], products: List[dict], faults: Optional[List[dict]] = None, max_wrong: int = 3,
                 date_fields: Optional[List[str]] = None, swap_hint: str = "swapped"):
        self.identity = identity
        # identity fields whose answers are ISO dates, and the hint value for a day/month swap: both come from the tool API
        self.date_fields = date_fields if date_fields is not None else [k for k in identity if "date" in k or "birth" in k]
        self.swap_hint = swap_hint
        self.products = [dict(p, product_id=f"p{i + 1}") for i, p in enumerate(products)]
        self.faults = {f["tool"]: dict(f) for f in (faults or [])}
        self.max_wrong = max_wrong
        self.verified: set = set()
        self.wrong = 0
        self.calls: List[dict] = []
        self.ledger = {"outcome": None, "reason": None, "promises": [], "notes": [], "callbacks": [], "transfers": []}
        self.closed = False

    def call(self, name: str, body: dict) -> tuple:
        """Returns (status_code, body)."""
        f = self.faults.get(name)
        if f and f.get("fail_first_n", 0) > 0:
            f["fail_first_n"] -= 1
            self.calls.append({"tool": name, "result": {"ok": False, "error": "service unavailable, nothing was recorded"}})
            return 500, {"ok": False, "error": "service unavailable, nothing was recorded"}
        if self.closed:
            return 200, {"ok": False, "error": "call already closed"}
        out: dict
        if name == "verify_identity":
            field, answer = body.get("field"), str(body.get("answer", ""))
            exp = str(self.identity.get(field, ""))
            if field in self.date_fields and not re.match(r"^\d{4}-\d{2}-\d{2}$", answer):
                out = {"ok": False, "error": "unreadable date"}
            elif self.wrong >= self.max_wrong:
                out = {"ok": False, "error": "check ended"}
            elif answer == exp:
                self.verified.add(field)
                out = {"ok": True, "verified": True, "wrong_answers_left": self.max_wrong - self.wrong, "all_verified": len(self.verified) >= len(self.identity)}
            else:
                self.wrong += 1
                out = {"ok": True, "verified": False, "wrong_answers_left": self.max_wrong - self.wrong, "all_verified": False}
                if field in self.date_fields and len(answer) == 10 and len(exp) == 10 and answer[:4] == exp[:4] and answer[5:7] == exp[8:10] and answer[8:10] == exp[5:7]:
                    out["hint"] = self.swap_hint
        elif name == "get_account":
            if len(self.verified) < len(self.identity):
                out = {"ok": False, "error": "identity not verified"}
            else:
                out = {"ok": True, "products": copy.deepcopy(self.products)}
        elif name == "create_promise":
            if len(self.verified) < len(self.identity):
                out = {"ok": False, "error": "identity not verified"}
            elif body.get("product_id") not in [p["product_id"] for p in self.products]:
                out = {"ok": False, "error": "unknown product_id"}
            elif not isinstance(body.get("amount"), (int, float)):
                out = {"ok": False, "error": "amount must be a number"}
            else:
                pid = f"pr{len(self.ledger['promises']) + 1}"
                self.ledger["promises"].append({"promise_id": pid, "product_id": body["product_id"], "amount": float(body["amount"]), "date": body.get("date")})
                out = {"ok": True, "promise_id": pid}
        elif name == "add_note":
            self.ledger["notes"].append({"product_id": body.get("product_id"), "reason": body.get("reason")})
            out = {"ok": True}
        elif name == "schedule_callback":
            self.ledger["callbacks"].append({"date": body.get("date"), "time": body.get("time")})
            out = {"ok": True}
        elif name == "transfer_to_agent":
            self.ledger["transfers"].append({"queue": body.get("queue")})
            out = {"ok": True}
        elif name == "close_call":
            self.ledger["outcome"] = body.get("outcome")
            self.ledger["reason"] = body.get("reason")
            self.closed = True
            out = {"ok": True}
        else:
            out = {"ok": False, "error": "unknown tool"}
        self.calls.append({"tool": name, "result": out})
        return 200, out

    def ledger_view(self) -> dict:
        return dict(self.ledger, calls=self.calls)


class Sim:
    def __init__(self, wf: dict, bank: FakeBank, variables: dict, trace: bool = False):
        self.wf = wf
        self.bank = bank
        self.vars: Dict[str, Any] = dict(variables)
        self.vars.setdefault("no_pause", "1")
        self.trace = trace
        self.log: List[str] = []
        self.counts: Dict[str, int] = {}
        self.path: List[str] = []
        self.errors: List[str] = []

    # ---- conditions
    def cond(self, c: dict) -> bool:
        if "logic" in c:
            res = [self.cond(x) for x in c.get("conditions", [])]
            return any(res) if c["logic"] == "or" else all(res)
        op = c.get("operator")
        if op == "always":
            return True
        v = self.vars.get(c.get("variable"))
        if op == "equals":
            return str(v) == str(c.get("operand"))
        if op == "not_equals":
            return str(v) != str(c.get("operand"))
        if op == "greater_than":
            try:
                return float(v) > float(c.get("operand"))
            except Exception:
                return False
        if op == "less_than":
            try:
                return float(v) < float(c.get("operand"))
            except Exception:
                return False
        if op == "is_set":
            return v is not None and v != ""
        if op == "is_not_set":
            return v is None or v == ""
        if op == "contains":
            return str(c.get("operand")).lower() in str(v).lower()
        return False

    def route(self, node: dict) -> Optional[str]:
        for t in node.get("transitions", []):
            if self.cond(t.get("condition", {})):
                return t["target_node"]
        return None

    # ---- execution of engine-run pieces
    def exec_code(self, name: str, code: str):
        g = {"vars": self.vars}
        try:
            exec(code, g)
        except Exception as e:  # the engine would swallow it; we record it
            self.errors.append(f"{name}: {type(e).__name__}: {e}")
        if self.vars.get("snippet_error"):
            self.errors.append(f"{name}: {self.vars.pop('snippet_error')}")

    def subst(self, s: Any) -> Any:
        if not isinstance(s, str):
            return s
        m = re.fullmatch(r"\{\{(\w+)(:json)?\}\}", s)
        if m:
            v = self.vars.get(m.group(1))
            return v  # None means: field dropped
        return re.sub(r"\{\{(\w+)\}\}", lambda mm: str(self.vars.get(mm.group(1), mm.group(0))), s)

    def run_tool(self, tool: dict, model_args: Optional[dict] = None, node_name: str = "") -> dict:
        fn = tool["function"]
        name = fn["name"]
        props = fn["parameters"]["properties"]
        body_props = props.get("body", {}).get("properties", {})
        body = {}
        for k, leaf in body_props.items():
            if "default" in leaf:
                v = self.subst(leaf["default"])
                if isinstance(v, str) and re.fullmatch(r"\{\{\w+\}\}", v):
                    v = None
                if v is None and model_args and k in model_args:
                    v = model_args[k]
                if v is not None:
                    body[k] = v
            elif model_args and k in model_args:
                body[k] = model_args[k]
        config = {"url": props.get("url", {}).get("default"), "method": props.get("method", {}).get("default"), "headers": {}, "body": body}
        if tool.get("pre_process_code"):
            g = {"vars": self.vars, "config": config}
            try:
                exec(tool["pre_process_code"], g)
            except Exception as e:
                self.errors.append(f"pre-hook {name}: {e}")
        status, data = self.bank.call(name, config["body"])
        key = node_name if node_name else name
        if status != 200:
            self.counts[key + "_failure_count"] = self.counts.get(key + "_failure_count", 0) + 1
            self.vars[key + "_failure_count"] = self.counts[key + "_failure_count"]
            self.vars[key + "_response.error"] = f"HTTP {status}"
            self.log.append(f"    CALL {name} {json.dumps(config['body'])} -> HTTP {status}")
            return {"status": "error", "error": f"HTTP {status}"}
        result = {"status": "success", "data": data, "message": "ok", "status_code": 200, "header": {}}
        if tool.get("post_process_code"):
            g = {"vars": self.vars, "result": result}
            try:
                exec(tool["post_process_code"], g)
            except Exception as e:
                self.errors.append(f"post-hook {name}: {e}")
        self.counts[key + "_success_count"] = self.counts.get(key + "_success_count", 0) + 1
        self.vars[key + "_success_count"] = self.counts[key + "_success_count"]
        for k, v in (result.get("data") or {}).items():
            if not isinstance(v, (list, dict)):
                self.vars[f"{key}_response.data.{k}"] = str(v).lower() if isinstance(v, bool) else v
        if model_args:
            for k, v in model_args.items():
                self.vars[f"{name}_args.{k}"] = v
        self.log.append(f"    CALL {name} {json.dumps(config['body'])} -> {json.dumps(data)[:120]}")
        return result

    # ---- main loop
    def run(self, turns: List[dict], max_steps: int = 400) -> dict:
        """turns: list of dicts for conversation nodes, in order. Each may have:
        'set': {var: value} extraction values; 'tool': {'name':..., 'args': {...}} a model tool call; 'node': expected node (checked if given)."""
        nodes = self.wf["nodes"]
        cur = self.wf["initial_node"]
        ti = 0
        steps = 0
        ended = None
        while steps < max_steps:
            steps += 1
            node = nodes[cur]
            self.path.append(cur)
            nt = node["node_type"]
            if nt == "end_call":
                ended = node["terminal"]["function"]["name"]
                self.log.append(f"END {cur} ({ended})")
                break
            if nt == "code":
                for pa in node.get("pre_actions", []):
                    self.exec_code(cur, pa["function"]["parameters"]["properties"]["code"]["default"])
                nxt = self.route(node) or node.get("passthrough_default_transition")
                self.log.append(f"  code {cur} -> {nxt}")
                cur = nxt
                continue
            if nt == "api_request":
                for pa in node.get("pre_actions", []):
                    self.run_tool(pa, node_name=cur)
                nxt = self.route(node) or node.get("passthrough_default_transition")
                self.log.append(f"  api {cur} -> {nxt}")
                cur = nxt
                continue
            # conversation: consume one scripted turn
            if ti >= len(turns):
                self.log.append(f"  conv {cur}: no more scripted turns")
                break
            t = turns[ti]
            ti += 1
            if t.get("node") and not (cur == t["node"] or (t["node"].endswith("*") and cur.startswith(t["node"][:-1]))):
                self.errors.append(f"turn {ti}: expected node {t['node']}, was in {cur}")
            self.log.append(f"CONV {cur} <- turn {ti}: {json.dumps({k: v for k, v in t.items() if k != 'node'})[:160]}")
            for k, v in (t.get("set") or {}).items():
                self.vars[k] = v
            moved = False
            if t.get("tool"):
                tool = next((x for x in node.get("tools", []) if x["function"]["name"] == t["tool"]["name"]), None)
                if tool is None:
                    self.errors.append(f"turn {ti}: tool {t['tool']['name']} not in node {cur}")
                else:
                    self.run_tool(tool, t["tool"].get("args") or {})
                    nxt = self.route(node)
                    if nxt:
                        self.log.append(f"  route after tool {cur} -> {nxt}")
                        cur = nxt
                        moved = True
            if not moved:
                nxt = self.route(node)
                if nxt:
                    self.log.append(f"  route {cur} -> {nxt}")
                    cur = nxt
                else:
                    self.log.append(f"  stay {cur}")
        return {"ended": ended, "ledger": self.bank.ledger_view(), "errors": self.errors, "path": self.path, "turns_used": ti, "vars": self.vars}
