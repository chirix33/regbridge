# RegBridge standards source ledger

This ledger records frozen regulatory materials for a controlled **prospective** FDA/CDER
forward-compatibility research scenario. FDA forward compatibility is currently
`not_operational`. A registered source does not independently authorize an executable conclusion.

| Source ID | Frozen artifact and digest | Author-verified locators | Governance |
|---|---|---|---|
| `fda-ectd-v4-ctoc-v2.2` | `snapshots/fda-ectd-v4-ctoc-headings-v2.2.pdf`; `382ec5e00b44d179abe7d3e1d9cebecef939938218c36badbde1689f54bfc3e6` | PDF page 8 / printed page 5: `3.2.S.1` remains. PDF page 39 / printed page 36: `3.2.S.1.1`–`3.2.S.1.3` are removed subheadings. | `source_verified` by `author-01`; `expert_validated: false`. |
| `fda-ectd-v4-tcg-v1.5` | `snapshots/fda-ectd-v4-technical-conformance-guide-v1.5.pdf`; `dccd247940cdf5bc7cbf6a5e31b8f2547ad7f61650ae1a138113feb315f8002e` | §2.1 / PDF page 13: replacement retains headings/attributes. §1.5.4 / PDF page 11: changed placement requires a new context group and old-context suspension; reuse by document identifier does not require resubmission of the file or document element. §1.5.5 / PDF page 12: existing hyperlinks must be relevant to the new context. | `source_verified` by `author-01`; `expert_validated: false`. |
| `fda-m4-ctd-organization-october-2017` | `snapshots/fda-m4-ctd-organization-october-2017.pdf`; `cc5672cdc3feb352d01c2cbfc823ea6cc3d45e657f3a4ca806cf486b41933cde` | Appendix A / PDF page 25 / printed page 22: manufacturer is optional; general umbrella values including `all` are not recommended when differentiation is unnecessary. | `source_verified` by `author-01`; nonbinding recommendation; `expert_validated: false`. |

Official FDA downloads:

- [CTOC v2.2](https://www.fda.gov/media/179699/download)
- [Technical Conformance Guide v1.5](https://www.fda.gov/media/179700/download)
- [M4 CTD Organization Guidance, October 2017](https://www.fda.gov/media/71551/download)

## M1 adjudicated derivation

Rule `FDA-CDER-M1-REMOVED-SUBHEADING-001` uses only this explicit mapping:

```text
3.2.S.1.1 → 3.2.S.1
3.2.S.1.2 → 3.2.S.1
3.2.S.1.3 → 3.2.S.1
```

The rule is `author_adjudicated_for_demo`, based on `mechanical_derivation`, and `hard` only
within the controlled prospective FDA/CDER scenario. Its decision is `REUSE_WITH_NEW_CONTEXT`; its
repair is `CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_LEGACY_CONTENT`. The existing document is reused
through its identifier without resubmitting the physical file or document element. No generic
nearest-parent algorithm is authorized.

This is internal research governance, not FDA approval, professional eCTD validation, or expert
regulatory ground truth.

## M2 adjudicated rules

- `FDA-CDER-M2-DISCOURAGED-MANUFACTURER-ALL-001` is a `medium`, `advisory`
  direct encoding of a nonbinding recommendation. It cannot force repair or claim noncompliance.
- `FDA-CDER-M2-PRESERVE-EXISTING-CONTEXT-002` is a `hard` controlled-eligibility
  mechanical derivation. It applies only with explicit preservation intent, exact matching,
  successful deterministic checks, and no hyperlinks or fixture hyperlinks whose relevance and
  destination have been author-verified. Its decision is `REUSE_AS_LEGACY_REFERENCE`, while the
  separate `manufacturer="all"` advisory remains visible.
- `FDA-CDER-M2-NORMALIZE-MANUFACTURER-003` is `hard` only after explicit normalization
  intent. It returns `REUSE_WITH_NEW_CONTEXT` and
  `CREATE_NEW_CONTEXT_GROUP_AND_SUSPEND_OLD`; the unchanged physical file/document element is not
  resubmitted. The optional keyword is omitted when partitioning is unnecessary, otherwise only an
  explicitly supplied stable value is accepted.
- `FDA-CDER-M2-HYPERLINK-RELEVANCE-004` is a `semantic_signal`. Unverified,
  contradictory, stale, or incompletely inspected links yield `HUMAN_REGULATORY_REVIEW`.

All four rules are `author_adjudicated_for_demo` by `author-01`, limited to the controlled
prospective FDA/CDER scenario, and remain `expert_validated: false`.

## Operational-availability record

`operational-status.yaml` records `not_operational` as an
`author_adjudicated_for_demo` mode guard at the direction of `author-01`. It is disabled as an
executable rule, is not source-verified evidence for the heading constraint, and remains
`expert_validated: false`. The record links the current FDA eCTD status page and carries an explicit
time-sensitive re-verification assumption.
