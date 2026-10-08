#!/usr/bin/env python3
"""
Why is a dashboard slow? A READ-ONLY report on the PostgreSQL database: how many loans are stored and how many of them are current and approved (the only
ones a dashboard reads), whether the statistics the query planner relies on are fresh, and the REAL plan and time of the dashboard's main queries.

    docker compose -p cdr-staging -f docker-compose.prod.yml --env-file .env.staging exec backend python scripts/db_diagnose.py

It only reads (EXPLAIN ANALYZE runs each query for real, so run it when the system is quiet). It needs no special rights: the application's own database role is enough.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CURRENT = "s.is_current = true AND s.status = 'APPROVED'"
QUERIES = {
    "summary figures (like the KPI summary)":
        f"SELECT coalesce(sum(r.loan_amount_tzs), 0), coalesce(sum(r.collateral_value_tzs), 0), count(distinct r.customer_id) "
        f"FROM submission_records r JOIN submissions s ON s.id = r.submission_id WHERE {CURRENT}",
    "by region and period (like hazard and combined exposure)":
        f"SELECT r.region, s.reporting_period, sum(r.loan_amount_tzs), sum(r.collateral_value_tzs), count(r.id) "
        f"FROM submission_records r JOIN submissions s ON s.id = r.submission_id WHERE {CURRENT} GROUP BY r.region, s.reporting_period",
}


def plan_verdict(plan_lines):
    """What the plan does with the table of loans, in words, and the time PostgreSQL says it took (ms, or None)."""
    text = "\n".join(plan_lines)
    time_ms = None
    m = re.search(r"Execution Time:\s*([\d.]+)\s*ms", text)
    if m:
        time_ms = float(m.group(1))
    if re.search(r"Seq Scan on submission_records", text):
        what = "reads the WHOLE table of loans (every stored loan, including old versions)"
    elif re.search(r"(Index|Bitmap Index|Bitmap Heap)[^\n]*submission_records", text):
        what = "reaches the loans through an index (only the loans of the submissions it needs)"
    else:
        what = "does something else with the loans (read the plan)"
    return what, time_ms


def legacy_summary_figures(db):
    """The three figures of the summary exactly as the application computed them before (three separate passes; the borrowers with count(distinct))."""
    from sqlalchemy import func
    from app.models.models import SubmissionRecord
    from app.services.analytics_service import _active_records_query
    query = _active_records_query(db, None, filter_institution_id=None, filter_region=None, filter_reporting_period=None)
    loan = query.with_entities(func.coalesce(func.sum(SubmissionRecord.loan_amount_tzs), 0.0)).scalar()
    collateral = query.with_entities(func.coalesce(func.sum(SubmissionRecord.collateral_value_tzs), 0.0)).scalar()
    borrowers = query.filter(SubmissionRecord.customer_id.isnot(None), SubmissionRecord.customer_id != "").with_entities(
        func.count(func.distinct(SubmissionRecord.customer_id))).scalar()
    return float(loan or 0.0), float(collateral or 0.0), int(borrowers or 0)


def new_summary_figures(db):
    from app.services.analytics_service import get_kpi_summary
    k = get_kpi_summary(db)
    return k["total_loan_exposure_tzs"], k["total_collateral_value_tzs"], k["total_borrowers"]


def timed_best_of(function, db, runs=3):
    """The fastest of a few runs (the first reads the table from disk), in milliseconds, and the figures."""
    import time
    best, figures = None, None
    for _ in range(runs):
        started = time.perf_counter()
        figures = function(db)
        db.rollback()                      # a fresh transaction each time, as for each request
        took = (time.perf_counter() - started) * 1000
        best = took if best is None else min(best, took)
    return best, figures


def main() -> int:
    from sqlalchemy import text
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        if db.get_bind().dialect.name != "postgresql":
            print("This report is for PostgreSQL (staging and production).")
            return 2
        one = lambda sql: db.execute(text(sql)).scalar()
        print("== What is stored")
        print(f"  loans stored (all versions of every submission): {one('select count(*) from submission_records'):,}")
        print(f"  loans in CURRENT, APPROVED submissions (what the dashboards read): "
              f"{one(f'select count(*) from submission_records r join submissions s on s.id = r.submission_id where {CURRENT}'):,}")
        for status, current, n in db.execute(text("select status, is_current, count(*) from submissions group by 1, 2 order by 3 desc")).all():
            print(f"  submissions {str(status):<12} current={str(current):<5} {n:>6}")
        size = one("select pg_size_pretty(pg_total_relation_size('submission_records'))")
        print(f"  size of the loans table with its indexes: {size}")
        print("\n== Are the planner's statistics fresh? (n_mod_since_analyze: rows changed since the last ANALYZE)")
        for row in db.execute(text("select relname, n_live_tup, n_dead_tup, n_mod_since_analyze, last_analyze, last_autoanalyze, last_autovacuum "
                                   "from pg_stat_user_tables where relname in ('submission_records', 'submissions') order by relname")).all():
            print(f"  {row[0]}: live {row[1]:,}, dead {row[2]:,}, changed since analyze {row[3]:,}, last analyze {row[4] or '-'}, last auto-analyze {row[5] or '-'}, last auto-vacuum {row[6] or '-'}")
        for name, sql in QUERIES.items():
            print(f"\n== {name}")
            try:
                lines = [r[0] for r in db.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql)).all()]
            except Exception as exc:
                db.rollback()
                print(f"  could not be explained: {type(exc).__name__}")
                continue
            what, ms = plan_verdict(lines)
            print(f"  the plan {what}; PostgreSQL took {ms:.0f} ms" if ms is not None else f"  the plan {what}")
            for line in lines[:28]:
                print("    " + line[:150])
        print("\n== The summary figures as the application computes them, the old way against the new way (the fastest of 3 runs of each)")
        old_ms, old_figures = timed_best_of(legacy_summary_figures, db)
        new_ms, new_figures = timed_best_of(new_summary_figures, db)
        print(f"  old (three passes, count(distinct)): {old_ms:,.0f} ms   {old_figures}")
        print(f"  new (one pass for the totals, DISTINCT list, working memory for the statement): {new_ms:,.0f} ms   {new_figures}")
        print(f"  the same figures: {old_figures == new_figures}   |   the new way takes {new_ms / old_ms * 100:.0f}% of the time of the old" if old_ms else "")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
