from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio_main import app  # noqa: E402,F401
from v2.match_metric_leaders import metric_catalog  # noqa: E402
from v2.metric_registry import METRIC_SET_VERSION  # noqa: E402


@app.get('/canonical/metrics')
def canonical_metrics():
    return {
        'metric_set_version': METRIC_SET_VERSION,
        'live': metric_catalog(),
    }
