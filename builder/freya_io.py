"""Save, publish and export workflows through the kit's freya.py, with an absolute state file (T7.1)."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import freya  # noqa: E402

STATE = ROOT / ".freya-agents.json"


def save(slot: str, wf: dict) -> dict:
    """Create on first use of the slot, update (and publish) afterwards. A first create is followed by one update so the
    agent config model is set and the version is published (DEV_GUIDE §16.3)."""
    existed = slot in (json.loads(STATE.read_text()) if STATE.exists() else {})
    r = freya.save_workflow(slot, wf, state_file=str(STATE))
    if not existed:
        r = freya.save_workflow(slot, wf, state_file=str(STATE))
    return r


def dry_run(name: str, wf: dict):
    return freya.validate_workflow(name, wf)


def export(workflow_id: str, path: str) -> str:
    return freya.export_workflow(workflow_id, path)
