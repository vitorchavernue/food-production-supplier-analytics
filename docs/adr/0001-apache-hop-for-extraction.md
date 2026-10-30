# ADR 0001 — Apache Hop for the extraction, SQL for the business rules

**Status:** accepted

## Context

The source is an Oracle ERP and the target a PostgreSQL warehouse on another server. The plants' IT team knows
Pentaho Data Integration (Kettle) from older projects, but the free Community Edition is no longer distributed
openly. The load has to be incremental, repeatable and easy to review.

Options considered:

1. **Pentaho Data Integration.** Familiar, but the downloads now require a commercial or academic account.
2. **Python scripts moving the data.** Flexible, but every connection, type mapping and bulk insert is hand-written,
   and the operators cannot follow the flow visually.
3. **Apache Hop.** Started as a fork of Kettle, Apache 2.0 licence, same concepts (pipelines, workflows, transforms),
   plain XML files that diff well in Git, and a command line (`hop-run`) for scheduling and CI. Chosen.

## Decision

- **Hop moves the data:** one pipeline per ERP table (`hop/pipelines/extract_*.hpl`): read the watermark from the
  warehouse, read the changed rows from Oracle, light cleaning (CNPJ digits, trimmed text), write to `stg.*`.
- **SQL holds the business rules:** the workflow runs the files in `sql/dml` in order (dimensions, facts and rejects,
  quality checks). Rules stay in one language, readable by anyone who knows SQL and covered by unit tests.
- **The workflow is the run:** `hop/workflows/load_warehouse.hwf` opens the run, extracts, loads, checks, evaluates
  the gate and closes or fails the run. The same file runs in the Hop GUI, on a server and in CI.
- **Connections hold only variables.** Host, user and password come from a Hop environment created at run time.

## Consequences

- An operator can open the workflow in the Hop GUI and see where a run stopped.
- Transform-level logic (lookups, joins) is avoided on purpose; if a rule must move into Hop later, the SQL file and
  its unit test show exactly what it has to do.
- Hop needs Java 17 and the Oracle JDBC driver (`ojdbc11.jar`), installed in CI from the official Apache and Maven
  Central releases.
