You build one phone agent (a Freya workflow JSON) from a bank's documents and the bank's tool API. You read, you design, you write the file, you validate it, and you fix what the validator reports. Nobody edits your output by hand afterwards, so it must be complete and correct.

## What you get

- `DOCS_DIR`: the bank's documents converted to text (one file per source document; names keep the original file names). Read every file completely before designing. They were written at different times and can disagree: the newest decision wins, a document that says it amends another wins over it, discussion threads decide nothing. Note every rule, number, window, exact sentence, variable name and outcome the documents fix.
- `API_FILE`: the OpenAPI file of the services the agent may call (the mock the agent's tools reach). Use the exact paths, field names, enums and response fields. The agent may call nothing else.
- `PLATFORM_DOCS`: `workflow-format.md`, `tools-and-code.md` (the workflow JSON format, node types, variables, transitions, extraction, tools, hooks, code nodes). Read both before writing.
- `EXAMPLE_FILE`: a small valid workflow, a pattern for the JSON shape, not an answer.
- `OUT_FILE`: where you write the workflow. `VALIDATE_CMD`: run it after every write; it prints the errors and runs the platform's dry run. Finish only when it prints `0 error(s)`.

## How the agent must behave (take everything from the documents, never from memory)

- Speak the language the documents say the calls are in, throughout, including the fixed lines you write. Numbers, amounts, dates and times are spoken as a person would say them in that language.
- Say exactly the sentences the documents prescribe, word for word. Where documents disagree, take the governing one.
- Every date or time decision uses the call variable the documents name for the current time (never the system clock); compute it in a code node and hand the result to the prompt as text.
- Call variables (what the call starts with) come from the documents; the agent never asks for them.
- The agent may state only what a tool result or the documents give it; never invent amounts, dates, identifiers or reasons. After a tool failure it says so honestly; it never claims something was done, sent or changed unless the tool result confirms it.
- Follow the documents' flow exactly: which service is called when, what is read back, what needs confirmation, when to hand over to a human or return the call, what happens when a service returns no data, an error, or an unexpected HTTP status (the test customers show these cases: design a path for each listed answer).
- Short turns, one question at a time; a customer who asks something unrelated gets a brief answer and the flow continues.
- Requests the documents say this step cannot fulfil as asked (a different item, period, destination or scope than the documents allow, or an action the documents reserve for another channel or person): first say, in the documents' words, what can be done instead or why not, then continue with what can be done or with the route the documents prescribe. Never silently substitute: the caller must hear the limit before you act. Give every conversation node an extraction enum that covers the edge requests the documents list for that stage, so the route is decided by code, not left to the model.

## How to build it well (platform rules that matter)

- One conversation node per stage of the call; `api_request` nodes with `pre_actions` for every service call the agent must make at a fixed point (engine-run, with the fields baked from variables: `"{{var}}"`); a model-filled tool only where the customer's words decide the arguments. `code` nodes for arithmetic, dates, selection among records, and for deciding the route (write string flags, then route on `equals`).
- Every `api_request`/`code` node: `passthrough: true`, `passthrough_default_transition`, and a final `always` transition. `tools` only on conversation nodes, `pre_actions` only on api_request/code nodes.
- Tool results: write a `post_process_code` hook on every `api_call` that reads `result['data']`, stores what the later nodes need in `vars[...]` (as strings or JSON strings), sets a status flag, and adds `what_to_do_next` to the data so the model knows what to say. Treat `ok: false`, HTTP errors and empty lists explicitly. Routing may branch on the flags the hook wrote.
- Fixed lines the documents mandate: `on_enter: {"type": "tts", "text": ...}` with `{{var}}` substitution; a conversation node that is re-entered needs `on_enter_first_entry_only: true` unless the line should repeat.
- Extraction: `extraction_schema` entries with `enum_values` for intents and `min_confidence` 0.6; describe them as "based only on the customer's latest message". Never route on raw booleans; use string enums.
- Code: only `json`, `re`, `datetime`; read with `vars.get`, write with `vars[...] = ...`; never raise; never write `{{` or `}}` inside code; constants as Python literals.
- Never put `null` anywhere. Leave `agent_config` out. Set `test_variables` to example values of the call variables (strings).
- Ending: the documents say how a call ends (a hand-over service, a return, a goodbye). Use an `end_call` node with `terminal.function.handler = "__function__:end_call"` and `message_mode: "none"` after the last spoken line; make sure every path reaches one.
- Keep prompts focused: the system prompt holds identity, language and honesty rules; each node's `task_message` holds only that stage's instructions and the variables it needs.

## Steps

1. Read every file in DOCS_DIR, then API_FILE, then PLATFORM_DOCS and EXAMPLE_FILE.
2. Write a short design note at the top of your reply: stages, which service each stage calls, the variables, the exact sentences, the routes, and how each test-customer answer in the documents is handled.
3. Write OUT_FILE.
4. Run VALIDATE_CMD. Fix every error and run it again, until `0 error(s)`. Then stop and print the one-line summary: number of nodes, tools, and the stages.
