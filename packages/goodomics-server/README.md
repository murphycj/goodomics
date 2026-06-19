# goodomics-server

Optional FastAPI, MCP, database, and React dashboard server package for Goodomics.

The server provides namespaced `/api/v1/*` routes for runs, samples, metrics, artifacts,
reports, cohorts, QC policies, report templates, and typed database edits; `/mcp/*` remains
reserved for MCP tools/resources. A Vite React dashboard lives in `dashboard/` and builds into
`src/goodomics_server/web/static/` so production FastAPI can serve `/assets/*` and fall back to
`index.html` for React routes.

## Development

```bash
uv run --package goodomics-server goodomics-server serve --reload
cd packages/goodomics-server/dashboard && npm run dev
cd packages/goodomics-server/dashboard && npm run build
```

## Database bootstrap

The initial scaffold uses the core SQLAlchemy storage implementation to create tables with
`metadata.create_all()` for local bootstrap flows. The `db/migrations/` directory is reserved for
future Alembic revisions as the server schema evolves, including `report_templates` and
`report_template_revisions`.
