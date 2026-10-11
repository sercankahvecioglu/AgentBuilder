"""Watchdog (dev only): a simulation whose iteration completed but whose status stays 'running' blocks the workspace
(ISS-005). Every 60 s, look at the newest simulations; if one is 'running' with a completed iteration for > 3 min,
set its status to completed through PUT (only when every run already has a judge verdict and the last call ended more than 20 min ago: forcing earlier cuts the judge off and gives 'no verdict') /api/v2/simulations/{id}.

    python dev/unstick.py            # loops until killed
"""
import datetime, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import freya


def check():
    r = freya.api("GET", "/api/v2/simulations", workspaceId=freya.workspace_id(), limit=5)
    sims = r.get("simulations") or r.get("items") or r
    for s in sims if isinstance(sims, list) else []:
        if s.get("status") != "running":
            continue
        its = freya.api("GET", f"/api/v2/simulations/{s['id']}/iterations")
        its = its.get("iterations") or its.get("items") or its
        if not its:
            continue
        it = freya.get_iteration(s["id"], its[0]["id"])
        runs = it.get("runs") or []
        # every call has ended (a verdict may still be 'inconclusive' or 'analyzing'; after 20 min it is never coming)
        if not runs or not all(r.get("endedAt") for r in runs):
            continue
        ended = max((r.get("endedAt") or "") for r in runs)
        try:
            t_end = datetime.datetime.fromisoformat(ended.replace("Z", "+00:00"))
        except Exception:
            continue
        age = (datetime.datetime.now(datetime.timezone.utc) - t_end).total_seconds()
        if age > 1200:
            freya.api("PUT", f"/api/v2/simulations/{s['id']}", {"status": "completed"})
            print(time.strftime("%H:%M:%S"), "unstuck", s["id"], f"(iteration ended {age:.0f}s ago)", flush=True)


if __name__ == "__main__":
    while True:
        try:
            check()
        except Exception as e:
            print(time.strftime("%H:%M:%S"), "watchdog error", str(e)[:200], flush=True)
        time.sleep(60)
