"""Prepare and optionally publish a fully canonical production DuckDB snapshot.

Usage:
    python -m v2.prepare_canonical_snapshot
    PUBLISH_CANONICAL_SNAPSHOT=1 python -m v2.prepare_canonical_snapshot

The default is deliberately dry-run with respect to R2 publishing: it downloads the
current snapshot, materialises every full-fidelity raw WhoScored match through the
Metrics Bible, verifies 100% canonical coverage, and prints the report. Publishing
requires the explicit environment flag so an incomplete or accidental local run
cannot overwrite the production object.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .canonical_materialize_all import materialize_all
from .canonical_readiness import assert_canonical_ready, canonical_readiness
from .r2_storage import R2DuckDBStore, validate_duckdb


def prepare_snapshot(*, publish: bool = False, force: bool = False) -> dict[str, object]:
    store = R2DuckDBStore()
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "football.canonical.duckdb"
        store.download_current(snapshot, required=True)
        base = validate_duckdb(snapshot)
        before = canonical_readiness(snapshot)
        materialization = materialize_all(snapshot, force=force)
        after = assert_canonical_ready(snapshot)

        published = False
        if publish:
            store.client.upload_file(store.config.bucket, store.config.current_key, str(snapshot))
            published = True

        return {
            "base": base,
            "before": before,
            "materialization": materialization,
            "after": after,
            "published": published,
            "r2_key": store.config.current_key,
        }


def main() -> None:
    publish = os.environ.get("PUBLISH_CANONICAL_SNAPSHOT", "").strip().lower() in {"1", "true", "yes"}
    force = os.environ.get("FORCE_CANONICAL_REMATERIALIZE", "").strip().lower() in {"1", "true", "yes"}
    report = prepare_snapshot(publish=publish, force=force)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if not publish:
        print("Canonical snapshot verified locally; R2 was not modified. Set PUBLISH_CANONICAL_SNAPSHOT=1 to publish.")


if __name__ == "__main__":
    main()
