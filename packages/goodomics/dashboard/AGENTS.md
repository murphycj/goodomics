# Goodomics Dashboard Agent Guide

This directory contains the React/Vite dashboard for Goodomics.

Use `instructions/FRONTEND.md` for shared dashboard, reporting, charting,
visual, and UI guidance.

## React Guidance

- Use `$vercel-react-best-practices` when writing, reviewing, or refactoring
  dashboard React code, including components, hooks, client-side data fetching,
  rendering performance, bundle size, and UI performance work.
- Treat the Vercel React guidance as React/Vite guidance first. Next.js,
  React Server Components, Server Actions, and Vercel deployment advice are
  advisory unless this dashboard adopts those technologies.
- Follow the repo-level frontend stack: Tailwind, Radix/shadcn-style
  components, `lucide-react`, TanStack primitives for data workflows, and
  Apache ECharts for charts.
- Keep component changes scoped and preserve Goodomics' biotech/R&D product
  feel: credible, work-focused, approachable, and not generic SaaS decoration.
- Avoid performance theater. Prefer concrete improvements: remove avoidable
  eager imports, stabilize hook dependencies, reduce unnecessary rerenders,
  split heavy components when useful, keep chart payloads bounded, and prevent
  layout shifts.

## Verification

- For dashboard source changes, run
  `npm --prefix packages/goodomics/dashboard run build` when feasible.
- Do not commit generated dashboard assets under
  `packages/goodomics/src/goodomics/server/web/static/`.
