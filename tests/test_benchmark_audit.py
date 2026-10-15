"""Unit tests for the benchmark metric auditor."""

import json
import pathlib

import pytest
from evaluation.validate_benchmark_metrics import (
    Discrepancy,
    _float_equal,
    audit_chunking_benchmark,
    audit_context_optimization_benchmark,
    audit_standard_benchmark,
    run_full_benchmark_audit,
)


def test_float_equal():
    assert _float_equal(0.76229166, 0.76229167)
    assert not _float_equal(0.7622, 0.7625, tol=1e-4)
    assert _float_equal(None, None)
    assert not _float_equal(0.5, None)
    assert not _float_equal(None, 0.5)


def test_discrepancy_materiality():
    d_immaterial = Discrepancy("test.json", "mrr", 0.762291, 0.762292, tolerance=1e-4)
    assert not d_immaterial.is_material()

    d_material = Discrepancy("test.json", "mrr", 0.7622, 0.7722, tolerance=1e-4)
    assert d_material.is_material()

    d_string = Discrepancy("test.json", "label", "expected", "actual")
    assert d_string.is_material()


def test_audit_baseline_passes():
    path = pathlib.Path("benchmarks/kip_v1_2_expanded_baseline_20261014_112147.json")
    if not path.exists():
        pytest.skip("Baseline artifact not present")
    report = audit_standard_benchmark(path, expected_count=80)
    assert report.passed
    assert report.case_count == 80
    assert abs(report.recomputed_mrr - 0.7622916) < 1e-4
    assert abs(report.recomputed_hit1 - 0.6875) < 1e-4
    assert abs(report.recomputed_hit5 - 0.8750) < 1e-4


def test_audit_chunking_passes_and_checks_multi_concept():
    path = pathlib.Path("benchmarks/kip_v1_2_chunking_treatment_20261014_124804.json")
    if not path.exists():
        pytest.skip("Chunking artifact not present")
    rep_raw, rep_dedup = audit_chunking_benchmark(path, expected_count=80)
    assert rep_raw.passed
    assert rep_dedup.passed
    assert abs(rep_raw.recomputed_mrr - 0.7300) < 1e-4
    assert abs(rep_dedup.recomputed_mrr - 0.74708) < 1e-4
    assert abs(rep_dedup.recomputed_hit5 - 0.9125) < 1e-4


def test_audit_context_optimization_passes():
    path = pathlib.Path(
        "benchmarks/kip_v1_2_context_optimization_treatment_20261015_062231.json"
    )
    if not path.exists():
        pytest.skip("Context optimization artifact not present")
    reports = audit_context_optimization_benchmark(path, expected_count=80)
    assert len(reports) == 3
    for r in reports:
        assert r.passed

    # Standard treatment checks
    treatment_rep = reports[1]
    assert abs(treatment_rep.recomputed_mrr - 0.754166) < 1e-4
    assert abs(treatment_rep.recomputed_hit5 - 0.8375) < 1e-4


def test_audit_detects_material_discrepancy():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_artifact = pathlib.Path(tmp_dir) / "fake_artifact.json"
        fake_data = {
            "mean_reciprocal_rank": 0.9999,  # Falsified
            "hit_rate_at_1": 0.5,
            "hit_rate_at_3": 0.5,
            "hit_rate_at_5": 0.5,
            "labelled_cases": 2,
            "case_results": [
                {
                    "case_id": "c1",
                    "retrieval": {
                        "expected_count": 1,
                        "reciprocal_rank": 0.5,
                        "hit_at_1": False,
                        "hit_at_3": True,
                        "hit": True,
                    },
                },
                {
                    "case_id": "c2",
                    "retrieval": {
                        "expected_count": 1,
                        "reciprocal_rank": 0.5,
                        "hit_at_1": False,
                        "hit_at_3": True,
                        "hit": True,
                    },
                },
            ],
        }
        fake_artifact.write_text(json.dumps(fake_data), encoding="utf-8")

        report = audit_standard_benchmark(fake_artifact, expected_count=2)
        assert not report.passed
        assert any(d.field_name == "mean_reciprocal_rank" for d in report.discrepancies)


def test_audit_detects_case_count_mismatch():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_artifact = pathlib.Path(tmp_dir) / "fake_count.json"
        fake_data = {
            "mean_reciprocal_rank": 1.0,
            "case_results": [
                {"case_id": "c1", "retrieval": {"reciprocal_rank": 1.0, "hit": True}}
            ],
        }
        fake_artifact.write_text(json.dumps(fake_data), encoding="utf-8")
        report = audit_standard_benchmark(fake_artifact, expected_count=80)
        assert not report.passed
        assert any(d.field_name == "total_case_count" for d in report.discrepancies)


def test_run_full_benchmark_audit():
    benchmarks_dir = pathlib.Path("benchmarks")
    all_passed, reports = run_full_benchmark_audit(benchmarks_dir)
    assert all_passed
    assert len(reports) >= 7
