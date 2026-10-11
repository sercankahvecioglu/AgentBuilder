"""Drive a saved workflow through POST /api/v2/chat/message with scripted customer lines (development check).

    python3 dev/chat_drive.py <workflow_id> '<json variables>' "line 1" "line 2" ...

Prints every assistant reply. The first reply is the model's own opening (chat never speaks the initial on_enter).
"""
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import freya  # noqa: E402


def main():
    wf, variables, lines = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3:]
    call_id = None
    for msg in lines:
        body = {"workflowId": wf, "message": msg, "customerVariables": variables}
        if call_id:
            body["callId"] = call_id
        t = time.time()
        try:
            r = freya.api("POST", "/api/v2/chat/message", body)
        except Exception as e:  # noqa: BLE001
            print(f"USER: {msg}\n  !! {str(e)[:300]}")
            break
        call_id = r.get("callId") or call_id
        print(f"USER: {msg}\nAGENT ({time.time() - t:.0f}s): {r.get('response')}\n")
    if call_id:
        try:
            freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
        except Exception:
            pass
        try:
            c = freya.get_call(call_id)
            calls = [json.loads(m["message"]) for m in c.get("messages", []) if m.get("role") == "system" and "function_call_start" in (m.get("message") or "")]
            for j in calls:
                a = j.get("args") or {}
                if j.get("function") != "code_exec":
                    print("TOOL:", j.get("function"), a.get("url", ""), json.dumps(a.get("body"), ensure_ascii=False)[:200])
        except Exception as e:  # noqa: BLE001
            print("(call events unavailable:", str(e)[:100], ")")


if __name__ == "__main__":
    main()
