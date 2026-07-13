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

## Configuration and authentication

Server settings use typed TOML sections. Configuration precedence is command
line arguments, `GOODOMICS_*` environment variables, TOML, then built-in
defaults. `--config` selects a file explicitly; otherwise Goodomics checks
`GOODOMICS_CONFIG` and then `./goodomics.toml`. Relative database, analytics,
secret-file, and filesystem-storage paths are resolved from the selected TOML
file. The first `goodomics init`, `goodomics serve`, or `goodomics ingest`
creates the selected file with local defaults when it is missing. Goodomics
never replaces an existing configuration.

Authentication is disabled by default. Local installations remain unrestricted
and do not need a signing key or user rows. A minimal secured setup is:

```toml
[auth]
enabled = true
signup_enabled = false
```

```bash
export GOODOMICS_AUTH_SECRET="replace-with-a-long-random-secret"
goodomics init --config goodomics.toml
goodomics serve --config goodomics.toml
```

When authentication is enabled and the installation has no users, the
dashboard redirects to **Set up Goodomics**. The setup form creates the first
installation administrator, signs that user in, and permanently closes the
first-run endpoint. Installation administrators have full permissions across
projects, users, roles, and installation-level operations. You can instead
complete setup from the command line with
`goodomics users create-admin --config goodomics.toml`.

The default password policy requires only six characters. Length and optional
composition rules are configured in TOML:

```toml
[auth.password]
min_length = 6
# max_length = 128
require_uppercase = false
require_lowercase = false
require_number = false
require_symbol = false
```

Omit `max_length` to leave it unrestricted. The same values can be overridden
with `GOODOMICS_AUTH_PASSWORD_MIN_LENGTH`,
`GOODOMICS_AUTH_PASSWORD_MAX_LENGTH`, and the corresponding
`GOODOMICS_AUTH_PASSWORD_REQUIRE_*` environment variables. The policy applies
to first-run setup, public signup, administrator-created users, password
changes, and CLI-created or reset passwords.

Installation administrators also see **User management** in the account menu.
That page creates and disables accounts, grants or removes installation-admin
access, resets passwords, and assigns each user a role per project. It shows
the permissions supplied by every assigned role. Goodomics prevents disabling
or demoting the final active installation administrator.

Passwords are stored with Argon2id. Login issues a 60-minute HS256 bearer token;
password changes and administrator resets invalidate existing tokens. Public
signup is separate from first-run setup and remains off unless
`auth.signup_enabled` is explicitly enabled. Password recovery is
administrator-driven with `goodomics users reset-password`.

Projects are private by default. Marking a project public makes only the
configured `[anonymous].permissions` effective for unauthenticated requests.
Project access is capability-based through editable Viewer, Analyst, Data
Manager, Owner, and custom roles.

See `goodomics.example.toml` for all sections, named filesystem/S3 locations,
anonymous capabilities, AI settings, and login/AI rate policies. Secrets belong
in environment variables, secret files, or provider credential chains.

!!! note "Persistent databases"
SQLite and DuckDB files require persistent local or block storage. Named S3
locations store managed files; they are not database backup destinations.

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
