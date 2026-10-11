// Everything that comes from the case's service contract and test customers lives here.
// PLACEHOLDER: the practice kit's seven tools and two practice customers, so the engine can be tested before the
// final zip arrives. Replace with the final case's contract (names, fields, enums, messages, customers).

export const BANK = {
  title: "Freya Bank collections tools (team mock)",
  base_path: "/v1",
  // what verify_identity compares against, per field: "date" (YYYY-MM-DD, swapped-day/month hint) or "text" (exact, trimmed)
  identity_fields: { date_of_birth: "date", phone_last4: "text" },
  max_wrong_answers: 3,
  swapped_hint: "day_month_swapped",
  not_verified_error: "identity not verified",
  closed_error: "call already closed",
};

// kind: the engine behaviour behind the tool (verify_identity | get_account | create_promise | add_note |
// schedule_callback | transfer_to_agent | close_call). name/path/fields/enums come from the contract.
export const TOOLS = [
  { name: "verify_identity", kind: "verify_identity", summary: "Check one security answer.",
    fields: { customer_id: { type: "string", required: true }, field: { type: "string", enum: ["date_of_birth", "phone_last4"], required: true },
              answer: { type: "string", required: true, description: "date_of_birth as YYYY-MM-DD" } },
    response: { ok: "boolean", error: "string", verified: "boolean", wrong_answers_left: "integer", all_verified: "boolean", hint: ["day_month_swapped"] } },
  { name: "get_account", kind: "get_account", summary: "The customer's late products.",
    fields: { customer_id: { type: "string", required: true } },
    response: { ok: "boolean", error: "string", products: "array" } },
  { name: "create_promise", kind: "create_promise", summary: "Record a promise to pay.",
    fields: { customer_id: { type: "string", required: true }, product_id: { type: "string", required: true },
              amount: { type: "number", required: true }, date: { type: "string", format: "date", required: true } },
    response: { ok: "boolean", error: "string", promise_id: "string" } },
  { name: "add_note", kind: "add_note", summary: "Note a product without a promise.",
    fields: { customer_id: { type: "string", required: true }, product_id: { type: "string", required: true },
              reason: { type: "string", enum: ["refused", "hardship", "dispute", "paid", "service_error"], required: true }, text: { type: "string" } },
    response: { ok: "boolean", error: "string" } },
  { name: "schedule_callback", kind: "schedule_callback", summary: "Schedule a callback.",
    fields: { customer_id: { type: "string", required: true }, date: { type: "string", format: "date", required: true }, time: { type: "string", required: true, description: "HH:MM" } },
    response: { ok: "boolean", error: "string" } },
  { name: "transfer_to_agent", kind: "transfer_to_agent", summary: "Transfer the call to a human queue.",
    fields: { customer_id: { type: "string", required: true }, queue: { type: "string", enum: ["restructuring", "general", "support"], required: true } },
    response: { ok: "boolean", error: "string" } },
  { name: "close_call", kind: "close_call", summary: "Close the call with an outcome. Must be the last call.",
    fields: { customer_id: { type: "string", required: true },
              outcome: { type: "string", enum: ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"], required: true },
              reason: { type: "string", description: "required except for promise and paid" } },
    response: { ok: "boolean", error: "string" } },
];

// Product list field name in get_account's response and the product fields the agent sees.
export const PRODUCTS_FIELD = "products";

// Test customers: one entry per case id. `variables` are the call variables; `identity` holds the right answers;
// `faults` makes a tool fail its first n calls (as the practice bank does).
export const CUSTOMERS = {
  "PUB-01": { variables: { first_name: "Daniel", last_name: "Reyes", title: "Mr", now: "2026-10-14T11:00" },
              identity: { date_of_birth: "1988-03-14", phone_last4: "4471" },
              products: [{ product_id: "p1", type: "credit_card", card_last4: "4821", past_due: 420.0, days_late: 6, minimum_payment: 126.0 }] },
  "PUB-10": { variables: { first_name: "Grace", last_name: "Lin", title: "Ms", now: "2026-10-14T11:00" },
              identity: { date_of_birth: "1989-02-23", phone_last4: "9904" },
              products: [{ product_id: "p1", type: "credit_card", card_last4: "7740", past_due: 365.0, days_late: 8, minimum_payment: 109.5 }],
              faults: { create_promise: { fail_first_n: 1 } } },
};
