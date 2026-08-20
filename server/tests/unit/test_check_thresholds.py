"""Unit tests for eval.check_thresholds. Pure I/O against tmp_path, no network."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval.check_thresholds import find_breaches, load_metrics, load_thresholds, main

_REPORT = {
    "object_id": "siemens-dishwasher",
    "metrics": {"recall_at_5": 0.9, "keyword_hit": 0.8, "refusal_accuracy": 0.96},
}
_THRESHOLDS = "recall_at_5: 0.85\nrefusal_accuracy: 0.95\n"


def _write_report(tmp_path: Path, metrics: dict[str, float]) -> Path:
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"object_id": "x", "metrics": metrics}), encoding="utf-8")
    return path


def _write_thresholds(tmp_path: Path, content: str = _THRESHOLDS) -> Path:
    path = tmp_path / "thresholds.yaml"
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------- load_metrics


def test_load_metrics_reads_the_metrics_object(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_REPORT), encoding="utf-8")

    metrics = load_metrics(report)

    assert metrics == {"recall_at_5": 0.9, "keyword_hit": 0.8, "refusal_accuracy": 0.96}


def test_load_metrics_rejects_report_with_no_metrics_key(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"object_id": "x"}), encoding="utf-8")

    with pytest.raises(ValueError, match="metrics"):
        load_metrics(report)


# ------------------------------------------------------------------ load_thresholds


def test_load_thresholds_parses_flat_mapping(tmp_path: Path) -> None:
    path = _write_thresholds(tmp_path)

    thresholds = load_thresholds(path)

    assert thresholds == {"recall_at_5": 0.85, "refusal_accuracy": 0.95}


def test_load_thresholds_rejects_non_mapping(tmp_path: Path) -> None:
    path = _write_thresholds(tmp_path, "- 1\n- 2\n")

    with pytest.raises(ValueError, match="mapping"):
        load_thresholds(path)


# -------------------------------------------------------------------- find_breaches


def test_find_breaches_empty_when_all_metrics_meet_threshold() -> None:
    breaches = find_breaches({"recall_at_5": 0.9}, {"recall_at_5": 0.85})
    assert breaches == []


def test_find_breaches_reports_metric_below_threshold() -> None:
    breaches = find_breaches({"recall_at_5": 0.5}, {"recall_at_5": 0.85})
    assert len(breaches) == 1
    assert "recall_at_5" in breaches[0]


def test_find_breaches_reports_missing_metric_as_a_breach() -> None:
    breaches = find_breaches({"keyword_hit": 0.9}, {"recall_at_5": 0.85})
    assert len(breaches) == 1
    assert "no such metric" in breaches[0]


# --------------------------------------------------------------------------- main()


def test_main_exits_zero_when_thresholds_are_met(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _write_report(tmp_path, {"recall_at_5": 0.9, "refusal_accuracy": 0.96})
    thresholds = _write_thresholds(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_thresholds.py", str(report), str(thresholds)])

    main()  # must not raise / exit


def test_main_exits_nonzero_when_a_threshold_is_breached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _write_report(tmp_path, {"recall_at_5": 0.5, "refusal_accuracy": 0.96})
    thresholds = _write_thresholds(tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_thresholds.py", str(report), str(thresholds)])

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0


def test_cli_matches_the_positional_invocation_used_in_eval_yml(tmp_path: Path) -> None:
    """`.github/workflows/eval.yml` calls this as `check_thresholds.py <report> <thresholds>`."""
    report = _write_report(tmp_path, {"recall_at_5": 0.5, "refusal_accuracy": 0.96})
    thresholds = _write_thresholds(tmp_path)
    script = Path(__file__).resolve().parents[2] / "eval" / "check_thresholds.py"

    result = subprocess.run(
        [sys.executable, str(script), str(report), str(thresholds)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "recall_at_5" in result.stderr
