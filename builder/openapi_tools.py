"""Tool definitions generated from the given OpenAPI file (D2). Nothing here knows any brief.

parse_api(path) -> Api: operations with url, body fields (type, enum, description, required) and response fields.
api_tool(api, op, baked, ...) -> one `api_call` function object for a node's `tools` or `pre_actions`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Op:
    name: str
    url: str
    method: str
    summary: str
    fields: Dict[str, dict]           # body property name -> schema (type, enum, description, format)
    required: List[str]
    response: Dict[str, dict]         # 200 response property name -> schema
    id_fields: List[str] = field(default_factory=list)   # response props ending in _id (expected on success)

    def enum(self, name: str) -> List[str]:
        return list((self.fields.get(name) or {}).get("enum") or [])


@dataclass
class Api:
    base_url: str
    ops: Dict[str, Op]
    title: str = ""

    def op(self, name: str) -> Op:
        if name not in self.ops:
            raise KeyError(f"tool API has no operation named {name!r}; it has {sorted(self.ops)}")
        return self.ops[name]

    def product_fields(self) -> Dict[str, dict]:
        """Properties of one product in the account lookup response, if the API has such a list."""
        for op in self.ops.values():
            for pname, pschema in op.response.items():
                if pschema.get("type") == "array" and isinstance(pschema.get("items"), dict):
                    props = pschema["items"].get("properties") or {}
                    if any(k.endswith("_id") for k in props):
                        return props
        return {}

    def product_list_field(self) -> str:
        for op in self.ops.values():
            for pname, pschema in op.response.items():
                if pschema.get("type") == "array" and isinstance(pschema.get("items"), dict):
                    if any(k.endswith("_id") for k in (pschema["items"].get("properties") or {})):
                        return pname
        return "products"


def parse_api(path: str) -> Api:
    doc = json.load(open(path, encoding="utf-8"))
    servers = doc.get("servers") or []
    base = (servers[0].get("url") if servers else "") or ""
    base = base.rstrip("/")
    ops: Dict[str, Op] = {}
    for p, methods in (doc.get("paths") or {}).items():
        for method, od in methods.items():
            if method.lower() not in ("post", "put", "get", "patch", "delete"):
                continue
            name = (od.get("operationId") or p.strip("/").split("/")[-1]).strip()
            body = (((od.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            fields = dict(body.get("properties") or {})
            required = list(body.get("required") or [])
            resp = {}
            r200 = (od.get("responses") or {}).get("200") or {}
            rs = ((r200.get("content") or {}).get("application/json") or {}).get("schema") or {}
            resp = dict(rs.get("properties") or {})
            ops[name] = Op(name=name, url=base + p, method=method.upper(), summary=od.get("summary", ""), fields=fields,
                           required=required, response=resp, id_fields=[k for k in resp if k.endswith("_id")])
    return Api(base_url=base, ops=ops, title=(doc.get("info") or {}).get("title", ""))


def _leaf(schema: dict, default: Optional[str], description: str = "") -> dict:
    leaf = {"type": schema.get("type", "string")}
    if schema.get("type") == "array":
        leaf["type"] = "string"
    desc = description or schema.get("description") or ""
    if schema.get("enum"):
        leaf["enum"] = list(schema["enum"])
        desc = (desc + " One of: " + ", ".join(map(str, schema["enum"]))).strip()
    if schema.get("format"):
        desc = (desc + f" Format: {schema['format']}.").strip()
    if desc:
        leaf["description"] = desc
    if default is not None:
        leaf["default"] = default
    return leaf


def api_tool(api: Api, op_name: str, baked: Dict[str, str], description: str = "", pre: str = "", post: str = "",
             retries: int = 0, timeout_ms: int = 12000, model_descriptions: Optional[Dict[str, str]] = None,
             omit: Optional[List[str]] = None, mapping: Optional[List[dict]] = None) -> dict:
    """One api_call tool.

    baked: body field -> default string (a literal, or a `{{var}}` that is always set at node entry). Every other
    body field of the operation is model-filled: it gets `default: "{{<field>}}"` so the model sees it (tc L78-99),
    unless it is listed in `omit` (optional fields never sent).
    """
    op = api.op(op_name)
    props, required = {}, []
    for fname, fschema in op.fields.items():
        if omit and fname in omit:
            continue
        if fname in baked:
            props[fname] = _leaf(fschema, baked[fname])
        else:
            props[fname] = _leaf(fschema, "{{" + fname + "}}", (model_descriptions or {}).get(fname, ""))
            if fname in op.required:
                required.append(fname)
    t = {
        "type": "function",
        "config": {"timeoutMs": timeout_ms, "maxRetries": retries},
        "function": {
            "name": op.name,
            "handler": "__function__:api_call",
            "description": description or op.summary or f"Call {op.name}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "default": op.url},
                    "method": {"type": "string", "default": op.method},
                    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                    "body": {"type": "object", "properties": props, "required": required},
                },
            },
        },
    }
    if pre:
        t["pre_process_code"] = pre
    if post:
        t["post_process_code"] = post
    if mapping:
        t["response_mapping"] = mapping
    return t


def numeric_fields(api: Api, op_name: str) -> Dict[str, str]:
    """Body fields that must be sent as numbers: name -> 'float' | 'int'."""
    out = {}
    for fname, fschema in api.op(op_name).fields.items():
        if fschema.get("type") == "number":
            out[fname] = "float"
        elif fschema.get("type") == "integer":
            out[fname] = "int"
    return out
