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


TEXT_SUFFIXES = (".md", ".txt", ".eml", ".csv", ".tsv", ".html", ".htm", ".json", ".yaml", ".yml", ".rst")
DOC_SUFFIXES = (".docx", ".pdf", ".xlsx", ".xlsm")
SKIP_NAMES = (".ds_store", "thumbs.db")


def expand_inputs(paths: list[str]) -> list[str]:
    """Directories become their readable files (sorted, recursive); unreadable types (images, archives) are left out."""
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if not d.startswith((".", "__")))
                for fn in sorted(files):
                    if fn.lower().startswith(".") or fn.lower() in SKIP_NAMES:
                        continue
                    if fn.lower().endswith(TEXT_SUFFIXES + DOC_SUFFIXES):
                        out.append(os.path.join(root, fn))
        else:
            out.append(p)
    return out


def read_document(path: str) -> str:
    """Text of one input file: Word, PDF and Excel are converted; everything else is read as text."""
    low = path.lower()
    if low.endswith(".docx"):
        import docx  # python-docx

        d = docx.Document(path)
        lines = [para.text for para in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                lines.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(x for x in lines if x is not None)
    if low.endswith(".pdf"):
        from pypdf import PdfReader

        r = PdfReader(path)
        return "\n\n".join((pg.extract_text() or "") for pg in r.pages)
    if low.endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        lines = []
        for ws in wb.worksheets:
            lines.append(f"## sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if any(c.strip() for c in cells):
                    lines.append(" | ".join(cells))
        return "\n".join(lines)
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def load_text_inputs(paths: list[str]) -> str:
    parts = []
    for p in expand_inputs(paths):
        try:
            body = read_document(p)
        except Exception as e:  # noqa: BLE001 - one unreadable file must not stop the build
            body = f"[could not read this file: {type(e).__name__}: {e}]"
        parts.append(f"<document name=\"{os.path.basename(p)}\">\n{body.strip()}\n</document>")
    return "\n\n".join(parts)


def fetch_api(mock_url: str, dest: str) -> str:
    """The tool API served by the mock itself at <mock_url>/openapi.json (the final: `build.py <case_folder> <mock_url>`).
    Saved to `dest`; the server URL is set to the mock when the file gives none."""
    import time
    import urllib.request

    base = mock_url.rstrip("/")
    last = None
    for wait in (0, 10, 20, 30):
        if wait:
            time.sleep(wait)
        try:
            req = urllib.request.Request(base + "/openapi.json", headers={"User-Agent": "Mozilla/5.0 (build-the-builder)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                api = json.load(r)
            break
        except Exception as e:  # noqa: BLE001
            last = e
    else:
        raise RuntimeError(f"could not fetch {base}/openapi.json: {last}")
    if not (api.get("servers") or [{}])[0].get("url"):
        api["servers"] = [{"url": base + ("/v1" if not base.endswith("/v1") else "")}]
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(api, f, indent=1, ensure_ascii=False)
    return dest


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
