// Team mock of Freya Bank's voice services for the final case (Cloudflare Worker, stateless).
// Same paths, field names and shapes as the bank's service contract; for the test customers it returns exactly the
// answers in test-customers.json (status code and body), per the lookup rules in test-customers.md.
//   POST /voice/v1/<service>     the seven services (JSON in, JSON out)
//   GET  /openapi.json           the tool API the builder reads
//   GET  /health
import { DATA } from "./data.js";

const BASE = "/voice/v1";
const SERVICES = ["cards.list", "cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change", "contact.email.get", "statement.pdf.send"];
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "*" };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...CORS } });
}

let guidCounter = 0;
function guid() {
  guidCounter = (guidCounter + 1) % 65536;
  return "f0e1d2c3b4a5968778695a4b3c2d" + guidCounter.toString(16).padStart(4, "0");
}

// Error bodies exactly as in section 4 of the contract.
function errorBody(code, message, type, rootCause) {
  const g = guid();
  return { result: { guid: g, returnCode: code, messageText: message, code, message, type, details: { guid: g, rootCause, errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } };
}
const ERR = {
  invalid: (field) => json(errorBody("INVALID_ARGUMENTS_ERROR", `${field} cannot be empty`, "ERROR", "InvalidArgumentsException"), 400),
  noCards: () => json(errorBody("FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı.", "WARNING", "NotFoundException"), 404),
  balanceNotFound: () => json(errorBody("FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı", "WARNING", "NotFoundException"), 404),
  weekNotFound: () => json(errorBody("FB_IVR_CHANNEL_121", "Ekstre haftası servisi hatası: kart bulunamadı", "WARNING", "NotFoundException"), 404),
  pdfNotFound: () => json(errorBody("FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı", "WARNING", "com.freyabank.ivrgateway.ivrchannel.rest.exception.NotFoundException"), 404),
  technical: () => json(errorBody("FBE00099", "Teknik hata: ABORTED: ", "ERROR", "TechnicalError"), 500),
};

function isTemplate(v) { return typeof v === "string" && (v.startsWith("{{") || v.startsWith("%7B%7B")); }
const norm = (v) => (v === undefined || v === null ? "" : String(v).trim());

// The request may come as the contract envelope {data:{...}, call:{...}} or as the flat fields (what a phone-platform
// tool with leaf parameters sends); both are read the same way.
function fields(body) {
  if (body && typeof body === "object" && body.data && typeof body.data === "object") return body.data;
  return body || {};
}

function customerByNo(no) {
  const key = norm(no);
  return DATA.customers.find((c) => norm(c.customerNo) === key) || null;
}
function entriesByCard(service, cardNumber) {
  const key = norm(cardNumber);
  for (const c of DATA.customers) {
    const s = (c.services || {})[service];
    if (s && typeof s === "object" && Object.prototype.hasOwnProperty.call(s, key)) return s[key];
  }
  return null;
}

async function answer(entry) {
  if (!entry || typeof entry.http !== "number") return null;
  if (entry.delaySeconds) await new Promise((r) => setTimeout(r, Math.min(Number(entry.delaySeconds) || 0, 25) * 1000));
  return json(entry.response, entry.http);
}

async function serve(service, body) {
  const f = fields(body);
  const firstCustomer = DATA.customers[0];
  switch (service) {
    case "cards.list": {
      if (isTemplate(f.customerNo)) return await answer(firstCustomer.services["cards.list"]);
      if (!norm(f.customerNo)) return ERR.invalid("customerNo");
      const c = customerByNo(f.customerNo);
      const r = c && (await answer(c.services["cards.list"]));
      return r || ERR.noCards();
    }
    case "cards.balance": {
      if (isTemplate(f.cardNumber)) return await answer(Object.values(firstCustomer.services["cards.balance"])[0]);
      if (!norm(f.cardNumber)) return ERR.invalid("card number");
      const r = await answer(entriesByCard("cards.balance", f.cardNumber));
      return r || ERR.balanceNotFound();
    }
    case "statement.week.get": {
      if (isTemplate(f.cardNumber)) return await answer(Object.values(firstCustomer.services["statement.week.get"])[0]);
      if (!norm(f.cardNumber)) return ERR.invalid("card number");
      const r = await answer(entriesByCard("statement.week.get", f.cardNumber));
      return r || ERR.weekNotFound();
    }
    case "statement.week.decide":
    case "statement.week.change": {
      if (!norm(f.cardNumber) || isTemplate(f.cardNumber)) return isTemplate(f.cardNumber) ? ERR.invalid("newStatementWeek") : ERR.invalid("card number");
      if (!norm(f.newStatementWeek)) return ERR.invalid("newStatementWeek");
      if (!norm(f.statementDay) && f.statementDay !== 0) return ERR.invalid("statementDay");
      const byWeek = entriesByCard(service, f.cardNumber);
      const r = byWeek && (await answer(byWeek[norm(f.newStatementWeek)]));
      return r || ERR.invalid("newStatementWeek");
    }
    case "contact.email.get": {
      if (isTemplate(f.customerNo)) return await answer(firstCustomer.services["contact.email.get"]);
      if (!norm(f.customerNo)) return ERR.invalid("customerNo");
      if (!norm(f.intAddressInfoType)) return ERR.invalid("intAddressInfoType");
      const c = customerByNo(f.customerNo);
      const r = c && (await answer(c.services["contact.email.get"]));
      return r || ERR.invalid("customerNo");
    }
    case "statement.pdf.send": {
      if (isTemplate(f.customerNo)) return await answer(firstCustomer.services["statement.pdf.send"]);
      for (const k of ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"]) {
        if (!norm(f[k])) return ERR.invalid(k);
      }
      const c = customerByNo(f.customerNo);
      const r = c && (await answer(c.services["statement.pdf.send"]));
      return r || ERR.pdfNotFound();
    }
    default:
      return json({ error: "unknown service" }, 404);
  }
}

// ---------------------------------------------------------------- OpenAPI for the builder
function openapi(origin) {
  const str = (d) => ({ type: "string", description: d });
  const req = (props, required) => ({ required: true, content: { "application/json": { schema: { type: "object", properties: props, required } } } });
  const envelope = "Also accepted as the contract envelope {\"data\": {...fields...}, \"call\": {\"ani\": \"...\", \"lang\": \"tr\"}}.";
  const resultProps = { guid: { type: "string" }, returnCode: { type: "string", description: "\"1\" on success; an error code otherwise" }, messageText: { type: "string" }, code: { type: "string" }, message: { type: "string" }, type: { type: "string", description: "null, \"ERROR\" or \"WARNING\"" } };
  const debtBlock = { type: "object", description: "May be absent for a currency the card does not have (not the same as NO_DEBT)", properties: {
    statementPaymentStatus: { type: "string", enum: ["HAS_DEBT", "NO_DEBT"] }, transferAmount: { type: "number" }, statementDebt: { type: "number" }, minPayment: { type: "number" },
    remainingDebt: { type: "number" }, remainingMinPayment: { type: "number" }, currentPeriodExpense: { type: "number" }, totalDebt: { type: "number", description: "can be negative (credit balance)" },
    totalDebtPaymentStatus: { type: "string", enum: ["HAS_DEBT", "NO_DEBT"] }, remainAutomaticPaymentAmount: { type: "number" } } };
  const resp = (dataProps, desc) => ({ "200": { description: desc || "Success: result.returnCode is \"1\" and data is present", content: { "application/json": { schema: { type: "object", properties: { data: { type: "object", properties: dataProps }, result: { type: "object", properties: resultProps } } } } } },
    "400": { description: "INVALID_ARGUMENTS_ERROR: a required field is missing or empty (no data object)" },
    "404": { description: "WARNING code (FB_IVR_CHANNEL_1xx): not found / nothing to do (no data object)" },
    "500": { description: "FBE00099 technical error (no data object)" } });
  const card = { type: "object", properties: { cardNumber: str("masked card number; send it back exactly as received"), cardNumberLast4: { type: "string" }, productName: str("free text, may be empty"), status: { type: "string", enum: ["A"] }, isMainCard: { type: "boolean" } } };
  const paths = {
    "/cards.list": { post: { operationId: "cards.list", summary: "The customer's eligible credit cards (active). 404 FB_IVR_CHANNEL_102 when the customer has no valid card. " + envelope,
      requestBody: req({ customerNo: str("8-digit customer number (string or number)"), aiFlow: { type: "string", default: "CardOps", description: "use case id, \"CardOps\"" } }, ["customerNo"]),
      responses: resp({ cards: { type: "array", items: card }, validCardsCount: { type: "integer" }, exitState: { type: "string", enum: ["1_CARD", "MULTI_CARD"] } }) } },
    "/cards.balance": { post: { operationId: "cards.balance", summary: "Statement dates, due dates and debt per currency of one card. 404 FB_IVR_CHANNEL_120 card not found. " + envelope,
      requestBody: req({ cardNumber: str("the cardNumber exactly as cards.list returned it") }, ["cardNumber"]),
      responses: resp({ cardNumber: { type: "string" }, cardNumberLast4: { type: "string" }, productName: { type: "string" }, statementDate: str("dd.MM.yyyy, the issued statement"), lastPayDate: str("dd.MM.yyyy, its due date"), nextStatementDate: str("dd.MM.yyyy"), nextLastPayDate: str("dd.MM.yyyy"),
        debtTL: debtBlock, debtUSD: debtBlock, debtEUR: debtBlock, debtGBP: debtBlock, statementPaymentStatus: { type: "string", enum: ["HAS_DEBT", "NO_DEBT"] }, totalDebtPaymentStatus: { type: "string", enum: ["HAS_DEBT", "NO_DEBT"] }, automaticPaymentFlag: { type: "string", enum: ["Y", "N"] } }) } },
    "/statement.week.get": { post: { operationId: "statement.week.get", summary: "The card's current statement week and day, next dates, joint-statement relation. 404 FB_IVR_CHANNEL_121 card not found. " + envelope,
      requestBody: req({ cardNumber: str("the cardNumber exactly as cards.list returned it") }, ["cardNumber"]),
      responses: resp({ cardNumber: { type: "string" }, cardNumberLast4: { type: "string" }, productName: { type: "string" }, statementWeek: { type: "integer", description: "1-4" }, statementDay: { type: "integer" }, statementDate: { type: "string" }, lastPayDate: { type: "string" }, nextStatementDate: { type: "string" }, nextLastPayDate: { type: "string" },
        relationType: { type: "string", enum: ["", "M", "C"], description: "empty = own statement; M = main card of a shared statement; C = linked card" }, relatedCardNumber: { type: "string" }, relatedCardProductName: { type: "string" } }) } },
    "/statement.week.decide": { post: { operationId: "statement.week.decide", summary: "Preview only: the statement date, due date and day the card would get with the requested week; changes nothing. Do not call it for the card's current week (error). " + envelope,
      requestBody: req({ cardNumber: str("the cardNumber exactly as cards.list returned it"), newStatementWeek: str("1-4 (number or string)"), statementDay: str("the card's current statementDay from statement.week.get") }, ["cardNumber", "newStatementWeek", "statementDay"]),
      responses: resp({ statementDate: str("dd.MM.yyyy, first statement under the requested week"), statementDueDate: str("dd.MM.yyyy, its due date"), statementDay: { type: "integer" }, responseCode: { type: "integer", description: "0 = fine" }, responseMessage: { type: "string" } }) } },
    "/statement.week.change": { post: { operationId: "statement.week.change", summary: "Changes the card's statement week (side effect; only after the caller agreed to the preview dates). Success = exitState OK and responseCode 0. " + envelope,
      requestBody: req({ cardNumber: str("the cardNumber exactly as cards.list returned it"), newStatementWeek: str("1-4"), statementDay: str("the card's current statementDay from statement.week.get") }, ["cardNumber", "newStatementWeek", "statementDay"]),
      responses: resp({ responseCode: { type: "integer" }, responseMessage: { type: "string" }, statementWeek: { type: "string" }, statementDay: { type: "string", description: "ignore; tell the caller the dates from the preview" }, exitState: { type: "string", enum: ["OK"] } }) } },
    "/contact.email.get": { post: { operationId: "contact.email.get", summary: "Registered e-mail / phone of the customer. The registered e-mail is ibanEmail (empty = none). " + envelope,
      requestBody: req({ customerNo: str("8-digit customer number"), intAddressInfoType: { type: "string", enum: ["E", "P", "B"], default: "E", description: "E e-mail, P phone, B both" } }, ["customerNo", "intAddressInfoType"]),
      responses: resp({ communicationType: { type: "string", enum: ["Both", "Phone", "Email"] }, ibanCountryCode: { type: "string" }, ibanAreaCode: { type: "string" }, ibanPhoneNum: { type: "string" }, ibanEmail: str("the registered e-mail address; empty when none"), ttsEmail: { type: "string" }, commGramType: { type: "string" }, exitState: { type: "string" } }) } },
    "/statement.pdf.send": { post: { operationId: "statement.pdf.send", summary: "Sends the statement PDF to the given address (side effect). 404 FB_IVR_CHANNEL_107 when there is no statement document. " + envelope,
      requestBody: req({ customerNo: str("8-digit customer number"), cardNumber: str("the cardNumber exactly as cards.list returned it"), currencyType: { type: "string", enum: ["TL", "USD", "EUR", "GBP"] }, statementDate: str("the statementDate from cards.balance, dd.MM.yyyy"), emailAddress: str("the registered e-mail address from contact.email.get") }, ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"]),
      responses: resp({ exitState: { type: "string", enum: ["DONE"] } }) } },
  };
  return { openapi: "3.0.3", info: { title: "Freya Bank voice services (team mock of the service contract)", version: "1.0", description: "POST, JSON. Success = HTTP 200 and result.returnCode \"1\". Error answers have no data object, only result (code, message, type ERROR/WARNING). Dates dd.MM.yyyy; amounts JSON numbers." }, servers: [{ url: origin + BASE }], paths };
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    if (request.method === "GET" && (path === "/health" || path === "")) return json({ durum: "ok", services: SERVICES.map((s) => BASE + "/" + s) });
    if (request.method === "GET" && (path === "/openapi.json" || path === BASE + "/openapi.json")) return json(openapi(url.origin));
    if (request.method === "POST" && path.startsWith(BASE + "/")) {
      const service = path.slice(BASE.length + 1);
      if (!SERVICES.includes(service)) return json({ hata: "bulunamadı", yollar: SERVICES.map((s) => "POST " + BASE + "/" + s) }, 404);
      let body = null;
      try { body = await request.json(); } catch { body = null; }
      try {
        return await serve(service, body);
      } catch (e) {
        return ERR.technical();
      }
    }
    return json({ hata: "bulunamadı", yollar: ["GET /health", "GET /openapi.json", ...SERVICES.map((s) => "POST " + BASE + "/" + s)] }, 404);
  },
};
