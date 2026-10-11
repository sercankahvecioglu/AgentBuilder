# Final-case mock of the bank's services (Cloudflare Workers)

`src/index.js` (state in a Durable Object per customer) serves the bank's tools under `/v1/<tool>` (POST, JSON), its own OpenAPI file at `/openapi.json`
(the builder reads it: `python3 builder/build.py <case_folder> https://<worker>.workers.dev`), and practice
endpoints for `tools/run_cases.py` (`POST /v1/practice/sessions`, `GET /v1/practice/ledger/<customer_id>`).

`src/contract.js` holds everything that comes from the case's service contract and test customers: tool names,
fields, enums, the test customers. Edit that file only.

Deploy: `wrangler login` once, `then
`wrangler deploy`. Keep it deployed until the results are out.
