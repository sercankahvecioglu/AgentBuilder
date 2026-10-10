"""Load the builder's inputs: brief text files and the tool API (OpenAPI) file.

Any number of text files (md, txt, eml, csv, ...) are concatenated in order, each
labelled with its file name, so a raw-material brief (mail + policy + memo + code list)
reads as one document with document boundaries the extractor can cite.
"""
from __future__ import annotations

import json
import os
from typing import Any

API_SUFFIXES = (".json", ".yaml", ".yml")


def split_args(paths: list[str]) -> tuple[list[str], str]:
    """The last argument ending in .json/.yaml is the tool API; everything else is brief text."""
    api = [p for p in paths if p.lower().endswith(API_SUFFIXES)]
    if not api:
        raise SystemExit("no tool API file (.json/.yaml) among the inputs")
    api_path = api[-1]
    texts = [p for p in paths if p != api_path]
    if not texts:
        raise SystemExit("no brief text file among the inputs")
    return texts, api_path


def load_text_inputs(paths: list[str]) -> str:
    parts = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            body = f.read()
        parts.append(f"<document name=\"{os.path.basename(p)}\">\n{body.strip()}\n</document>")
    return "\n\n".join(parts)


def load_api(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise SystemExit("pip install pyyaml to read a YAML tool API") from e
        return yaml.safe_load(raw)
    return json.loads(raw)


def api_summary(api: dict[str, Any]) -> dict[str, Any]:
    """Operations with body fields and enums; used by the prompts and by verify.

    {"server": url, "operations": {name: {"path", "method", "summary", "fields": {field: {"type", "enum", "description", "required"}}}}}
    """
    server = (api.get("servers") or [{}])[0].get("url", "")
    ops: dict[str, Any] = {}
    for path, methods in (api.get("paths") or {}).items():
        for method, op in methods.items():
            if method.lower() not in ("post", "get", "put", "patch", "delete"):
                continue
            name = op.get("operationId") or path.strip("/").replace("/", "_")
            body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            required = set(body.get("required") or [])
            fields = {}
            for fname, fs in (body.get("properties") or {}).items():
                fields[fname] = {
                    "type": fs.get("type", ""),
                    "enum": list(fs.get("enum") or []),
                    "format": fs.get("format", ""),
                    "description": fs.get("description", ""),
                    "required": fname in required,
                }
            resp = {}
            for code, r in (op.get("responses") or {}).items():
                schema = (((r.get("content") or {}).get("application/json") or {}).get("schema") or {})
                resp[str(code)] = {"description": r.get("description", ""), "properties": _flatten_props(schema)}
            ops[name] = {"path": path, "method": method.upper(), "summary": op.get("summary", ""), "fields": fields, "responses": resp}
    return {"server": server, "title": (api.get("info") or {}).get("title", ""), "operations": ops}


def _flatten_props(schema: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (schema.get("properties") or {}).items():
        key = f"{prefix}{k}"
        if v.get("type") == "object":
            out.update(_flatten_props(v, key + "."))
        elif v.get("type") == "array" and isinstance(v.get("items"), dict) and v["items"].get("type") == "object":
            out.update(_flatten_props(v["items"], key + "[]."))
        else:
            out[key] = {"type": v.get("type", ""), "enum": list(v.get("enum") or []), "description": v.get("description", "")}
    return out


def api_text(summary: dict[str, Any]) -> str:
    """Compact human-readable rendering of the tool API for the prompts."""
    lines = [f"Tool API: {summary.get('title','')} (server {summary.get('server','')})"]
    for name, op in summary["operations"].items():
        lines.append(f"- {name} [{op['method']} {op['path']}]: {op['summary']}")
        for f, fs in op["fields"].items():
            enum = f" enum={fs['enum']}" if fs["enum"] else ""
            fmt = f" format={fs['format']}" if fs["format"] else ""
            req = "required" if fs["required"] else "optional"
            desc = f" — {fs['description']}" if fs["description"] else ""
            lines.append(f"    body.{f}: {fs['type']}{fmt}{enum} ({req}){desc}")
        for code, r in op["responses"].items():
            props = ", ".join(f"{k}{'='+str(v['enum']) if v['enum'] else ''}" for k, v in r["properties"].items())
            lines.append(f"    response {code}: {r['description']}" + (f" fields: {props}" if props else ""))
    return "\n".join(lines)
