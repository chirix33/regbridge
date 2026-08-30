# M2 scenario statement for paper and demonstration

RegBridge evaluates a controlled **prospective** FDA/CDER eCTD v3.2.2-to-v4.0 research scenario.
FDA forward compatibility is recorded and displayed as `not_operational`; current-operational mode
does not execute the prospective M1/M2 rules. The prototype is risk analysis and decision support,
not FDA certification, regulatory advice, or a predictor of filing/application acceptance.

For Case B, FDA's nonbinding manufacturer-keyword guidance produces a visible advisory for
`manufacturer="all"`, not a claim of noncompliance. Explicit preservation can retain
`REUSE_AS_LEGACY_REFERENCE` only under a hard, author-adjudicated controlled-eligibility gate.
Explicit normalization yields `REUSE_WITH_NEW_CONTEXT`, creates a new context group, suspends the
old one, and reuses an eligible unchanged document by identifier. Missing intent abstains.

For Case C, deterministic structural/lifecycle rules establish initial eligibility. Supported stale
or ambiguous PDF text/link evidence, unverified hyperlink relevance, or incomplete required
inspection yields `HUMAN_REGULATORY_REVIEW`. Semantic signals never independently produce a hard
prohibition, lifecycle break, `REUSE_WITH_NEW_CONTEXT`, or compliance determination. A model-only
clean result cannot author-verify hyperlink relevance.

The sources, formalized rules, and canonical Case B label are author-verified/adjudicated by
`author-01`; no qualified external regulatory reviewer has validated them. Accordingly,
`expert_validated: false` is retained throughout.
