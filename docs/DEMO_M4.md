# M4 five-minute demonstration operator guide

Start the local application in fixture mode:

```powershell
.\scripts\dev.ps1
```

Open `http://127.0.0.1:5173`.

Every page carries the same primary navigation (Scope / Demonstration / Evaluation), and each
demonstration page carries a Case A / Case B / Case C switcher directly under its heading, so the
shot list below can be walked without returning to Scope between cases.

## Shot list

- 0:00-0:30: open Scope, state the narrow problem, show FDA/CDER scope, `not_operational`, and
  `expert_validated: false`.
- 0:30-1:35: open Case A, run the removed `3.2.S.1.2` placement preset, show identifier reuse,
  new context group, legacy suspension, source evidence, and graph edge table.
- 1:35-2:55: open Case C, run stale applicant/content mismatch, then show the dashboard case trace
  contrasting B2 legacy reuse with RegBridge human-review escalation.
- 2:55-4:10: open Evaluation, show repetition separation, unsafe-FNR and review-bypass, family
  sensitivity caveat, BM25 retrieval panel, reasoning/usage, and cost.
- 4:10-4:35: open Case B, run the lifecycle-sensitive manufacturer metadata scenario.
- 4:35-5:00: return to the disclosure boundary: RegBridge is human decision support, not FDA
  advice or acceptance prediction.

## Capture checklist

Run `.\scripts\m4-verify.ps1` first. Capture 1440x900 and 1280x720 screenshots for:

- `/demo/case-a` after evidence and graph trace are visible;
- `/demo/case-c` after the stale-content decision is visible;
- `/demo/case-b` after metadata findings are visible;
- `/evaluation` with the decision metrics and retrieval panel visible.

Store presentation-only screenshots under `paper/figures/m4/` and update
`paper/figures/m4/manifest.json` with viewport, route, fixture, snapshot digest, capture command,
and image SHA-256.

## Recovery path

If the API is not running, restart with `.\scripts\dev.ps1`. If a live model key is unavailable,
do nothing: the recording path uses fixture analysis and the committed presentation snapshot only.
If browser automation is unavailable, use the static screenshot manifest and manual route sequence
above; do not regenerate or edit M3 results during recovery.

