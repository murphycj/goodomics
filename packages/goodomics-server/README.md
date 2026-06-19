# goodomics-server

Optional FastAPI, MCP, and database server package for Goodomics.

## Database bootstrap

The initial scaffold uses the core SQLAlchemy storage implementation to create tables with
`metadata.create_all()` for local bootstrap flows. The `db/migrations/` directory is reserved for
future Alembic revisions as the server schema evolves.
