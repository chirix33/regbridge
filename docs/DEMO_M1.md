# Five-minute demonstration — M1 segment

1. Begin on the scope page and point to **FDA forward compatibility: `not_operational`**, the
   prospective-scenario label, and **expert validated: no**.
2. Open **Run M1 heading case**. Keep prospective research mode selected.
3. Run `3.2.S.1.1`. Show the parsed leaf and exact source placement, then the
   `REUSE_WITH_NEW_CONTEXT` decision.
4. Open each evidence card. Show both FDA snapshot digests and the approved page/section locators.
5. Read the repair: create a new `3.2.S.1` context group, suspend legacy content, reuse the existing
   document identifier, and do not resubmit its physical file or document element.
6. Inspect the typed graph and its text alternative; show the three explicit `MAPS_TO` edges.
7. Run `3.2.S.1` as the clean negative, then `3.2.S.1.4` to show abstention without nearest-parent
   inference.
8. Return to `3.2.S.1.1`, select **Current operational**, and run again. Show that the prospective
   rule is bypassed and the result is unresolved `HUMAN_REGULATORY_REVIEW` because availability is
   `not_operational`.

Close by stating: RegBridge is an FDA/CDER-scoped decision-support research prototype; its M1
labels are author-adjudicated and not regulatory-expert validated.
