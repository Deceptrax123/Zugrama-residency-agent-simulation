# Hosted access proposal · 28 October 2026

**Status:** explicitly approved by the organiser and deployed as Site version 6.
The seven-agent real event remains stopped. See [HOSTED_ACCESS.md](HOSTED_ACCESS.md)
for the implemented access flow and validation. The original proposal and initial
approval-review history are retained below for context.

## Completed enrollment

Seven reviewed registrations have been imported into the separate live residency:
Moses Sam Paul, Disha, Srinitish, Dhruv, Rajat Kumar Luthra, Louisa and Kishore
Ramesh Kumar. Three unfinished drafts were left untouched. Participant allowances,
identity documents and memory preferences were retained. The live event is idle
with zero model calls, zero completed calls and zero conversation messages.

The current host UI runs on the GCP instance at http://127.0.0.1:7380 and requires
SSH port forwarding from a laptop. Its generated organiser account is stored in
the private file `.data/participant-launch/host-account.json` (mode 0600).

## Proposed hosted behavior, not implemented or deployed

- A simulation host page on the existing Zugrama Site, with a separate secret
  access link. It shows the cohort, event status, graphs and host transcript.
  Explicit host actions control Start, Stop and day transitions. Merely opening
  the page, enrolling residents or connecting the host never starts an event.
- A resident page on the same Site. It uses the existing private onboarding
  return-link credential, without requiring ChatGPT sign-in. A resident can see
  their own identity, joined-period conversations, notes, reflections, allowance
  and request status. Other residents' private records are excluded server-side.
- A resident request form can ask the owning agent to explore a requirement,
  optionally with another enrolled resident. It queues a private human request;
  the agent can defer or decline it. It never starts a stopped event.

## Production changes requiring approval

This requires new protected web APIs and database tables for scoped snapshots
and queued commands. A host process makes outbound authenticated connections to
the Site to publish bounded views and receive commands; no GCP port is exposed.
Publishing these views would store mirrored private agent information in the
hosted Site database in addition to the existing local simulation records.

Host control and bridge credentials are separate from resident return-link keys.
Resident ownership is derived from the authenticated private key, never a caller-
supplied resident ID. Commands use unique IDs, bounded payloads and durable local
receipts. An uncertain delivery/execution is reported without automatic replay.

Checks before publication will cover resident isolation, invalid credentials,
attempted peer-agent control, host-only event controls, command deduplication,
offline status, restart/uncertain delivery and an idle production smoke test.
Tests that press Start use isolated synthetic fixtures. The real event remains
stopped throughout deployment and verification.

An automatic approval review rejected the initial implementation patch because
it introduced persistent public-facing command APIs and a bridge capable of
publishing profiles and executing event controls. No part of that patch was
applied. Enrollment and existing local host access are unaffected.
