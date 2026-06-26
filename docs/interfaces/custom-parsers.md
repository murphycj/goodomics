# Custom parsers

Use a custom parser when your lab has a table, dataframe, notebook object, or
internal result format that Goodomics does not parse yet.

Users write parsers. Goodomics handles ingestion: creating runs, samples,
processed samples, data imports, data profiles, and DuckDB analytical records.

## Minimal notebook parser

```python
from pathlib import Path

from goodomics import ParserOutput, parser, profile

rnaseq_tpm = profile(
    "user:rnaseq:tpm",
    name="RNA-seq TPM values",
    data_type="feature_matrix",
    producer_tool="lab-notebook",
    feature_type="gene",
    value_type="numeric",
    query_modes=["sample", "feature", "cohort"],
)


@parser(key="lab-rnaseq", label="Lab RNA-seq table", profiles=[rnaseq_tpm])
def parse_rnaseq_table(path: Path, out: ParserOutput) -> None:
    import csv

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        sample_ids = [column for column in reader.fieldnames or [] if column != "gene"]

        for row in reader:
            gene = row["gene"]
            for sample_id in sample_ids:
                out.feature_value(
                    sample_id=sample_id,
                    feature_id=gene,
                    value=float(row[sample_id]),
                    profile=rnaseq_tpm,
                    feature_type="gene",
                    value_semantics="tpm",
                )


result = parse_rnaseq_table.ingest(
    Path("tpm_matrix.csv"),
    project="rnaseq-core",
    assay="bulk_rnaseq",
    run_id="batch-042",
)
```

The decorated function is registered in the current Python process, so this
works naturally in Jupyter notebooks and short scripts. No package, entry point,
or plugin scaffolding is required.

## Emit common record types

The `out` object is the parser's normalized output builder.

```python
out.metric("pct_mapped", 97.2, sample_id="S1")

out.feature_value(
    sample_id="S1",
    feature_id="TP53",
    value=41.5,
    profile="user:rnaseq:tpm",
)

out.feature_call(
    sample_id="S1",
    feature_id="EGFR",
    call_code="AMP",
    profile="cbioportal:copy_number:discrete_calls",
)

out.payload(
    "source_table",
    [{"sample": "S1", "qc_status": "pass"}],
    profile="user:lab:payloads",
)

out.file("results/source.tsv", role="source")
```

Calling `out.metric(...)` without a profile creates a default
`user:<parser-key>:metrics` profile. For richer data, define a profile inline or
reuse a built-in profile ID.

## Profiles

A data profile is the semantic contract for a logical dataset. It says what kind
of data the parser emits and how Goodomics tools should query it.

Use a custom profile when the data shape is specific to your dataset or lab:

```python
from goodomics import profile

gene_tpm = profile(
    "user:rnaseq:tpm",
    name="RNA-seq TPM values",
    data_type="feature_matrix",
    producer_tool="lab-rnaseq",
    feature_type="gene",
    value_type="numeric",
    query_modes=["sample", "feature", "cohort"],
)
```

Reuse a built-in profile ID when your custom parser emits the same semantic
contract as an existing Goodomics parser:

```python
from goodomics.data_profiles import CBIOPORTAL_MUTATIONS_MAF

out.metric("variant_count", 12, sample_id="S1", profile=CBIOPORTAL_MUTATIONS_MAF)
```

## Authoring paths

Start with the notebook path:

```python
@parser(key="my-parser")
def parse_my_data(value, out):
    ...

parse_my_data.ingest(value, run_id="run-1")
```

Move to a normal Python module when the parser should be shared by a team:

```python
from my_lab.parsers import parse_my_data

parse_my_data.ingest("results.tsv", project="demo")
```

Use a packaged source registration only when the parser should be installed and
discovered automatically by Goodomics. Packages can expose a `SourceSpec`
through the `goodomics.sources` entry point group.

## Current boundary

Custom parsers are Python APIs. A parser defined in a notebook is available to
that notebook kernel or Python process. The command-line interface can discover
built-in parsers and installed package entry points, but it cannot discover a
function that only exists inside an active notebook.
