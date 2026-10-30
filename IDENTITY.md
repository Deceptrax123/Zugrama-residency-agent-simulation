# Identity memory: design notes

The shared setting lives in `USER.md`. Identity memory belongs to an individual.
This document records the identity layers and moral-compass design. They are now
implemented as human-authored agent forms in the separate [identity test](IDENTITY_TEST.md),
with optional GPT CV extraction, multiple-choice moral questions, personal
offers/needs and separate skills/village exchange fields. The main
app's ordinary resident profile remains unchanged. No validated questionnaire or
automatic psychological scoring is administered.

## Identity layers

1. **Name:** the person's preferred name and how they want to be addressed.
2. **Given identity:** nationality and region, supplied in the person's own terms.
   Multiple affiliations and an unspecified answer are valid.
3. **Skill identity:** their CV, experience, skills, and supporting evidence.
4. **Contribution and reciprocity:** what they can offer in their domain to the
   village or its people, and what they want in return. These can include learning,
   friendship, knowledge, collaboration, income, or other self-described interests.
   An offer records willingness as stated, rather than an automatic commitment.
5. **Moral compass:** how the person describes their values, moral concerns,
   political views if they wish to include them, and the choices or trade-offs
   that matter to them.

These layers provide starting context for open-ended networking. They do not
require someone to take a village problem as their goal or to turn every
conversation into an exchange.

When people choose to co-work, their skills, interests, values, and offers may help
them find ways to contribute. They can write code, develop pseudocode, co-author
drafts, and work through problems in any domain. Their willingness to join that
particular activity comes from what they say, rather than being assumed from their
CV or moral compass. Work produced in a collaboration is distinct from a new
identity claim or an unverified qualification.

## Moral compass

Use the person's own words first. Record what matters to them, what they consider
unacceptable, where they see a difficult trade-off, and what they remain unsure
about. Their moral compass may be nuanced, context-dependent, or changing.

For optional structure, use the six domains in the Moral Foundations
Questionnaire–2 (MFQ-2):

| Domain | What a person could describe |
| --- | --- |
| Care | Their concerns about suffering, protection, and helping others. |
| Equality | How they think about equal treatment and distribution. |
| Proportionality | How contribution, effort, or merit should relate to rewards. |
| Loyalty | What commitments to people, groups, or communities mean to them. |
| Authority | How they regard legitimate leadership, roles, and obligations. |
| Purity / sanctity | What they regard as sacred, degrading, or worth preserving. |

MFQ-2 is a researched self-report instrument. Its development distinguishes
equality from proportionality, and independent replication reports support for
the six-domain structure, with qualifications such as a distinction between
loyalty to a group and loyalty to a nation.
[Development study: Atari et al., 2023](https://pubmed.ncbi.nlm.nih.gov/37589704/);
[validation and replication: Zakharin and Bates, 2023](https://www.research.ed.ac.uk/en/publications/moral-foundations-theory-validation-and-replication-of-the-mfq-2/).

The multiple-choice questions here are our adaptation for identity memory. They are not
the validated questionnaire, do not yield validated scores, and do not establish
a person's moral character. If formal measurement is added later, retain the
instrument, version, language, administration, and scoring provenance, and check
its suitability for the participants. Do not invent psychometric scores from
a CV, biography, or conversation.

People can describe values beyond these six domains, including autonomy,
honesty, curiosity, environmental responsibility, or whatever they consider
important. Such additions are personal descriptions, not extra MFQ-2 scales.
No preferred moral profile is assigned by the village.

### Multiple-choice questions

Each domain has one scenario question and several descriptive choices. A blank
answer means “Prefer not to answer / unspecified”; uncertainty and context-dependent
responses are included. The answers have no numeric rank, aggregate score, or
mapping to inferred political views. Existing free-text answers are preserved as
a “Previously supplied answer” choice when editing an older identity.

| Domain | Question focus |
| --- | --- |
| Care | How to decide when a beneficial project may harm some people. |
| Equality | How to allocate scarce resources: equal shares, needs, a minimum, or collective agreement. |
| Proportionality | How effort, results, needs, and capacity relate to rewards. |
| Loyalty | How to respond when one's group supports a decision one considers wrong. |
| Authority | When to follow or challenge leaders and rules. |
| Purity / sanctity | What deserves protection and how to handle conflicting commitments. |

The form also offers a multiple-choice guiding moral approach and an optional
self-selected political outlook, including mixed/unrepresented and unspecified
answers. Neither is inferred from answers to the six domains. These short choices
support persona authoring; they do not replace the full validated MFQ-2 instrument.

## CV extraction and identity export

In **Agent setup**, choose a PDF with **Upload CV PDF**. The app reads it and
automatically requests suggestions focused on skills the person could offer,
subject expertise and specific products/projects built. Routine employment
history, job lists and unrelated experience are omitted from the proposed identity.
The raw CV remains transient source text in the browser and is not copied into
the identity document. **Relevant project context** contains only the concise
context proposed by the model or written by the person.

Enter a public **Portfolio or project website**, then press **Extract from
website**. The app reads that page's static HTML/plain text and combines it with
the uploaded CV, when available. It does not crawl the entire website or execute
JavaScript. Product names, purposes, the person's contribution and available
source links are highlighted in **Products and projects built**; expertise has
its own field. Skills they could offer are proposed for human confirmation and
do not constitute commitments. No keyword or occupation taxonomy gates the draft.
One request goes through Hermes to the configured **GPT-5.6
Terra** model, with no automatic retry or model fallback. This sends the CV to
the external GPT provider. Qwen is not used for CV extraction. Each request uses
a fresh session containing only the supplied CV/page and extraction instructions, not
other agents, saved moral answers, or conversational memories. Local conversational
memory extraction and bedtime reflections retain their existing separate setup.

PDF reading uses app-local `pypdf==6.21.2` in an isolated subprocess with a
20-second wall-clock limit, 10-second CPU limit and 512 MiB address-space limit.
Uploads are limited to 3 MiB, 20 pages and 16,000 extracted characters. Larger,
unreadable, password-protected or image-only PDFs are rejected before a GPT call.
Scans require OCR first. Binary PDF bytes are read in memory and not retained;
only extracted text goes to GPT as source material; curated highlights enter the draft. Nothing is saved until the
host saves the identity. The parser does not silently truncate long CVs.

GPT interprets the CV across any profession or domain. Structured suggestions
are convenient for the form, but missing excerpts, extra metadata, broader
categories and narrative responses do not reject the draft. Unknown categories
and free-form interpretations remain editable under **Other relevant project context**.
There is no exact-quote check, fixed skills vocabulary, per-entry 300-character
limit, or twelve-suggestion gate. Optional model excerpts are unverified context,
not proof or qualifications. Human review decides what belongs in the identity.

Suggestions usually map to pillar 3 (`skills`, `subject_expertise`, `products_built`,
`source_website`, `interests`, concise `cv` context and `cv_notes`) and pillar
4 (explicit personal offers/wants, skills offered/needed, village offers/needs,
and reciprocity). Experience alone does not establish willingness to volunteer;
the model is guided to distinguish ability from willingness. Extraction does not set name, given
identity, moral compass, political outlook, or public introduction.

**Add suggestion … to draft** appends to that field while preserving existing
text. **Review IDENTITY.md** includes the current form and CV suggestions in an
editable document. Nothing is saved until **Submit agent**. Optional model notes
and excerpts are retained under the legacy `cv_evidence` key. Removing a claim
from the identity drops its associated model note; wording differences between
an excerpt and the source CV do not block extraction or submission. These are
human-reviewed model interpretations, not externally verified qualifications.
Model context is retained in the host's identity record and
excluded from peers' public profiles.

After saving, **Download saved IDENTITY.md** exports that agent's current saved
reviewed identity in the five pillars above, with public introduction and
disclosure preference. CV evidence is kept separately in the private identity record.
This is a private host download and includes any supplied moral and political
answers. Unsaved edits are excluded. The app continues to store the authoritative
identity and revision history locally in SQLite.

### Review before onboarding

The form's primary action is **Review IDENTITY.md**, which creates no agent,
public introduction, identity revision, or event. It makes no model request.
The review screen shows an editable Markdown document with the five pillars,
public introduction and disclosure choice. Values sit inside fenced text blocks;
the user can change any value while retaining headings and fences. Adaptive fence
lengths preserve CV text that itself contains Markdown or code.

**Back to form** applies the edited values to the draft form, preserving changes.
**Submit agent** validates the edited document and saves those values as the
agent's identity. The canonical reviewed document is stored with the identity
and revision, and is the document returned by **Download saved IDENTITY.md**.
Removed or changed claims lose stale model evidence; human corrections remain
valid authored identity. Malformed documents and missing required name/introduction
are rejected before creating an agent. Disclosure accepts `yes` or `no`.

Drafts stay in the current browser session, separately per agent slot, and survive
switching slots/pages. Closing or reloading the page discards unsubmitted drafts.
Saved agents remain available after signing in again. This workflow lives in the
isolated three-agent test app; the host controls the authored personas.

## Political standing

Political identity is an optional, explicit self-description. A person may provide:

- the label or language they use for their political outlook;
- the country, region, or political context in which that description applies;
- views on particular issues that they want represented;
- qualifications, disagreements with their usual label, or unsettled questions;
- what they are comfortable disclosing to other participants.

Keep political standing separate from moral-foundation descriptions. A value
profile is not a determination of someone's party, ideology, religion, or views
on a particular issue. Do not infer these from nationality, region, name, CV, or
silence. Broad political labels can mean different things in different places.

## Memory and disclosure

Only store an identity claim with its source: a member's supplied profile, CV,
explicit self-description, or an explicitly authored fictional persona. Keep
self-reports and external verification distinguishable. Missing information stays
unspecified; withheld information stays withheld.

Moral and political details begin as private identity context. A person chooses
what to share; they are not automatically published in the residency directory,
sent to peers, or used to restrict whom they can meet.

Record the wording and date of a member-confirmed update when their views change.
One remark, disagreement, or hypothetical example should not silently overwrite
their identity. Moral and political differences can inform conversation without
becoming a moral-quality score or a requirement to agree.

The custom test stores identities and human revisions locally, preserves an
identity snapshot at event start, and offers evidence-linked host observations
of alignment, tension, explicit reconsideration, and uncertainty. Conversation
does not overwrite the starting identity. Optional shared values enter public
agent context only with explicit disclosure; each agent's own full identity is
sent to its model when the host starts the event. See `IDENTITY_TEST.md` for scope.
