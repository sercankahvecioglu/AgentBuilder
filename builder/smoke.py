"""Smoke test through POST /api/v2/chat/message (T7.2): two turns, no bank tool call, warnings only.

Facts from the spikes: in chat the initial node's on_enter is not spoken and the first turn's routing is suppressed,
so turn 1 ("Hello?") shows the opening the model writes from its task text; turn 2 (a confirmation) must reach the
first security question. The customer id is a dummy, so no bank write can happen before identity (verify would fail).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import freya  # noqa: E402
from builder.generate import tv  # noqa: E402
from builder.schema import Spec  # noqa: E402


def run_smoke(workflow_id: str, spec: Spec) -> List[str]:
    warnings: List[str] = []
    variables = {cv.name: f"smoke_{cv.name}" for cv in spec.call_variables}
    variables[tv(spec.roles.customer_id_var)] = "c_smoke_no_such_customer"
    variables[tv(spec.roles.now_var)] = time.strftime("%Y-%m-%dT%H:%M")
    forbidden = [w.lower() for w in tv(spec.opening.forbidden_before_identity)]
    first = tv(spec.opening.first_sentence)
    call_id = None
    replies = []
    accept = (tv(spec.opening.accept_examples) or ["yes"])[0]
    for msg in ["Hello?", accept]:
        body = {"workflowId": workflow_id, "message": msg, "customerVariables": variables}
        if call_id:
            body["callId"] = call_id
        try:
            r = freya.api("POST", "/api/v2/chat/message", body)
        except RuntimeError as e:
            warnings.append(f"smoke: chat turn failed: {str(e)[:200]}")
            break
        call_id = r.get("callId") or call_id
        replies.append(str(r.get("response") or ""))
    if call_id:
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
        except RuntimeError:
            pass
    if replies:
        r0 = replies[0].lower()
        key_words = [w for w in re.findall(r"[a-z]+", first.lower()) if len(w) > 4][:6]
        missing = [w for w in key_words if w not in r0]
        if missing:
            warnings.append(f"smoke: opening reply lacks words of the first sentence: {missing}; reply={replies[0][:200]!r}")
        bad = [w for w in forbidden if re.search(r"\b" + re.escape(w.split()[-1]) + r"\b", r0)]
        if bad:
            warnings.append(f"smoke: forbidden words before identity in the opening: {bad}")
    if len(replies) > 1:
        r1 = replies[1].lower()
        bad = [w for w in forbidden if re.search(r"\b" + re.escape(w.split()[-1]) + r"\b", r1)]
        if bad:
            warnings.append(f"smoke: forbidden words before identity in turn 2: {bad}")
        q0 = spec.identity.questions[0] if spec.identity.questions else None
        if q0 and not any(w in r1 for w in re.findall(r"[a-z]{4,}", q0.api_field.replace("_", " "))):
            warnings.append(f"smoke: turn 2 does not look like the first security question ({q0.api_field}): {replies[1][:200]!r}")
    return warnings + [f"smoke reply {i + 1}: {r[:300]}" for i, r in enumerate(replies)]


def run_smoke_generic(workflow_id: str, wf: dict) -> List[str]:
    """Two chat turns with the workflow's own test_variables (agent build mode: no spec to check against)."""
    variables = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in (wf.get("test_variables") or {}).items()}
    replies, warnings = [], []
    call_id = None
    for msg in ["Alo?", "Evet."]:
        body = {"workflowId": workflow_id, "message": msg, "customerVariables": variables}
        if call_id:
            body["callId"] = call_id
        try:
            r = freya.api("POST", "/api/v2/chat/message", body)
        except RuntimeError as e:
            warnings.append(f"smoke: chat turn failed: {str(e)[:200]}")
            break
        call_id = r.get("callId") or call_id
        replies.append(str(r.get("response") or ""))
    if call_id:
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
        except RuntimeError:
            pass
    if not replies or not replies[0].strip():
        warnings.append("smoke: no reply to the first turn")
    return warnings + [f"smoke reply {i + 1}: {r[:300]}" for i, r in enumerate(replies)]
