# Dossier and comparison UX

The September 6, 2026 wording and layout pass adds an upload, options, processing, and results
flow to the M4.2.2 product workspaces. It does not change migration rules, decisions, source
evidence, model prompts, benchmark labels, or historical presentation artifacts.

## Using the workspaces

In Analyzer, choose a ZIP or try the sample dossier, continue to options, confirm the intended
context, and select **Parse and analyze**. The existing thinking-orb loader occupies the working
screen until the run reaches a terminal state. Results replace the form and receive keyboard
focus. **Edit setup** retains the chosen file and options; **Back to home** starts a fresh screen.
Leaving the page does not cancel work already submitted to the server.

In Baselines, read a ZIP's document list or use the previous parsed inventory. Choose documents
and an available model, then select **Run comparison**. Changing dossiers requires reading the
new document list before comparison. All systems receive the same selected inputs. The page
reports differing decisions without scoring correctness or ranking systems.

Decisions and coverage use readable labels. Incomplete inspection and failed processing remain
distinct. Package checks and technical records retain details for investigation. Connection
errors offer actionable recovery; retrying a status check does not create a second run.

## Verification

Run from the repository root:

- `npm --prefix frontend run lint`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `npm --prefix frontend run test:ux`

The browser command starts isolated servers on ports 8011 and 5174, forces offline fixture mode,
and uses `results/ux-verification.sqlite3`. It does not use a live model. Screenshots and failure
traces are written under the ignored `frontend/test-results/` directory.

Verified: 17 component tests, four browser journeys, production build, and automated accessibility
checks. Browser journeys include a real synthetic ZIP, desktop 1440 x 900 and mobile 390 x 844,
focus transitions, absence of page-wide horizontal overflow, loading-only content, and return
navigation. Existing guided-case and evaluation journeys also pass. Initial browser checking
found duplicated comparison-region names; the corrected names identify each document.

Not verified in this UX pass: live-provider execution, manual screen-reader use, 200% browser
zoom, RTL layouts, and the full backend milestone verification suite. The historical paper
screenshots were not regenerated.
