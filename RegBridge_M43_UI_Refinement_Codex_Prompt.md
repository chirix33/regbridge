# Codex task: Correct the action overview and redesign the RegBridge UI

Implement this refinement in the existing local RegBridge checkout on `codex/m4-3-action-review`. The reviewed published revision is `c93b2f381e43111d206b58efe0d1e1a8d72e2029` (presentation version 1.1.0). Inspect any subsequent local changes before editing; preserve unrelated files and changes. Do not reset, clean, switch to main, merge, deploy, or push. Leave the changes available for review unless I separately instruct otherwise.

## Objective and authorization

Make the application usable by a reviewer who wants to know what was found, what needs attention, and why. Correct the duplicate-looking inspection rows and implement the visual/interaction design below. This authorizes changes to presentation, layout, styles, navigation, and product setup controls. It does not authorize changing migration decisions, scientific policies, benchmark labels, model prompts, or experimental results.

Read the current local `AGENTS.md`, `IMPLEMENTATION.md`, M4.3 documentation, and any applicable nested instructions completely. Update active documentation to reflect the specifically authorized UI changes; older presentation requirements do not require asking me again. Preserve historical milestone records. Inspect `git status` and diff before edits.

Use the installed `frontend-design`, `improve-animations`, and `better-layout` skills. Find and read their actual instructions; do not merely mention their names. If a named skill is unavailable, report that fact and use the available tools and this specification. Do not claim to have used unavailable skills or silently install unrelated dependencies.

`curve-array.svg` and `curve-array.png` are the SVG and PNG files for the new logo of RegBridge respectively. Use them as the logo. Let me know if I have to convert any of these files to an ICO to get the Favicon version of this web app and make it the favicon for the frontend.

Start with a concise diagnosis and implementation plan, then implement through verification. Ask only if an unresolved issue would require changing scientific policy, expanding scope, or contradicting these instructions.

## References and inspection boundary

Use the three attached images as design references:

1. `Microsoft Edge Appshot 2026-09-17T02-46-39.923Z.jpg`: current results show five review items for three leaves, including repeated “Content inspection is incomplete; no content concern is inferred from this limitation.”
2. `1.jpeg`: upload and sample as side-by-side alternatives, followed by a selected-file summary and Continue button.
3. `2.jpeg`: an area modal with supporting evidence and graph/typed-neighborhood explanations; a separate All documents inventory.

The review session inspected the newly pushed revision `c93b2f381e43111d206b58efe0d1e1a8d72e2029`. The duplicate-item construction is now verified from source, as detailed below; the reviewer did not run the application or inspect the original live response payload. Verify the behavior locally against actual records before changing it. If images are not attached in this Codex session, implement from the detailed requirements below and explicitly report the missing visual references.

Likely starting points, subject to local changes:

- `frontend/src/api/presentation.ts`, `wording.ts`, and target setup helpers.
- `frontend/src/components/ReviewWorkspace.tsx`, `ProductSetup.tsx`, `WorkspaceFlow.tsx`, `ProductNav.tsx`, and graph components.
- `frontend/src/pages/DossierWorkspace.tsx`, `BaselinesWorkspace.tsx`, and `ScopePage.tsx`.
- The actual global styles, design tokens, product contracts, and presentation tests.

## 1. Diagnose and correct the duplicate inspection rows

### Verified source diagnosis at c93b2f3

In `frontend/src/api/presentation.ts`, `documentReviewItems()` first adds placement observations, manufacturer observations, and remaining findings. It then unconditionally calls `add("inspection", "Document inspection", ...)` whenever the document statuses include `Incomplete inspection` or `Inspection intentionally omitted`. There is no check for an already-present substantive item that should carry this qualification. The manufacturer item already includes an incomplete-inspection sentence before the extra inspection item is created.

The helper `add()` also assigns `statuses: d.statuses` to every item. Consequently, a generic inspection item inherits unrelated document-level badges such as Proposed change or Advisory. `groupReviewItems()` iterates over all generated items and includes the complete document context in its equivalence signature. The two similar inspection rows therefore remain separate for the two different leaves. This is projection-driven extra-item creation, not evidence that the model generated duplicate findings or that React rendered a single item twice.

For three substantive items with incomplete inspection on the placement and manufacturer documents, this path produces exactly the five-row structure in the screenshot. Fix the projection and item-specific qualification model; do not weaken grouping to merge the two different document contexts.

Additional verified issues:

- The inspection branch uses “Complete document inspection before deciding reuse” even for B2's intentional omission. Present B2's methodological limitation truthfully without depicting its expected omission as a malfunction or requesting a change to the baseline algorithm. Any broader next check must remain distinguished from B2's recorded recommendation.
- `DocumentReview` renders the generated review-item list plus a separate incomplete-inspection paragraph and other uncertainty/findings sections. Consolidate repeated caveats while retaining all distinct information.
- `WorkspaceFlow` still explicitly calls `scrollIntoView` with `behavior: "instant"`.
- `ReviewWorkspace` already implements a separate All documents inventory at this revision. Refine and reuse it rather than rebuild it as though it were missing. It currently uses inline detail expansion, not the requested modal.

Source references:

- https://github.com/chirix33/regbridge/blob/c93b2f381e43111d206b58efe0d1e1a8d72e2029/frontend/src/api/presentation.ts
- https://github.com/chirix33/regbridge/blob/c93b2f381e43111d206b58efe0d1e1a8d72e2029/frontend/src/components/ReviewWorkspace.tsx
- https://github.com/chirix33/regbridge/blob/c93b2f381e43111d206b58efe0d1e1a8d72e2029/frontend/src/components/WorkspaceFlow.tsx

### Required correction

Trace actual recorded results through projection/grouping to rendered rows. Identify whether duplicates originate in the API, multiple findings/limitations, projection logic, grouping, or repeated component rendering. Report which source records and keys produce the extra rows. Also check whether unrelated document-wide statuses are copied onto individual limitation rows.

For the controlled three-document sample, the overview should communicate the three substantive areas when supported by the records:

- Document placement.
- Manufacturer metadata.
- Applicant information/content review.

An incomplete inspection that qualifies an existing placement or metadata item belongs in that item’s status and detail, not in an additional generic “Document inspection” row repeating the same requirement. In the pictured state, the two such limitation rows should be absorbed into their respective substantive items, with their information preserved.

This is not permission to hard-code three rows, recognize sample titles/IDs, truncate a list, or globally deduplicate strings. Other uploads may have more/fewer areas and multiple affected documents. One document may have several independent substantive findings. Preserve those findings and each leaf’s provenance, context, actions, and conditions.

If incomplete inspection is the only actionable result, retain a clearly labeled review item. If structured facts cannot establish an area more specific than content inspection, use an honest general label. Never manufacture an applicant mismatch, stale text, or other finding to populate an expected demo area.

Projection rules:

- Use typed recorded facts/findings/statuses, not narrative-string parsing, to identify areas and associate limitations.
- Keep final decisions and repairs unchanged. Distinguish domain findings from analysis limitations.
- Attach each limitation to the applicable leaf/area and preserve additional unresolved checks in its detail.
- Derive item-specific badges from the applicable finding/qualification; retain the full document-level status separately in document detail. Do not blindly copy every document status to every item.
- Do not merge different lifecycle contexts or conflicting outcomes just because filenames or displayed text match.
- Use stable UI identities, including system identity for baseline comparison; avoid duplicate DOM IDs and index-dependent focus restoration.
- Count primary review items and affected documents/leaf contexts accurately. Present “documents” to users; explain differing leaf contexts only where needed.

Preserve these outcomes:

- Case A hard mapping plus abstention: retain the context-change decision/action; clearly state content inspection is incomplete and approval is required.
- Case B/C abstention without a substantive semantic finding: request completion of inspection; do not claim stale content was found.
- Supported applicant mismatch: show the actual mismatch, its evidence, and the bounded verification task.
- Provider/pipeline failure: no regulatory decision, with an explicit service-failure state.
- B2 intentionally omitted inspection: neither abstention nor semantic clearance.
- Out-of-policy coverage, missing history, and unassessed documents: visible and never represented as clean reuse.

Differentiate missing analysis evidence from evidence that exists but cannot be displayed because source metadata or a UI lookup is unavailable. The latter is a presentation limitation, not grounds to invent a new regulatory result. Missing required citations must not be silently replaced by unrelated graph evidence. Show the available facts and the exact unresolved limitation.

Do not force the model to find something, retry valid abstentions, tune prompts, or weaken validation to make the sample appear successful.

## 2. Replace the visual system with a coherent light theme

Use these palette roles throughout the app:

| Role | Value |
| --- | --- |
| Warm light background/base surface | `#F3E8DF` |
| Burgundy accent, primary controls, selected interactions | `#452829` |
| Main text | `#242424` |
| Secondary text | `#57595B` |
| Text on burgundy controls | `#F3E8DF` |

This resolves the light-theme requirement while preserving the requested cream text on dark accent surfaces. Do not use cream body text on cream/white surfaces. Use restrained lighter surfaces, borders, and shadows derived from this palette. Remove the current navy/black page backgrounds, blue accents, dark glass treatments, and competing typography. Keep real error/status distinctions with text/icons and accessible color; do not make all statuses visually identical.

Use **DM Mono by Colophon Foundry** as the primary application typeface, including controls. Use supported font weights, readable line height, and deliberate hierarchy. Keep paragraph measures around 55–70 characters where appropriate; result grids can be wider. Do not shrink text to force five columns onto a phone. Prefer local font assets with the required license and a usable monospace fallback so the offline demo does not depend on a Google Fonts request.

Use the Utopia calculators substantively:

- Type: https://utopia.fyi/type/calculator/
- Space: https://utopia.fyi/space/calculator/
- Grid/container: https://utopia.fyi/grid/calculator/

Choose and record suitable viewport endpoints, base sizes, scale ratios, spacing, and container/gutter values. A reasonable starting range is 360–1440px with 16–18px body text, then validate DM Mono’s actual layout. Generate reusable CSS custom properties with fluid `clamp()` values and relative units. Include the calculator configuration links in a design note or token comments. Apply the tokens across pages rather than adding isolated arbitrary sizes. Breakpoints remain appropriate for structural changes such as stacked upload choices.

Use Iconoir consistently. Apply the new theme to retained routes as well, including Evaluation and guided cases, without changing their research data.

## 3. Smooth scrolling and restrained motion

Provide smooth programmatic scrolling for page transitions, anchors, and relevant in-page navigation. Audit explicit `behavior: "instant"` overrides, including those in `WorkspaceFlow`. Respect `prefers-reduced-motion` by disabling smooth scrolling and unnecessary animation for that preference.

Keep native wheel/touch scrolling: no scroll hijacking or heavy smooth-scroll library. Use scroll padding/margins so the navigation does not cover headings or focused controls. The screenshot shows a heading obscured by the nav; fix that layout/focus interaction.

Use short, consistent transitions (approximately 150–220ms where appropriate), especially for controls, area pills, modal entry/exit, and selection states. Avoid animating every property, excessive motion, or layout shifts. Polling must not repeatedly steal focus or scroll the page. Preserve the overview’s scroll position when closing a modal.

## 4. Upload/home page

Follow the sketch with two equally clear alternatives under “Choose your dossier”:

- **Upload a dossier**: an accessible file picker/drop area with concise supported ZIP guidance.
- **Use the sample**: clearly identified as an alternative that loads the bundled synthetic dossier.

Place them side by side on desktop with a visible “or”; stack them on narrow screens while preserving that relationship. There is exactly one selected package at a time. Sample selection replaces the selected upload and vice versa. Guard against an asynchronous sample download overwriting a newer user selection.

After selection, show a compact summary with the actual filename, Change/remove control, and **Continue to options**. Both alternatives must enter the same production parsing/analysis flow; selecting the sample must not return canned presentation results or silently change model execution mode.

Remove “The uploaded ZIP is discarded…” explanatory text from this page. Keep concise input restrictions necessary to avoid misleading users about confidential sponsor submissions.

Replace the repeated FDA availability alert/banner with a calm, readable footer note on the **home/upload view only**. No warning triangle, alert role, alarming border, or repeated box. Identify home by the upload step as well as route, because options/results may also use `/`.

Suggested note: “Research prototype for selected FDA/CDER reuse checks. This demonstration explores prospective forward compatibility, which is not currently operational. Results do not establish submission readiness or FDA acceptance and have not been validated by a regulatory expert.”

Do not repeat this global footer note on options, processing, results, Baselines, About, Evaluation, or guided pages. Preserve truthful scope/provenance in actual records, existing scientific disclosures, and result-specific limitations. This is a presentation change, not a change to `not_operational` or `expert_validated: false`.

## 5. Options page

Remove the Scenario select and the user-facing “Current operational” choice. Use short explanatory text:

“We’ll compare your **eCTD v3.2.2** dossier with the selected **eCTD v4.0** requirements to identify reuse decisions.”

Style the two versions as tasteful burgundy-accent inline highlights. Add a brief scope phrase: “Selected FDA/CDER Module 3 checks · prospective research scenario.” Use the correct version numbers above, not the typo `3.2.21`.

The product request must explicitly use `prospective_forward_compatibility`. Do not delete the backend current-operational guard, historical contracts, or guided test capability. Ensure old browser state cannot silently submit current-operational mode behind text promising a prospective comparison. Update only the editable new-run setup, without mutating past runs.

Replace the metadata-intent select with a properly labeled native radio group:

- Preserve existing metadata.
- Plan metadata changes.
- I’m not sure yet.

Map these exactly to the existing intents. Keep undecided intent as the default for a new dossier unless the user explicitly selects otherwise. Preserve valid explicit intent when carrying the same inventory into Baselines.

Each choice has a small, styled question-mark help button. Provide a concise explanation on hover and keyboard focus, and on tap/click for touch users. Popovers must be accessible, dismissible with Escape/outside interaction, remain usable when the pointer enters them, and not change the radio value accidentally. Do not put a help button inside another interactive element. Explain the lifecycle consequences in the help text; do not erase the meaning of preservation.

Remove the “Server-configured analysis” field group/card and model/configuration identifiers from the normal setup. Model selection stays controlled by backend environment variables. Keep unavailable-configuration errors actionable. Retain only a compact factual execution/data-destination sentence near the analysis action: external provider, local service, or offline demonstration, as actually configured. Put full attribution in technical details. Do not silently fall back between execution modes.

## 6. Results and area modal

Keep the overview concise: Area / What was found / Next step / Affected documents / Status. Use the corrected primary-item semantics from section 1. Preserve Needs attention and All documents.

Area pills are real buttons with pointer cursor. On hover and keyboard focus, transition to burgundy with cream text and a visible focus treatment. Their accessible name should make the result context distinguishable when area names repeat.

Clicking an area opens a **near-full-screen overlay modal**, replacing the below-table expansion. Use most of the viewport with a small desktop inset; on phones use the available screen with safe-area padding. Implement:

- Accessible named dialog, modal semantics, focus containment, and inert background.
- A persistent header with area title and **X close button at top right**, outside the scrolling content or sticky within the correct container.
- Escape and close-button dismissal; accessible touch targets.
- One main vertical content scroller, body scroll lock, no background scrolling, and no hidden close button after long scrolling.
- Focus restoration to the opening button and restoration of the underlying page position.

Within the modal show document identity and source location, Current / Recommended / Why / Next step, followed by specific conditions. Keep content concise and do not repeat identical caveats under several headings.

Then present supporting evidence as in the sketch: identifiable source/file, cited passage, page/section/locator, and source link where available. Separate uploaded-document evidence from standards evidence. Explain missing evidence precisely.

Under “How this conclusion is supported,” offer the existing graph and typed-neighborhood/text views. On wide screens they may sit side by side as sketched; stack or tab them if that is clearer on narrow screens. Reuse real graph data and existing graph capability. If no interactive graph exists locally, implement only a bounded faithful view of existing nodes/edges or preserve the existing view and report its scope; do not fabricate decorative relationships. Keep readable text alternatives. Technical execution/trace/digests belong in a separate collapsed section.

All documents is a real inventory view as sketched, not merely the same action list with another filter. Include original document title, filename, source section, assessed/coverage status, and a Review control. Preserve distinct leaf contexts when one physical file appears more than once. Include clean, incomplete, out-of-scope, missing-history, unassessed, and failed entries with honest labels. All must remain inspectable.

Apply the shared presentation to interactive Baselines without giving B0/B1 RegBridge-only evidence, rules, or graph explanations. Preserve system attribution and native missing-information disclosures. Analyzer must contain no baseline statistics or comparisons.

## 7. Navigation and About

Top navigation: **Analyzer, Baselines, About**. Remove Evaluation and Guided cases from desktop and mobile nav only. Keep their routes, direct links, functionality, and historical content intact; do not delete or redirect them to home.

Simplify About to:

- Title: “About RegBridge”.
- One short paragraph explaining scoped, evidence-grounded reuse decision support.
- A compact sequence: read the dossier; apply selected standards-based checks; inspect bounded content with AI when applicable; combine results and show recommendations/evidence/limitations.

Do not imply automatic standards discovery, expert approval, complete FDA validation, or file conversion. Remove the large source registry, hashes, milestone history, and repeated warning panels from About’s main presentation. Keep necessary provenance accessible through evidence/technical views and existing APIs. Do not add another elaborate dashboard.

## 8. Verification and delivery

Implement focused tests for the actual diagnosed bug and interactions. Validate:

- The pictured combination yields placement, manufacturer metadata, and supported applicant/content items without two extra generic limitation rows. Each applicable item still visibly shows its incomplete-inspection qualification.
- An inspection-only outcome remains visible; changing findings changes the overview. Arbitrary uploads are not forced to three items.
- Multi-finding, multi-document, repeated-path/different-context, clean, missing-evidence, abstention, out-of-coverage, and failure states retain their meaning.
- Sample/upload selection, cancellation, replacement, metadata radios/help, configuration errors, and stale browser scenario state behave correctly.
- Modal keyboard access, Escape, focus return, close-button visibility at the bottom of a long result, touch behavior, and background scroll lock work.
- Smooth scrolling respects reduced motion; headings are not obscured by the nav.
- Evaluation and guided URLs still work after their nav entries are removed.
- New-run product configuration remains backend-owned and historical attribution is unchanged.

Run the repository’s applicable lint, type, schema, component, backend, E2E/accessibility, and protected-artifact checks. Do not rewrite frozen digests to make a gate pass. Distinguish pre-existing verifier incompatibilities from new regressions and report them honestly.

Use fresh correctly configured development servers. Inspect real screenshots at 1440×900, 1280×720, and approximately 390×844, including upload, options, results, All documents, a long scrolled modal, Baselines, and About. Check text contrast, 200% zoom, content overflow, wrapping, and reduced motion. Tests passing alone are not visual acceptance.

No paid/live experiment is required by this task. Use representative recorded responses and the production synthetic package in network-free verification. Do not alter prompts or rerun frozen experiments. State clearly whether any live check was performed.

Deliver the code changes, a short diagnosis of the original extra rows, the presentation grouping rules, screenshots, exact checks/results, and any remaining limitations. Explain the palette roles and record Utopia token settings. Leave the branch ready for my visual review; do not claim completion from test counts without examining the rendered pages.
