"""Run one simulated customer against a saved agent (the organisers' way) and print the transcript.

    python3 dev/sim_drive.py <agent_id> '<json variables>' "<persona prompt>" [name]
"""
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import freya  # noqa: E402


def main():
    agent_id, variables, prompt = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
    name = sys.argv[4] if len(sys.argv) > 4 else "dev sim " + time.strftime("%H:%M:%S")
    persona = freya.create_personas([{"name": name, "prompt": prompt, "successCriteria": "All of these are true:\n- the assistant answered in Turkish", "tags": ["dev"]}])["personas"][0]
    pid = persona["id"]
    t0 = time.time()
    sim_id, it_id, status = freya.run_simulation(agent_id, name, {pid: variables})
    print(f"simulation {sim_id} {status} after {time.time() - t0:.0f}s")
    runs = freya.get_iteration(sim_id, it_id)["runs"]
    for r in runs:
        print("judge:", r.get("outcome"), (r.get("reason") or "")[:300])
        c = freya.get_call(r["callId"])
        print("ended:", c.get("endedReason"))
        for m in c.get("messages", []):
            if m.get("role") in ("user", "assistant"):
                print(f"  {round(m.get('secondsFromStart') or 0):>4}s {m['role'][:4]} {(m.get('nodeId') or '')[:16]:16} {(m.get('message') or '')[:220]}")
            elif "function_call_start" in (m.get("message") or "") and "code_exec" not in m["message"]:
                j = json.loads(m["message"]); a = j.get("args") or {}
                print(f"  {round(m.get('secondsFromStart') or 0):>4}s TOOL {j.get('function')} {json.dumps(a.get('body'), ensure_ascii=False)[:160]}")
            elif "function_call_error" in (m.get("message") or ""):
                print(f"  {round(m.get('secondsFromStart') or 0):>4}s TOOL-ERROR {(m.get('message') or '')[:200]}")


if __name__ == "__main__":
    main()
