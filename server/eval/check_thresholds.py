"""CLI: `python check_thresholds.py <report.json> <thresholds.yaml>`.

Compares an eval report's aggregate metrics against `thresholds.yaml` and
exits non-zero if any configured threshold is breached. Invoked as a plain
script (see `.github/workflows/eval.yml`), not `python -m`, so this module
deliberately imports nothing from `app` or `eval.schema` — only the
standard library and PyYAML, both resolvable regardless of `sys.path[0]`.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml


def load_metrics(report_path: Path) -> dict[str, float]:
    """Read the `metrics` object out of a report written by `run_eval.py`."""
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    metrics = raw.get("metrics") if isinstance(raw, dict) else None
    if not isinstance(metrics, dict):
        raise ValueError(
            f"{report_path} has no top-level 'metrics' object — "
            "is this an eval report produced by run_eval.py?"
        )
    return {str(name): float(value) for name, value in metrics.items()}


def load_thresholds(thresholds_path: Path) -> dict[str, float]:
    """Read `thresholds.yaml`: a flat mapping of metric name -> minimum value."""
    raw = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"{thresholds_path} must contain a YAML mapping of "
            f"metric name -> minimum value, got {type(raw).__name__}."
        )
    thresholds: dict[str, float] = {}
    for name, value in raw.items():
        if not isinstance(value, int | float):
            raise ValueError(
                f"{thresholds_path}: threshold {name!r} must be a number, got {value!r}."
            )
        thresholds[str(name)] = float(value)
    return thresholds


def find_breaches(metrics: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    """Return one message per breached threshold; empty means everything passed.

    A threshold naming a metric the report doesn't have is itself a breach
    — a gate that silently no-ops is worse than one that fails loudly.
    """
    breaches: list[str] = []
    for name, minimum in thresholds.items():
        if name not in metrics:
            breaches.append(f"{name}: no such metric in the report (required >= {minimum:.3f})")
        elif metrics[name] < minimum:
            breaches.append(f"{name}: {metrics[name]:.3f} < {minimum:.3f}")
    return breaches


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exit non-zero if an eval report breaches thresholds.yaml."
    )
    parser.add_argument("report", type=Path, help="Path to the JSON report written by run_eval.py.")
    parser.add_argument("thresholds", type=Path, help="Path to thresholds.yaml.")
    args = parser.parse_args()

    metrics = load_metrics(args.report)
    thresholds = load_thresholds(args.thresholds)
    breaches = find_breaches(metrics, thresholds)

    for name, value in sorted(metrics.items()):
        gate = f" (gate: >= {thresholds[name]:.3f})" if name in thresholds else ""
        print(f"{name}: {value:.3f}{gate}")

    if breaches:
        print("\nTHRESHOLD BREACH:", file=sys.stderr)
        for breach in breaches:
            print(f"  - {breach}", file=sys.stderr)
        raise SystemExit(1)

    print("\nAll thresholds met.")


if __name__ == "__main__":
    main()
