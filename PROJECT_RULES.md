# LUFCData Analysis App — Project Rules

## Rule 1: Metrics Bible is the sole statistical authority

Every football statistic, metric, definition, label, calculation, aggregation, ranking, comparison and derived value shown by the Analysis App must come from the project's Metrics Bible and the canonical backend data that implements it.

- Do not invent replacement metrics.
- Do not approximate a missing metric from unrelated fields.
- Do not substitute convenient frontend calculations for Metrics Bible definitions.
- Do not silently fall back to legacy/statistically different fields.
- If a required Metrics Bible metric is not available through an API response, treat that as a backend/API wiring defect to fix, not a reason to create a frontend substitute.
- UI labels and formatting may change presentation, but must not change the underlying metric meaning.

## Rule 2: Backend data already exists — wire it through

The default assumption is that the canonical football data exists in the backend/DuckDB/R2 pipeline. When the UI is empty or incomplete, investigate the complete path:

canonical data -> Metrics Bible definition -> backend query -> API response -> frontend adapter/types -> latest UI component.

Do not solve missing UI data by fabricating new data sources or parallel statistical logic.

## Rule 3: Latest UI only

All product work must target the current/latest LUFCData frontend and its active components/routes. Before changing UI code, verify that the file/component being edited is actually used by the deployed frontend.

Do not spend implementation effort patching abandoned, legacy, duplicate or superseded UI paths merely because they still exist in the repository.

## Rule 4: Live deployment is the acceptance test

A green commit, passing test, successful build or successful Render deploy is not proof that a feature works.

Before declaring a fix complete, verify the live production path that the user actually uses:

1. Confirm the intended commit is deployed to the correct Render service.
2. Confirm the live backend endpoint returns the required canonical data.
3. Confirm the live frontend is configured to call that backend.
4. Confirm the latest UI consumes and renders the returned fields.
5. Confirm the user-visible production page is populated correctly.

If any step cannot be verified, report exactly which step remains unverified. Never say a fix is complete merely because code was pushed or CI/deployment is green.

## Rule 5: Diagnose from evidence, not assumptions

For empty panels, missing players, missing metrics, missing top performers, missing match stats or missing match logs, identify the first broken boundary in the live chain before changing code.

Useful evidence includes live API responses, Render application logs, deployed commit IDs, environment configuration, browser/network responses, and the actual latest UI source path.

## Rule 6: Preserve architecture and avoid regressions

Changes should be minimal and traceable. Preserve working routes and existing canonical data contracts unless the Metrics Bible requires a deliberate contract change. When a contract changes, update backend, API schema/adapters, frontend types and UI consumption together.

## Definition of Done

A statistical feature is done only when the latest production UI displays the correct Metrics Bible-defined values from the canonical backend through the live deployed API, with the relevant production path verified end-to-end.

This document is the standing implementation rule for future work on this repository. When another instruction conflicts with these rules, stop and resolve the conflict explicitly rather than silently bypassing them.
