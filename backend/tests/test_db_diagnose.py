"""
scripts/db_diagnose.py (a read-only report for slow dashboards). Only its plan reader can be tested without PostgreSQL: it must tell a plan that
reads the whole table of loans from one that goes through an index, and find the time PostgreSQL measured.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("db_diagnose_tool", Path(__file__).resolve().parent.parent / "scripts" / "db_diagnose.py")
dd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dd)


def test_a_plan_that_scans_every_loan_is_called_so():
    what, ms = dd.plan_verdict(["Aggregate", "  ->  Hash Join", "        ->  Seq Scan on submission_records r  (rows=600000)", "Execution Time: 812.345 ms"])
    assert "WHOLE table" in what and ms == 812.345


def test_a_plan_that_uses_an_index_is_called_so():
    what, ms = dd.plan_verdict(["Aggregate", "  ->  Nested Loop", "        ->  Index Scan using ix_submission_records_submission_loan on submission_records r",
                                "Execution Time: 95.1 ms"])
    assert "index" in what and ms == 95.1


def test_a_bitmap_scan_counts_as_an_index():
    what, _ = dd.plan_verdict(["  ->  Bitmap Heap Scan on submission_records r", "        ->  Bitmap Index Scan on ix_submission_records_submission_loan"])
    assert "index" in what


def test_an_unknown_plan_or_none_does_not_fail():
    assert dd.plan_verdict([]) == ("does something else with the loans (read the plan)", None)
    assert dd.plan_verdict(["Result", "Execution Time: 0.050 ms"])[1] == 0.05
