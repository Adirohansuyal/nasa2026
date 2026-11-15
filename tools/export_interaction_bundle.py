"""Export the integrated interaction analysis CSV for the static HTML dashboard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import INTERACTION_RESULTS  # noqa: E402

OUT = ROOT / "assets" / "interaction_data.js"
COLUMNS = [
    "variable_x", "variable_y", "lag_months", "sample_size", "spearman_rho",
    "p_value", "fdr_q_value", "fdr_significant",
]


def main() -> None:
    frame = pd.read_csv(INTERACTION_RESULTS)
    missing = sorted(set(COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Interaction results are missing columns: {', '.join(missing)}")
    frame = frame[COLUMNS].copy()
    frame["fdr_significant"] = frame["fdr_significant"].astype(bool)
    records = frame.replace({np.nan: None}).to_dict(orient="records")
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    OUT.write_text(f"window.INTERACTION_DATA={payload};\n", encoding="utf-8")
    print(f"Exported {len(records)} actual interaction rows to {OUT}")


if __name__ == "__main__":
    main()
