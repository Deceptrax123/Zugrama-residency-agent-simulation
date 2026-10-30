# Zugrama — Agent Residency Simulation: independent onboarding

A separately hosted, account-free intake site. People enter a name and optional
nickname, save a private identity and optional PDF before the residency simulation
is deployed, and return later to revise them. No email, password or ChatGPT sign-in
is required. Dhun is environment context; topics and collaborations stay open-ended.
Saving an intake never starts an event. Uploading a CV explicitly requests GPT Terra extraction for review.

The seven steps collect name/nickname/background/interests; relevant skills, subject
expertise, products and portfolio; personal and professional offers/needs; village
exchange and public introduction; optional moral-compass MCQs; local-memory
priorities and exclusions; and the agent's USD allowance/wrap-up reserve. Applicants
review an editable IDENTITY.md before final submission. The MCQs draw on MFQ-2
domains but are original prompts, not a validated psychometric scale.

D1 stores a submission under the SHA-256 hash of a random 256-bit private draft key.
Names and nicknames do not identify records or grant access. R2 stores the draft's
optional PDF (3 MB maximum). The key is kept in the browser and sent only in a
request header. A private return link carries it in the URL fragment, which is
removed from the address bar after opening and is not sent as part of HTTP URLs.
Anyone who has the private return link can read or edit that submission; the UI
explains this. Losing both browser storage and the return link loses access.

Every API operation checks the key; writes also check Origin, JSON writes require
application/json, and bodies are bounded before buffering. There is no public
listing, name lookup, or public PDF URL. Users can delete their saved submission
and PDF; the browser then switches to a new private key. Existing account-owned
records remain preserved and their legacy authenticated API access still works,
while the current public form never starts or requires a sign-in flow. No database
migration or data deletion was required to replace sign-in.

The site owner can administer hosted data through Sites; applicants are told this.
The export contains reviewed Markdown, preferences, USD amounts and optional PDF,
not the private draft key. Downloading is optional: submissions remain in the
organiser’s Sites database for later cohort import. Participants are not asked
to manually send their files to the host. In the residency app, choose an Agent setup slot and
**Import saved onboarding file**. This fills a local draft and parses the PDF locally.
CV suggestions can now be extracted and reviewed on this site. Portfolio URLs
remain saved for optional website extraction in the residency app. No Hermes
credential or private simulation memory is embedded in this website. The memory
form includes an explicit own-notes-in-GPT choice (`network_context`), which is
saved with the preferences and disclosed at final review. Older missing values
are not silently treated as participant consent by the Site API.

## Hosted CV extraction

D1 `cv_jobs` holds private PDF extraction jobs and results, scoped to the same
submission key. A worker on the residency host polls over HTTPS with a separate
server secret, fetches one leased PDF, parses it locally and uses the existing
Hermes **gpt-5.6-terra** route with a fresh isolated session and tools disabled.
Only the CV and extraction instructions are sent to that model, with no resident
conversations or memories. The website receives only the resulting suggestions.
Credentials stay on the host. No model fallback or inference retry is performed.

The form saves typed answers before upload. Suggestions append to existing fields
and never submit an identity. Full suggestions remain visible if a field is full.
A reopened completed result is offered for explicit addition, rather than repeatedly
restoring edits the applicant removed. The user must review IDENTITY.md before
final submission. Already-saved PDFs have an extraction button; failed extraction
has an explicit retry button. Queued jobs wait while the host is offline.

The server secret `EXTRACTION_WORKER_TOKEN` must match the ignored, mode-0600
`../.data/intake-extractor/config.json`. Deploy the Site after changing its secret.
On the residency host, using the same Python environment as other app scripts:

```bash
python3 -B scripts/intake_extractor.py setup
python3 -B scripts/intake_extractor.py start
python3 -B scripts/intake_extractor.py status
python3 -B scripts/intake_extractor.py stop
```

Run these from `residency_app/`. Setup does not overwrite an existing secret. The
worker is a detached host process, not an operating-system boot service; after a
host reboot, start Hermes and this worker again. Its private SQLite journal blocks
repeated execution of a job after uncertain delivery. A ten-minute lease timeout
allows an explicit retry; limits are 10 requests per draft/day, 100 queued requests
site-wide/day and 50 model attempts/rolling day on this host. CV processing is
outside agent networking allowances. Runtime logs contain no CV or result bodies.
Deleting a submission also deletes its jobs/results and private PDF.

## Local development and checks

Use Node >=22.13 with npm. Run the Sites skill's dependency installer only if needed,
then build with its build-site helper. No dependencies changed for account-free
onboarding. Apply the migrations in `drizzle/` in order, once, to local D1, using
`dist/server/wrangler.json` and `.wrangler/state`. Migration 0001 adds the extraction
queue without changing saved submissions. For local tests set
`EXTRACTION_WORKER_TOKEN=qa-extraction-worker-only` in ignored `.dev.vars`.

```bash
npm run dev -- --hostname 127.0.0.1 --port 5175
node --test tests/submission-key.test.mjs tests/cv-extraction.test.mjs
node node_modules/typescript/bin/tsc --noEmit
```

From the parent `residency_app/` folder, run the local-only browser flow:

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/browsers" node tests/onboarding_site_browser.cjs
node tests/onboarding_extraction_api.cjs
```

It checks direct name/nickname entry with no account, private save/reload, return-link
recovery in a fresh browser, isolation between people with identical names, PDF
storage, extraction with synthetic worker responses, editable Markdown, USD/preferences export, key/Origin enforcement, deletion
and mobile layout. Exported test files and screenshots contain synthetic data and
are ignored under test-results/.
