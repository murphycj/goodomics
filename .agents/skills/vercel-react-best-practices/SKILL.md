---
name: vercel-react-best-practices
description: React performance and styling guidance for Goodomics dashboard work. Use when writing, reviewing, or refactoring React/Vite dashboard code, especially components, hooks, client-side data fetching, rendering performance, bundle size, Tailwind styling, or UI performance.
license: MIT
metadata:
  author: vercel
  version: "1.0.0"
---

# Vercel React Best Practices

Use this skill when changing React code in `packages/goodomics/dashboard`, or
when a task mentions React component performance, client-side data fetching,
bundle size, rendering behavior, hooks, memoization, Suspense, or UI refactors.

Goodomics-specific use:

- Treat this as React/Vite guidance first. Next.js, React Server Components,
  Server Actions, and Vercel deployment rules are advisory unless the dashboard
  adopts those technologies.
- Keep Goodomics dashboard conventions ahead of generic advice: Tailwind,
  Radix/shadcn-style components, `lucide-react`, TanStack primitives, and
  Apache ECharts.
- Prefer targeted improvements that preserve existing product behavior and
  biotech/R&D visual tone.
- Before finishing dashboard edits, check for avoidable eager imports,
  unnecessary rerenders, unstable hook dependencies, oversized client payloads,
  layout shifts, and missing loading/error/empty states.

For detailed Vercel Engineering rules and examples, search `AGENTS.md` in this
skill directory for the relevant category or rule instead of loading unrelated
sections.

Source: `vercel-labs/agent-skills`, `skills/react-best-practices`, MIT.
