# Database backends

Goodomics defaults to local-first storage, then allows teams to move to a more
durable catalog database when needed.

## SQLite

SQLite is the default catalog store for local product and project metadata.

```bash
GOODOMICS_DATABASE_URL=sqlite+aiosqlite:///.goodomics/goodomics.db
```

## Postgres

Use Postgres for more durable team deployments:

```bash
GOODOMICS_DATABASE_URL=postgresql+psycopg://localhost/goodomics
```

## MySQL

Use MySQL when it fits existing infrastructure:

```bash
GOODOMICS_DATABASE_URL=mysql+aiomysql://localhost/goodomics
```

!!! note "Analytical storage"
    The catalog database stores product metadata. DuckDB remains the default
    local analytical store for project-level metrics and omics-shaped tables.
