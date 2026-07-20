# CLI

The Goodomics CLI is the main entry point for standalone reports, local ingest,
and server startup.

## Inspect the command

```bash
goodomics --help
```

From a checkout of the repository:

```bash
uv run --package goodomics goodomics --help
```

## Generate a standalone report

```bash
goodomics report ./results --template rnaseq-qc.yaml --out report.html
```

The report command should support exported dashboard templates, so templates can
round-trip between local report generation and dashboard editing.

Saved report definitions can also be rendered from the local Goodomics metadata
store:

```bash
goodomics report ./results --report project-overview --project rnaseq-core --out report.html
```

When `--report` is provided, Goodomics loads the saved report, executes its
saved insights against the selected project's SQL metadata store and DuckDB analytical
store, and writes a self-contained HTML snapshot.

!!! note "Offline reports"
    Standalone reports should be self-contained HTML files by default. They
    should not require CDN-hosted JavaScript, CSS, fonts, or images.

## Ingest outputs

Use ingest when you want Goodomics to preserve run context in local or team
storage:

```bash
goodomics ingest ./results \
  --project rnaseq-core \
  --report rnaseq-qc@v3 \
  --cohort production-rnaseq-hg38@2026-05 \
  --run-id 2026-06-16_batch_042
```

On the first `goodomics ingest`, `goodomics init`, or `goodomics serve` in a
directory, Goodomics creates `./goodomics.toml` with local defaults. Use
`--config path/to/settings.toml` or `GOODOMICS_CONFIG` to choose another
location; Goodomics creates a missing selected file and never replaces an
existing one. Ingest reads database, analytics, and file-storage defaults from
that configuration, while its command-line flags remain higher precedence.

Built-in CLI ingest types include `multiqc` and `cbioportal`. Custom parsers
defined in notebooks are Python-process local; package reusable parsers with a
`goodomics.sources` entry point when they should be discovered by the CLI.

## Start local services

```bash
goodomics serve
goodomics ui
```

`goodomics serve` starts the optional server surface. `goodomics ui` should stay
focused on the local dashboard workflow.

## Manage secured installations

User management is available only when `[auth].enabled = true`. The first
administrator can be created without existing credentials while installation
setup is still open:

```bash
goodomics users create-admin
```

After setup, every user-management operation requires an active installation
administrator. Use `--admin-email` (or `GOODOMICS_ADMIN_EMAIL`) to identify the
administrator; Goodomics requests that administrator's password with a hidden
prompt. If another user command is run before setup, the CLI offers to create
the first administrator interactively.

```bash
goodomics users create --admin-email owner@example.org
goodomics users create-admin --admin-email owner@example.org
goodomics users reset-password user@example.org
goodomics users disable user@example.org
```

Administrator resets set `must_change_password` and invalidate outstanding
bearer tokens. Goodomics does not send password-recovery email in this release.
Goodomics rejects user-management commands when authentication is disabled and
prevents disabling the final active installation administrator. Creating the
first administrator from the CLI also closes the dashboard's setup flow.

For non-interactive installation automation, `GOODOMICS_ADMIN_PASSWORD` supplies
the authorizing administrator password without placing it on the command line.
Keep that variable in a secret store rather than in the TOML configuration.

## Manage project visibility

Use a project ID or slug to make an existing project public or private:

```bash
goodomics projects set-visibility rnaseq-core public \
  --admin-email owner@example.org
goodomics projects set-visibility rnaseq-core private \
  --admin-email owner@example.org
```

When authentication is enabled, this operation requires an active installation
administrator, using the same hidden prompt or administrator environment
variables as user management. With authentication disabled, the local operator
can change visibility directly. Public visibility and the `[anonymous]`
permission list work together: visibility exposes the project, while the TOML
permissions determine which anonymous operations are allowed within it.
