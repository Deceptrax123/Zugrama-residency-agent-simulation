# Host-approved saved drafts · 28 October 2026

At the organiser's explicit request, all five saved draft profiles were reviewed
for readiness. This review used their entered answers and did not run a model or
infer missing biography, offers, needs, moral answers or political views.

| Profile | Decision | Entered information |
| --- | --- | --- |
| Hiro | Enrolled, slot 16 | Identity, detailed skills/projects, personal and residency offers/needs, and public introduction |
| Guru | Enrolled, slot 17 | Identity, skills/projects, personal offers/needs, residency contribution/needs, introduction and some optional moral answers |
| Keerthi / Keer | Pending | Basic identity and interests; skills/offers/needs and introduction are blank |
| Kishore / Kiho | Pending | Basic identity and interests; skills/offers/needs and introduction are blank |
| Aditya Singh / Adi | Pending | Basic identity and interests; skills/offers/needs and introduction are blank |

The cohort has **17 residents**: 15 reviewed submissions and two host-approved
drafts. There are 20 registration records. The Site still stores five as drafts,
including the two now enrolled; their form data, status and update timestamps
were not changed. This records host enrollment without claiming personal review.

The importer accepts a draft only when the authenticated host explicitly attaches
`host_review: {approved: true, note: "reason"}` to that exact source record.
Unapproved drafts remain skipped. The source timestamp and data hash are retained
in `cohort_enrollment_reviews`. IDENTITY.md is rendered directly from saved fields.
The standard preview/hash confirmation, private SQLite backup, capacity checks,
budget validation and no-Start behavior still apply. Blank optional fields stay
blank. Existing memory choices are preserved; missing own-note GPT consent in a
host-approved legacy draft defaults to false.

The outbound bridge marks only these residents' own snapshots with
`enrollment.basis = host_reviewed_draft`. A draft holder can open their own agent
only after that protected host enrollment is published. They still need their
personal browser key. Names, peer IDs, unapproved drafts and deleted profiles do
not grant access. The dashboard explains the enrollment and links back to the
editable onboarding form. Private host review notes and source hashes are not
included in resident snapshots.

Validation: 18 backend cohort/approval/bridge/model tests, 14 Site Node tests,
TypeScript checking and production build passed. The local browser test exercised
actual Sites storage and the Python bridge, an unapproved draft denied access,
host-approved draft access, peer isolation, private commands without auto-Start,
six synthetic GPT decisions, restricted Python, boards, notes and mobile layout.
The published read-only browser check verifies 17 residents and the Sol route.

Evidence: `test-results/host-draft-enrollment-tests.log`, `host-draft-browser.log`,
`host-draft-published-browser.log`, `host-draft-enrollment-preservation.json` and
`deployment-readiness.json`. Full review/import records remain private under
`.data/participant-launch/host-draft-*.json`.

Site version **11**, commit `ca8a14f8c2a02a306fbd30cd41f246d239013852`.
The live model remains **gpt-6.1-sol**. Existing identities, allowances and memory
preferences were preserved. All 251 original simulation files match their saved
baseline. The live event is **idle, with zero networking calls and messages**.
