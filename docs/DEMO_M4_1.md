# M4.1 product demonstration

Generate or verify the public synthetic dossier:

```powershell
.\.venv\Scripts\python.exe scripts\generate_m4_1_dossier.py --check
```

Start RegBridge with `LLM_MODE=fixture` for a network-free demonstration, open `/`, and upload
`data/demo-dossiers/m4-1/regbridge-m4-1-composite.zip`. Confirm the visible FDA/CDER target,
prospective scenario, preservation intent, and synthetic-data declaration. The profile panel must
report three dossier documents, matching index MD5, and scoped checks.

Open each result. Case A shows the XML-derived removed heading and context-group repair; Case B
shows the XML-derived manufacturer value and lifecycle-preservation advisory; Case C shows PDF
applicant wording compared with `us-regional.xml`. Evidence, trace, model record, graph, edge table,
and text alternative remain available in the document drawer.

Open `/baselines`, reuse the current inventory, and run all four systems. Discuss agreement and the
Case C B2/RegBridge contrast without accuracy, winner, ranking, or superiority language. B1 exposes
its ranked BM25 spans; B2 is explicitly `No LLM`.

For a live product run, use the allowlisted GPT-5.5 server configuration. Temperature is omitted.
Qwen remains greyed out and cannot be called. Interactive runs are not benchmark evaluations.

Run `scripts/m4-1-verify.ps1` twice before presentation. Full DTD/FDA validation, multi-sequence
history reconstruction, confidential submissions, and public deployment remain out of scope.

Generate the four presentation screenshots with `scripts/m4-1-capture.ps1`. The command runs
entirely in fixture mode, uploads the real composite ZIP, and writes images plus a hash manifest
under `paper/figures/m4-1/`. It never calls a network model or changes M3/M4 artifacts.
