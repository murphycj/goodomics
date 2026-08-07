# Report configuration

Goodomics stores reports as YAML documents. A report arranges
saved insights in a grid and can add filters or result-row defaults. See the
[insight configuration reference](insight-configuration.md) for the insight
definitions referenced by report insights.

## Example

```yaml
version: 1
name: RNA sequencing QC report
description: Reusable project QC overview.

filters: []
limit: 1000
random: false

layout:
  columns: 12
  row_height: 64

insights:
  - id: sample-qc-overview
    layout:
      x: 0
      y: 0
      width: 12
      height: 6

refresh_policy:
  mode: manual
```

The executable inputs are `version`, `filters`, `limit`, `random`, `layout`,
`insights`, and optional `refresh_policy`. Name and description are saved
metadata. The server generates the stable report ID when it saves the report.

### `version`

Required. The report schema version. The only supported value is `1`.

### `name`

Required and nonblank in every complete report document. Human-readable report
name. Partial patch requests may omit it, but cannot clear it.

### `description`

Optional explanatory text stored with the report and rendered snapshot.

### `filters`

Optional. Uses the same `field`, `operator`, and `value`
shape as
[`analysis.filters`](insight-configuration.md#analysisfilters).

Report filters are added to each insight as AND conditions. They cannot change
an insight's grain, values, aggregations, matching rules, join behavior, or
occurrence scope.

### `limit`

Optional integer from 1 to 10,000. When present, it overrides each referenced
insight's `analysis.limit` after report filters, aggregation, and joining have
finished.

### `random`

Optional boolean. When present, it overrides each referenced insight's
`analysis.random`. Set it to `true` to select completed result rows randomly or
`false` to preserve their stable order.

For both settings, precedence is execution request, saved report, saved
insight, then the server defaults of `limit: 1000` and `random: false`.

### `layout`

Optional; defaults to a 12-column grid with a 64-pixel row unit.

#### `layout.columns`

Integer from 1 to 48; defaults to `12`. Every insight must satisfy
`x + width <= columns`.

#### `layout.row_height`

Integer from 1 to 1,000; defaults to `64`. It defines the rendered height of
one grid row.

### `insights`

Required and must contain at least one entry. Each entry references one saved
insight and gives it a grid placement.

#### `insights[].id`

Required and unique within the report. This is the public ID of an existing
saved insight in the same project and is also its grid/render identity. The
server validates existence, ownership, and permission and never silently drops
a missing insight. One saved insight can occur in a report only once.

#### `insights[].layout`

Required placement object:

| Input    | Constraint            | Purpose               |
| -------- | --------------------- | --------------------- |
| `x`      | Integer, 0 or greater | Left grid coordinate  |
| `y`      | Integer, 0 or greater | Top grid coordinate   |
| `width`  | Positive integer      | Width in grid columns |
| `height` | Positive integer      | Height in grid rows   |

### `refresh_policy`

Optional. Currently contains one input, `mode`, whose only supported value and
default is `manual`.

## Strict validation

Report create, executable patch, validation, preview, and execution requests
all use the same strict model. Unknown keys, invalid filters, missing or
cross-project insight dependencies, duplicate insight IDs, and out-of-bounds
layouts are rejected before persistence. Missing insights are never silently
dropped.
