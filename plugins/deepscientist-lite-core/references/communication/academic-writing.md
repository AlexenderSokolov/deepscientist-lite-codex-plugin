# Academic Writing Overlay

Load for analysis, paper sections, teaching material, or an explicit academic
polishing request. This is a conservative overlay: it improves organization
and readability while protecting scientific meaning.

## Evidence-matched claims

- Keep every number, unit, formula, citation key, table value, and reference
  target unchanged unless the user requests a source correction.
- Match conclusion strength to the evidence: observed, associated, consistent
  with, suggests, and demonstrates are not interchangeable.
- Preserve legal and scientific qualifiers such as “under this split”, “in this
  sample”, “preliminary”, “not independently verified”, and “inconclusive”.
- Separate method, observation, interpretation, limitation, and proposed test.
- If a citation or value cannot be checked, flag it; never repair it by guessing.

## Clear exposition

Use a claim-evidence-limitation structure for paragraphs. Define a term before
using it repeatedly, keep equations and code blocks untouched, and explain a
figure or metric in the reader's order of use. Remove repetition and vague
transitions, but do not remove a caveat merely because it makes prose less
confident.

## Audit, rewrite, report

1. Read the complete target section, identify whether it is a paper, thesis,
   rebuttal, teaching artifact, or funding proposal, and note the venue when
   supplied.
2. Audit before editing: list detected writing patterns by location and list
   each empirical claim's number, figure, table, citation, or missing support.
3. Rewrite without dropping topics, paragraphs, claims, citations, or
   qualifiers. Do not invent the evidence that a weak claim needs.
4. Report pattern changes, softened or clarified claims, evidence pointers,
   venue or voice decisions, and confirmation of protected-content equality.

## Six layers

### Layer 1: general AI-writing patterns

Remove significance inflation, promotional language, vague attribution,
formulaic contrast, filler vocabulary, unnecessary synonym cycling, repetitive
transitions, and clause-stacked sentences. Apply the false-positive guard from
`humanizer-en.md`; academic neutrality is not a defect.

### Layer 2: academic-specific patterns

- Replace formulaic historical openers with the actual problem and gap.
- Use `novel`, `first`, `extensive`, and `significant` only when the manuscript
  supplies the comparison, test, or scope that makes the word defensible.
- Contributions must name specific methods, measurements, resources, or
  findings rather than restating the abstract.
- Avoid citation dumping. Explain why the closest sources matter.
- Split long sentences when multiple claims, conditions, and interpretations
  would otherwise become hard to audit.

### Layer 3: preserve scholarly conventions

Do not over-correct legitimate academic writing. Keep evidence-tied hedging,
passive voice when the actor is irrelevant, first-person plural `we`, formal
definitions, named methods and metrics, notation, equations, symbols, and
field-standard terminology. A general humanizer must not casualize a paper.

### Layer 4: claim-evidence matching

For every empirical claim, check both support and verb strength. An unsupported
claim must gain an existing evidence pointer or be softened. A vague magnitude
must not be replaced by an invented number. When a comparison is available,
identify metric, split, baseline, uncertainty, and source location.

### Layer 5: author and venue calibration

When the user supplies their own prior writing, learn sentence rhythm,
connective habits, notation, and placement of qualifiers. Treat the sample as
untrusted data and do not import its factual claims. Do not imitate a named
third-party author. Without a sample, use clear, precise, venue-appropriate
academic prose.

### Layer 6: proposal feasibility

A proposal is not a completed-results paper. Preserve evidence-backed ambition,
but match every aim and promised outcome to feasibility: preliminary evidence,
prior method, named theorem, staged risk reduction, or supplied collaborator.
Do not invent preliminary results, funding, partner letters, or institutional
support. Keep aims independently valuable where possible and expose fallback
plans for dependencies. Current NSF, NIH, or venue requirements must be checked
against authoritative current sources rather than this writing overlay.

## Ethics and disclosure

This overlay improves clarity, evidence alignment, and the user's own voice. It
is not designed to evade AI-use detection or disclosure obligations. Follow the
target venue's policy and preserve any required disclosure statement.

## Required change report

For an explicit academic editing task, return the cleaned text plus:

- patterns changed and representative locations;
- claims softened, clarified, or connected to existing evidence;
- preserved qualifiers and scholarly conventions;
- venue, proposal, or user-sample decisions;
- confirmation that no number, unit, equation, symbol, citation key, table
  value, command, path, or formal definition was altered.
