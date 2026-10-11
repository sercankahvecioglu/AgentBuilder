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
RETRY_WAITS_S = (20, 40, 60)   # the platform answers 502/504 or times out in waves; a build must not die on one of them


def _retry(fn, what: str, log=None):
    """Call fn(); on a platform error wait and try again (up to len(RETRY_WAITS_S) more times)."""
    import time

    last = None
    for i, wait in enumerate(RETRY_WAITS_S + (None,)):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 (HTTP errors, timeouts, connection resets)
            last = e
            if wait is None:
                break
            if log:
                log(f"{what} failed ({str(e)[:120]}); retry {i + 1} in {wait} s")
            time.sleep(wait)
    raise last


def save(slot: str, wf: dict, log=None) -> dict:
    """Create on first use of the slot, update (and publish) afterwards. A first create is followed by one update so the
    agent config model is set and the version is published (DEV_GUIDE §16.3). Platform errors are retried."""
    existed = slot in (json.loads(STATE.read_text()) if STATE.exists() else {})
    r = _retry(lambda: freya.save_workflow(slot, wf, state_file=str(STATE)), "save", log)
    if not existed:
        r = _retry(lambda: freya.save_workflow(slot, wf, state_file=str(STATE)), "save (publish)", log)
    return r


def dry_run(name: str, wf: dict):
    return freya.validate_workflow(name, wf)


def export(workflow_id: str, path: str, log=None) -> str:
    return _retry(lambda: freya.export_workflow(workflow_id, path), "export", log)
