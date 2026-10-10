"""Spike 1 workflow: answers S1-S9 in one scripted chat session (dev material, never used by the builder).

Covers:
  S1 pre/post hooks on a pre_actions api_call (api_request node)
  S2 form of get_account products in vars (mapped list vs flattened)
  S3 extraction: assistant turns visible? date anchor (real clock vs now)? {{var}} in description? float in words?
  S4 reset of an extracted enum by code: does it re-appear from older turns?
  S5 on_enter tts on the close node spoken before pre_actions? ledger + transcript order with end_call none
  S6 {{x:json}} baked number, baked product_id/date from code vars
  S7 failure shape on an api_request node, counters, post-hook on failure
  S8 code -> api -> code re-entering the same api node
  S9 code node right after a conversation node in chat/message
"""
import json, sys, pathlib

API = json.load(open(pathlib.Path(__file__).resolve().parents[2] / "tools" / "openapi.json"))
BASE = API["servers"][0]["url"]


def api_tool(name, body_defaults, pre="", post="", retries=0):
    """One api_call function. body_defaults: {field: default string}."""
    t = {
        "type": "function",
        "config": {"timeoutMs": 12000, "maxRetries": retries},
        "function": {
            "name": name,
            "handler": "__function__:api_call",
            "description": f"Call {name}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": f"{BASE}/{name}"},
                    "method": {"type": "string", "default": "POST"},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": {k: {"type": "string", "default": v} for k, v in body_defaults.items()}, "required": list(body_defaults)},
                },
            },
        },
    }
    # amount must be typed number for the bank
    if "amount" in body_defaults:
        t["function"]["parameters"]["properties"]["body"]["properties"]["amount"]["type"] = "number"
    if pre: t["pre_process_code"] = pre
    if post: t["post_process_code"] = post
    return t


def always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def eq(target, var, val, desc=""):
    return {"target_node": target, "description": desc or f"{var} == {val}", "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": val}]}}


def code_node(name, code, nxt, transitions=None):
    return {
        "name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                        "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}, "timeout_ms": {"type": "number", "default": 10000}}}}}],
        "transitions": (transitions or []) + [always(nxt)],
    }


def api_node(name, tool, nxt, transitions=None, mapping=None, on_enter=None):
    return {
        "name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": nxt,
        "on_enter": on_enter or {"type": "silent"}, "disable_inactivity_monitor": True,
        "pre_actions": [tool], "response_mapping": mapping or [],
        "transitions": (transitions or []) + [always(nxt)],
    }


def end_node(name, fn):
    return {"name": name, "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": fn, "handler": "__function__:end_call",
                         "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}}}


EXTRACT = [
    {"name": "intent", "type": "string", "enum_values": ["go", "stop", "none"], "min_confidence": 0.6,
     "description": "Based only on the customer's latest message: 'go' if the customer says the word go, 'stop' if the customer says the word stop, otherwise 'none'."},
    {"name": "d_test", "type": "date", "min_confidence": 0.6, "description": "The payment date the customer mentions or agrees to in the latest message."},
    {"name": "amt", "type": "float", "min_confidence": 0.6, "description": "The amount of money the customer says they will pay, as a number."},
    {"name": "dob_said", "type": "date", "min_confidence": 0.6, "description": "The date of birth the customer states, if any."},
]

POST_VERIFY = """try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        vars['s1_post'] = 'ran'
        vars['s1_post_count'] = str(int(vars.get('s1_post_count') or 0) + 1)
        if isinstance(d, dict):
            vars['v_status'] = 'verified' if str(d.get('verified')).lower() == 'true' else 'wrong'
            d['what_to_do_next'] = 'ok'
        else:
            vars['v_status'] = 'noresult'
except Exception as e:
    vars['v_status'] = 'hookerror'
    vars['s1_err'] = str(e)
"""
PRE_VERIFY = """import json
try:
    vars['s1_pre'] = 'ran'
    vars['s1_pre_body'] = json.dumps(config.get('body')) if isinstance(config, dict) else 'noconfig'
except Exception as e:
    vars['s1_pre'] = 'err ' + str(e)
"""

POST_GA = """import json
try:
    if isinstance(result, dict):
        result.pop('header', None)
        vars['ga_post'] = 'ran'
        d = result.get('data')
        if isinstance(d, dict):
            vars['ga_products_json'] = json.dumps(d.get('products'))
except Exception as e:
    vars['ga_post'] = 'err ' + str(e)
"""

ACCOUNT_FACTS = """import json, datetime
try:
    vars['s9_code_ran'] = 'yes'
    p = vars.get('products')
    vars['s2_type'] = type(p).__name__
    try:
        vars['s2_repr'] = json.dumps(p)[:400]
    except Exception:
        vars['s2_repr'] = str(p)[:400]
    vars['s2_flat'] = str(vars.get('get_account_response.data.products.0.product_id'))
    prods = None
    if isinstance(p, list):
        prods = p
    elif isinstance(p, str):
        try:
            prods = json.loads(p)
        except Exception:
            prods = None
    if not prods:
        pj = vars.get('ga_products_json')
        if isinstance(pj, str):
            prods = json.loads(pj)
    first = prods[0] if isinstance(prods, list) and prods else {}
    vars['p_product'] = str(first.get('product_id') or vars.get('get_account_response.data.products.0.product_id') or 'p1')
    vars['p_amount'] = float(first.get('past_due') or vars.get('get_account_response.data.products.0.past_due') or 0)
    now = datetime.date.fromisoformat(str(vars.get('now'))[:10])
    vars['p_date'] = (now + datetime.timedelta(days=2)).isoformat()
    vars['attempts'] = '0'
    vars['pr_status'] = ''
    vars['s9_err'] = ''
except Exception as e:
    vars['s9_err'] = str(e)
    vars['p_product'] = 'p1'
    vars['p_amount'] = 1.0
    vars['p_date'] = '2000-01-01'
    vars['attempts'] = '0'
    vars['pr_status'] = ''
"""

PRE_PROMISE = """import json
try:
    vars['pr_pre_count'] = str(int(vars.get('pr_pre_count') or 0) + 1)
    b = config.get('body') if isinstance(config, dict) else None
    if isinstance(b, dict) and 'amount' in b:
        b['amount'] = float(b['amount'])
        vars['pr_coerced'] = 'yes'
    vars['pr_body_seen'] = json.dumps(config.get('body')) if isinstance(config, dict) else 'noconfig'
except Exception as e:
    vars['pr_pre_err'] = str(e)
"""
POST_PROMISE = """import json
try:
    vars['pr_post_count'] = str(int(vars.get('pr_post_count') or 0) + 1)
    if isinstance(result, dict):
        result.pop('header', None)
        vars['pr_result_keys'] = ','.join(sorted(result.keys()))
        vars['pr_result_status'] = str(result.get('status'))
        d = result.get('data')
        if isinstance(d, dict) and str(d.get('ok')).lower() == 'true' and d.get('promise_id'):
            vars['pr_status'] = 'ok'
        else:
            vars['pr_status'] = 'failed'
            vars['pr_fail_data'] = str(d)[:200]
    else:
        vars['pr_status'] = 'failed'
        vars['pr_result_keys'] = type(result).__name__
except Exception as e:
    vars['pr_status'] = 'failed'
    vars['pr_post_err'] = str(e)
"""

PROMISE_RETRY = """try:
    a = int(vars.get('attempts') or 0) + 1
    vars['attempts'] = str(a)
    vars['s7_node_fc'] = str(vars.get('do_promise_failure_count'))
    vars['s7_node_sc'] = str(vars.get('do_promise_success_count'))
    vars['s7_tool_fc'] = str(vars.get('create_promise_failure_count'))
    vars['s7_resp_status'] = str(vars.get('create_promise_response.status'))
    vars['s7_resp_code'] = str(vars.get('create_promise_response.status_code'))
    vars['s7_resp_err'] = str(vars.get('create_promise_response.error'))
    vars['s7_pr_status_before'] = str(vars.get('pr_status'))
    vars['pr_status'] = ''
    vars['retry'] = 'yes' if a < 2 else 'no'
except Exception as e:
    vars['retry'] = 'no'
    vars['s7_err'] = str(e)
"""

RESET_INTENT = """try:
    vars['s4_hits'] = str(int(vars.get('s4_hits') or 0) + 1)
    vars['s4_intent_seen'] = str(vars.get('intent'))
    vars['intent'] = 'none'
    vars['s9_after_conv'] = 'yes'
except Exception as e:
    vars['s4_err'] = str(e)
"""

wf = {
    "initial_node": "start",
    "system_prompt": "You are a test assistant. Speak English. One short sentence per turn. Never call a tool.",
    "test_variables": {},
    "global_nodes": {},
    "nodes": {
        "start": {
            "name": "start", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "Test start. I propose Friday the sixteenth of October. Does that work?"},
            "on_enter_first_entry_only": True,
            "task_message": "Say only: 'Noted.' No tool call is allowed in this turn.",
            "extraction_schema": EXTRACT,
            "transitions": [eq("reset_intent", "intent", "go"), always("start")],
        },
        "reset_intent": code_node("reset_intent", RESET_INTENT, "start2"),
        "start2": {
            "name": "start2", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "Reset done. I propose Friday the sixteenth of October for four hundred and twenty. Does that work?"},
            "on_enter_first_entry_only": True,
            "task_message": "Say only: 'Noted.' No tool call is allowed in this turn.",
            "extraction_schema": EXTRACT,
            "transitions": [eq("reset_intent", "intent", "go"), eq("do_verify1", "intent", "stop"), always("start2")],
        },
        "do_verify1": api_node("do_verify1",
            api_tool("verify_identity", {"customer_id": "{{customer_id}}", "field": "{{id_field1}}", "answer": "{{id_answer1}}"}, pre=PRE_VERIFY, post=POST_VERIFY),
            "end_fail", transitions=[eq("do_verify2", "v_status", "verified")], mapping=[{"path": "data.verified", "variable": "v1_mapped"}]),
        "do_verify2": api_node("do_verify2",
            api_tool("verify_identity", {"customer_id": "{{customer_id}}", "field": "{{id_field2}}", "answer": "{{id_answer2}}"}, pre=PRE_VERIFY, post=POST_VERIFY),
            "end_fail", transitions=[eq("load_account", "v_status", "verified")], mapping=[{"path": "data.verified", "variable": "v2_mapped"}]),
        "load_account": api_node("load_account", api_tool("get_account", {"customer_id": "{{customer_id}}"}, post=POST_GA, retries=1),
            "account_facts", mapping=[{"path": "data.products", "variable": "products"}]),
        "account_facts": code_node("account_facts", ACCOUNT_FACTS, "do_promise"),
        "do_promise": api_node("do_promise",
            api_tool("create_promise", {"customer_id": "{{customer_id}}", "product_id": "{{p_product}}", "amount": "{{p_amount:json}}", "date": "{{p_date}}"}, pre=PRE_PROMISE, post=POST_PROMISE),
            "promise_retry", transitions=[eq("say_recorded", "pr_status", "ok")]),
        "promise_retry": code_node("promise_retry", PROMISE_RETRY, "goodbye_fail", transitions=[eq("do_promise", "retry", "yes")]),
        "say_recorded": {
            "name": "say_recorded", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "Your promise is recorded after {{attempts}} retries. Say bye to finish."},
            "task_message": "Say only: 'Please say bye.' No tool call is allowed in this turn.",
            "extraction_schema": [{"name": "bye", "type": "string", "enum_values": ["bye", "none"], "min_confidence": 0.6, "description": "Based only on the customer's latest message: 'bye' if the customer says bye or goodbye, otherwise 'none'."}],
            "transitions": [eq("goodbye", "bye", "bye"), always("say_recorded")],
        },
        "goodbye": {
            "name": "goodbye", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "Thank you for your time and goodbye."},
            "task_message": "Say goodbye in three words. No tool call is allowed in this turn.",
            "transitions": [always("close_promise")],
        },
        "close_promise": api_node("close_promise", api_tool("close_call", {"customer_id": "{{customer_id}}", "outcome": "promise"}, post="try:\n    result.pop('header', None)\n    vars['close_post'] = 'ran'\nexcept Exception:\n    pass\n"),
            "end_promise"),
        "end_promise": end_node("end_promise", "promise"),
        "goodbye_fail": {
            "name": "goodbye_fail", "node_type": "conversation",
            "on_enter": {"type": "tts", "text": "I could not record the promise. Say bye to finish."},
            "task_message": "Say only: 'Please say bye.' No tool call is allowed in this turn.",
            "extraction_schema": [{"name": "bye", "type": "string", "enum_values": ["bye", "none"], "min_confidence": 0.6, "description": "Based only on the customer's latest message: 'bye' if the customer says bye or goodbye, otherwise 'none'."}],
            "transitions": [eq("close_fail", "bye", "bye"), always("goodbye_fail")],
        },
        "close_fail": api_node("close_fail", api_tool("close_call", {"customer_id": "{{customer_id}}", "outcome": "no_promise", "reason": "service_error"}),
            "end_fail", on_enter={"type": "tts", "text": "Thank you and goodbye. This line is spoken by the close node."}),
        "end_fail": end_node("end_fail", "no_promise"),
    },
}

out = pathlib.Path(__file__).resolve().parent / "spike1.workflow.json"
out.write_text(json.dumps(wf, indent=1))
s = json.dumps(wf)
assert "null" not in s, "null in workflow"
for n, node in wf["nodes"].items():
    for pa in node.get("pre_actions", []):
        c = pa["function"]["parameters"]["properties"].get("code", {}).get("default", "")
        assert "{{" not in c and "}}" not in c, f"braces in code of {n}"
print("wrote", out, "nodes", len(wf["nodes"]))
