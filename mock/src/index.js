// Team mock of the bank's services for the final case. Generic engine; the contract lives in contract.js.
//   POST <base_path>/<tool>            the tools the phone agent calls (JSON body, JSON reply)
//   GET  /openapi.json                 the tool API the builder reads
//   POST <base_path>/practice/sessions {case} -> {variables}   a fresh customer for a test run (tools/run_cases.py)
//   GET  <base_path>/practice/ledger/<customer_id>             what was recorded
// State: one KV record per customer_id.
import { BANK, TOOLS, PRODUCTS_FIELD, CUSTOMERS } from "./contract.js";

const JSON_HEADERS = { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" };
const reply = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: JSON_HEADERS });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    const base = BANK.base_path.replace(/\/+$/, "");
    try {
      if (request.method === "OPTIONS") return new Response("", { headers: JSON_HEADERS });
      if (path === "/openapi.json" || path === base + "/openapi.json") return reply(openapi(url.origin));
      if (path === "" || path === "/") return reply({ ok: true, service: BANK.title, openapi: url.origin + "/openapi.json" });
      if (path === base + "/practice/sessions" && request.method === "POST") return await newSession(request, env);
      const m = path.match(new RegExp("^" + base + "/practice/ledger/([^/]+)$"));
      if (m && request.method === "GET") return reply(await ledgerOf(env, decodeURIComponent(m[1])));
      if (path.startsWith(base + "/") && request.method === "POST") {
        const name = path.slice(base.length + 1);
        const tool = TOOLS.find((t) => t.name === name);
        if (!tool) return reply({ ok: false, error: "unknown tool " + name }, 404);
        let body;
        try { body = await request.json(); } catch { return reply({ ok: false, error: "body must be JSON" }, 400); }
        return await callTool(env, tool, body || {});
      }
      return reply({ ok: false, error: "not found" }, 404);
    } catch (e) {
      return reply({ ok: false, error: "mock error: " + (e && e.message ? e.message : String(e)) }, 500);
    }
  },
};

// ---------------------------------------------------------------- state
async function load(env, cid) {
  const raw = await env.LEDGER.get("cust:" + cid);
  return raw ? JSON.parse(raw) : null;
}
async function save(env, st) {
  await env.LEDGER.put("cust:" + st.customer_id, JSON.stringify(st), { expirationTtl: 60 * 60 * 24 * 14 });
}
function freshState(cid, cust, caseId) {
  return {
    customer_id: cid, case: caseId || "", identity: cust.identity || {}, products: JSON.parse(JSON.stringify(cust.products || [])),
    faults: JSON.parse(JSON.stringify(cust.faults || {})), verified: {}, wrong: 0, closed: false,
    outcome: null, reason: null, promises: [], notes: [], callbacks: [], transfers: [], calls: [], created: new Date().toISOString(),
  };
}

async function newSession(request, env) {
  let body = {};
  try { body = await request.json(); } catch {}
  const caseId = body.case || Object.keys(CUSTOMERS)[0];
  const cust = CUSTOMERS[caseId];
  if (!cust) return reply({ ok: false, error: "unknown case " + caseId }, 404);
  const cid = "c_" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
  const st = freshState(cid, cust, caseId);
  await save(env, st);
  return reply({ ok: true, variables: { customer_id: cid, ...(cust.variables || {}) } });
}

async function ledgerOf(env, cid) {
  const st = await load(env, cid);
  if (!st) return { ok: false, error: "unknown customer" };
  return { ok: true, customer_id: cid, case: st.case, outcome: st.outcome, reason: st.reason, promises: st.promises, notes: st.notes,
           callbacks: st.callbacks, transfers: st.transfers, calls: st.calls, closed: st.closed };
}

// ---------------------------------------------------------------- tools
async function callTool(env, tool, body) {
  const cid = body.customer_id;
  if (!cid) return reply({ ok: false, error: "customer_id is required" }, 400);
  let st = await load(env, cid);
  if (!st) {
    // an unknown customer id (e.g. the platform's test call): a default customer so the call can proceed
    const first = Object.values(CUSTOMERS)[0];
    st = freshState(cid, first, "default");
  }
  const log = (result) => { st.calls.push({ tool: tool.name, args: body, result: result, at: new Date().toISOString() }); };
  const done = async (result, status = 200) => { log(result); await save(env, st); return reply(result, status); };

  // required fields
  for (const [f, spec] of Object.entries(tool.fields || {})) {
    if (spec.required && (body[f] === undefined || body[f] === null || body[f] === "")) return await done({ ok: false, error: `${f} is required` });
    if (spec.enum && body[f] !== undefined && body[f] !== "" && !spec.enum.includes(String(body[f]))) return await done({ ok: false, error: `${f} must be one of ${spec.enum.join(", ")}` });
  }
  if (st.closed) return await done({ ok: false, error: BANK.closed_error });

  // injected faults (fail the first n calls of a tool with a 500, like the practice bank)
  const fault = st.faults && st.faults[tool.name];
  if (fault && fault.fail_first_n > 0) {
    fault.fail_first_n -= 1;
    log({ ok: false, error: "service unavailable, nothing was recorded" });
    await save(env, st);
    return reply({ ok: false, error: "service unavailable, nothing was recorded" }, 500);
  }

  const allVerified = () => Object.keys(BANK.identity_fields).every((f) => st.verified[f]);
  switch (tool.kind) {
    case "verify_identity": {
      const field = String(body.field || ""), answer = String(body.answer || "").trim();
      const kind = BANK.identity_fields[field];
      if (!kind) return await done({ ok: false, error: "unknown field" });
      const expected = String(st.identity[field] || "").trim();
      const left = () => Math.max(0, BANK.max_wrong_answers - st.wrong);
      if (st.wrong >= BANK.max_wrong_answers) return await done({ ok: false, error: "no attempts left", verified: false, wrong_answers_left: 0, all_verified: false });
      if (kind === "date") {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(answer)) return await done({ ok: false, error: "answer must be a date YYYY-MM-DD", verified: false, wrong_answers_left: left(), all_verified: allVerified() });
        if (answer === expected) { st.verified[field] = true; return await done({ ok: true, verified: true, wrong_answers_left: left(), all_verified: allVerified() }); }
        const [y, m, d] = expected.split("-");
        if (BANK.swapped_hint && answer === `${y}-${d}-${m}`) return await done({ ok: true, verified: false, wrong_answers_left: left(), all_verified: allVerified(), hint: BANK.swapped_hint });
      } else if (answer.toLowerCase().replace(/\s+/g, "") === expected.toLowerCase().replace(/\s+/g, "")) {
        st.verified[field] = true; return await done({ ok: true, verified: true, wrong_answers_left: left(), all_verified: allVerified() });
      }
      st.wrong += 1;
      return await done({ ok: true, verified: false, wrong_answers_left: left(), all_verified: allVerified() });
    }
    case "get_account": {
      if (!allVerified()) return await done({ ok: false, error: BANK.not_verified_error });
      return await done({ ok: true, [PRODUCTS_FIELD]: st.products });
    }
    case "create_promise": {
      if (!allVerified()) return await done({ ok: false, error: BANK.not_verified_error });
      const pid = String(body.product_id || "");
      if (!st.products.some((p) => String(p.product_id) === pid)) return await done({ ok: false, error: "unknown product_id" });
      if (st.promises.some((p) => p.product_id === pid)) return await done({ ok: false, error: "this product already has a promise" });
      const amount = Number(body.amount);
      if (!(amount > 0)) return await done({ ok: false, error: "amount must be a positive number" });
      if (!/^\d{4}-\d{2}-\d{2}$/.test(String(body.date || ""))) return await done({ ok: false, error: "date must be YYYY-MM-DD" });
      const promise_id = "pr" + (st.promises.length + 1);
      const prod = st.products.find((p) => String(p.product_id) === pid);
      st.promises.push({ promise_id, product_id: pid, type: prod.type, amount, date: body.date });
      return await done({ ok: true, promise_id });
    }
    case "add_note": {
      st.notes.push({ product_id: String(body.product_id || ""), reason: String(body.reason || ""), text: String(body.text || "") });
      return await done({ ok: true });
    }
    case "schedule_callback": {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(String(body.date || ""))) return await done({ ok: false, error: "date must be YYYY-MM-DD" });
      if (!/^\d{2}:\d{2}$/.test(String(body.time || ""))) return await done({ ok: false, error: "time must be HH:MM" });
      st.callbacks.push({ date: body.date, time: body.time });
      return await done({ ok: true });
    }
    case "transfer_to_agent": {
      st.transfers.push({ queue: String(body.queue || "") });
      return await done({ ok: true });
    }
    case "close_call": {
      st.outcome = String(body.outcome || "");
      st.reason = body.reason === undefined || body.reason === null || body.reason === "" ? null : String(body.reason);
      st.closed = true;
      return await done({ ok: true });
    }
    default:
      return await done({ ok: false, error: "tool kind not implemented: " + tool.kind });
  }
}

// ---------------------------------------------------------------- OpenAPI (what the builder reads)
function openapi(origin) {
  const paths = {};
  for (const t of TOOLS) {
    const properties = {};
    const required = [];
    for (const [f, spec] of Object.entries(t.fields || {})) {
      const leaf = { type: spec.type || "string" };
      if (spec.enum) leaf.enum = spec.enum;
      if (spec.format) leaf.format = spec.format;
      if (spec.description) leaf.description = spec.description;
      properties[f] = leaf;
      if (spec.required) required.push(f);
    }
    const resp = {};
    for (const [k, v] of Object.entries(t.response || {})) {
      if (Array.isArray(v)) resp[k] = { type: "string", enum: v };
      else if (v === "array" && k === PRODUCTS_FIELD) resp[k] = { type: "array", items: { type: "object", properties: productProps() } };
      else resp[k] = { type: v };
    }
    paths["/" + t.name] = { post: { operationId: t.name, summary: t.summary || t.name,
      requestBody: { required: true, content: { "application/json": { schema: { type: "object", properties, required } } } },
      responses: { "200": { description: "Result", content: { "application/json": { schema: { type: "object", properties: resp } } } },
                   "500": { description: "The service failed; nothing was recorded. The call may be repeated." } } } };
  }
  return { openapi: "3.0.3", info: { title: BANK.title, version: "1.0" }, servers: [{ url: origin + BANK.base_path }], paths };
}

function productProps() {
  // the union of the fields the test customers' products carry
  const props = {};
  for (const c of Object.values(CUSTOMERS)) for (const p of c.products || []) for (const [k, v] of Object.entries(p)) {
    if (!props[k]) props[k] = { type: typeof v === "number" ? (Number.isInteger(v) ? "integer" : "number") : "string" };
  }
  const types = [...new Set(Object.values(CUSTOMERS).flatMap((c) => (c.products || []).map((p) => p.type)).filter(Boolean))];
  if (props.type && types.length) props.type.enum = types;
  return props;
}
