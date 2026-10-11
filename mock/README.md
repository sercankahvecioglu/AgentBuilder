# Mock of Freya Bank's voice services (final case), on Cloudflare Workers

`src/index.js` serves the seven services of the bank's service contract under `/voice/v1/<service>` (POST, JSON),
with exactly the answers of `test-environment/test-customers.json` (status code and body, `delaySeconds` honoured,
contract error bodies for anything not in the file), plus `GET /openapi.json` for the builder and `GET /health`.
Requests may use the contract envelope `{"data": {...}, "call": {...}}` or the flat fields.

`src/data.js` is generated: `python3 mock/build_data.py <case_folder>/test-environment/test-customers.json`.

Deploy: `wrangler login` once, then `wrangler deploy` (URL: https://freya-final-mock.sarperkahvecioglu1.workers.dev).
Keep it deployed until the results are out.
