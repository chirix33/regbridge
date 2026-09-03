# 001 - Add Analysis Results Entry Motion

- **Status**: DONE
- **Commit**: e9225ba
- **Severity**: LOW
- **Category**: Missed opportunities
- **Estimated scope**: 2 files, small CSS and class-name edits

## Problem

When an analysis run completed, the result region appeared immediately. On the AAAI demonstration path, that abrupt insertion made the async state change feel like a page jump instead of a completed analysis handoff. The result area is occasional, not high-frequency, and the purpose is preventing a jarring change.

Current implemented attachment point:

```tsx
/* frontend/src/pages/HeadingCasePage.tsx:277 - current */
{analysis && (
  <div className="analysis-results motion-enter" aria-live="polite" ref={resultsRef} tabIndex={-1}>
```

Current implemented motion tokens and entry rule:

```css
/* frontend/src/styles/index.css:86 - current */
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);
--duration-entry: 220ms;

/* frontend/src/styles/index.css:218 - current */
.motion-enter {
  transition:
    opacity var(--duration-entry) var(--ease-out),
    transform var(--duration-entry) var(--ease-out);
}

@starting-style {
  .motion-enter {
    opacity: 0;
    transform: translateY(12px) scale(0.985);
  }
}
```

## Target

The analysis-results container enters with a single CSS `@starting-style` transition. The target values are exact:

```css
/* target */
:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --duration-entry: 220ms;
}

.motion-enter {
  transition:
    opacity 220ms var(--ease-out),
    transform 220ms var(--ease-out);
}

@starting-style {
  .motion-enter {
    opacity: 0;
    transform: translateY(12px) scale(0.985);
  }
}

@media (prefers-reduced-motion: reduce) {
  .motion-enter {
    transform: none;
    transition: opacity 120ms linear;
  }

  @starting-style {
    .motion-enter {
      opacity: 0;
      transform: none;
    }
  }
}
```

## Repo conventions to follow

- Shared motion tokens live in `frontend/src/styles/index.css` under `:root`; do not create per-component easing constants.
- The frontend uses React class names and global CSS rather than a motion library for this category of UI state change.
- Keep the result container accessible: `aria-live="polite"`, focus target behavior, and `tabIndex={-1}` must remain intact.
- Existing exemplar: `frontend/src/pages/HeadingCasePage.tsx:278` attaches `motion-enter` to the results container without changing result semantics.

## Steps

1. In `frontend/src/styles/index.css`, add `--ease-out: cubic-bezier(0.23, 1, 0.32, 1);` and `--duration-entry: 220ms;` under `:root` if they are missing.
2. In `frontend/src/styles/index.css`, add `.motion-enter` with transitions only for `opacity` and `transform`.
3. In `frontend/src/styles/index.css`, add an `@starting-style` block that starts `.motion-enter` at `opacity: 0` and `transform: translateY(12px) scale(0.985)`.
4. In `frontend/src/styles/index.css`, add a `prefers-reduced-motion: reduce` branch that removes transform movement and keeps `opacity 120ms linear`.
5. In `frontend/src/pages/HeadingCasePage.tsx`, add `motion-enter` to the `.analysis-results` container and keep the existing `aria-live`, `ref`, and focus props.

## Boundaries

- Do NOT animate individual findings, evidence rows, trace list items, graph nodes, or metric rows.
- Do NOT add a new animation dependency.
- Do NOT use `transition: all`, `ease-in`, `scale(0)`, layout-position movement, or durations over 300ms.
- Do NOT change regulatory decision data, evidence rendering, focus behavior, or analysis API calls.
- If a step does not match the code at commit `e9225ba`, stop and report the drift instead of improvising.

## Verification

- **Mechanical**: run `npm run lint`, `npm run typecheck`, `npm run test -- --run`, and `npm run build` from `frontend`; all must pass.
- **Feel check**: run the UI, trigger a case analysis, and confirm the completed result region fades in with a small upward settle, not a large slide or bounce.
- **Feel check**: in DevTools Animations, slow playback to 10 percent and confirm the result starts at `translateY(12px) scale(0.985)` and ends at normal position and scale.
- **Reduced motion**: emulate `prefers-reduced-motion: reduce` and confirm the result uses opacity only with no visible position movement.
- **Done when**: the analysis-results container enters once on analysis completion, remains readable while entering, and the focus target still works for keyboard and screen-reader users.
