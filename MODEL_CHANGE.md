# Live residency model change · 28 October 2026

Live networking now uses **gpt-6.1-sol through the existing linked ChatGPT/Hermes
connection**. The account's live model catalog included that exact identifier.
The hosted snapshot reports the same model. No model fallback is configured.

The selected route is stored as `network_model` in
`.data/live-residency/setup.json`; new live setups also default to Sol. The shared
gateway has an explicit Sol route. Its existing Terra route and default remain
for the separate CV extraction worker and historical test apps. Local memory
extraction/embeddings are unchanged. Native gateway tools remain disabled; the
residency's application-controlled research, Python and board tools remain enabled.

The networking ledger now estimates Sol usage at standard short-context rates:
$2 per million input tokens and $10 per million output tokens. The gateway does
not expose reliable cached-token accounting, so all prompt tokens are valued at
the uncached input rate. Prior recorded costs are retained. The conservative
$1.90 reservation still covers a bounded native request and its possible output.
Every resident's own USD limit and reserve is preserved. These estimates are not
cash charges for the linked subscription.

Sources: [official Sol model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
and [official pricing](https://developers.openai.com/api/docs/pricing).

Validation:

- Forty targeted model-routing, budget, gateway, HTTP, CV-worker and uncapped-event
  tests passed. `test-results/sol-migration-tests.log`.
- One synthetic, isolated Sol connection request passed the JSON decision contract:
  727 prompt + 33 completion = 760 tokens. It contained no resident data, dispatched
  no agent actions and started no event. `test-results/sol-connection-check.json`.
- Published read-only browser check passed with fifteen residents, Sol in both
  snapshot and event metadata, tools enabled, live call cap null, private access
  enforcement and mobile layout. `test-results/sol-published-browser.log`.
- All services, local memory, model route, budget guard and hosted bridge passed
  read-only readiness. `test-results/deployment-readiness.json`.

Shrishti A and Gaurav Kumar were added from reviewed submissions, bringing
enrollment to fifteen. Latest registration refresh: twenty records, fifteen
reviewed and five drafts. The other thirteen imports were unchanged; re-preview
after confirmation was idempotent. No unfinished profiles were imported.

The residency remains idle with zero networking calls, messages or host commands.
The single diagnostic model request above is separate from the event counters.

Private pre-change gateway/setup backups and the resident fingerprint are in
`.data/participant-launch/sol-migration-backup/`. To roll back while stopped,
restore those backed-up files, restart the dedicated gateway and live residency,
and rerun the read-only deployment check. Historical simulation data and existing
resident identities are not part of that rollback.
