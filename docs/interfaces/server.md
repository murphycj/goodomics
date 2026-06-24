# Server

Run the optional server when you want the FastAPI API, MCP access, database
mode, and the React dashboard.

## Start the server

```bash
goodomics serve
```

For local development from the repository:

```bash
uv run --package goodomics goodomics serve --reload
```

The FastAPI API is available under `/api/v1/*`. MCP routes remain separated
under `/mcp/*`.

## Dashboard assets

The React dashboard builds into:

```text
packages/goodomics/src/goodomics/server/web/static/
```

When dashboard assets are present, the server can serve the built dashboard.
When assets are missing, `/` returns setup guidance by default.

## Proxy to Vite

To proxy dashboard requests to Vite during development, set
`GOODOMICS_DASHBOARD_DEV_URL` and run the dashboard dev server:

```bash
GOODOMICS_DASHBOARD_DEV_URL=http://127.0.0.1:5173 \
  goodomics serve --reload
```

```bash
cd packages/goodomics/dashboard
npm run dev
```
