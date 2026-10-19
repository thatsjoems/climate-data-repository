"""
True/false columns that may not be empty, and the one foreign-key index (migration a1c4e8f2b603).

The model, the migration and the verification script must agree: a column declared NOT NULL in the models and not in the migration would exist in every
test and in no real database (the gap tests/test_schema_parity.py exists for).
"""
import re
from pathlib import Path

from sqlalchemy import inspect

from app.core.database import Base
from tests.conftest import TEST_ENGINE

BACKEND = Path(__file__).resolve().parents[1]
BOOLEANS = {("institutions", "is_active"), ("users", "is_active"), ("submission_records", "is_valid"), ("notifications", "is_read")}
MIGRATION = (BACKEND / "alembic" / "versions" / "a1c4e8f2b603_boolean_columns_not_null_and_one_index.py")


def test_the_models_declare_these_columns_not_null_with_a_default(db_session):
    inspector = inspect(TEST_ENGINE)
    for table, column in BOOLEANS:
        col = next(c for c in inspector.get_columns(table) if c["name"] == column)
        assert col["nullable"] is False, f"{table}.{column} must not allow NULL"
        assert col["default"] is not None, f"{table}.{column} needs a database default"


def test_a_row_without_a_value_gets_the_default_not_null(db_session):
    from app.models.models import Institution, InstitutionType
    db_session.execute(Institution.__table__.insert().values(id="i1", code="X", name="X", type=InstitutionType.BANK.name))
    db_session.commit()
    row = db_session.execute(Institution.__table__.select()).first()
    assert row.is_active is True


def test_the_migration_covers_every_column_and_the_index():
    text = MIGRATION.read_text(encoding="utf-8")
    for table, column in BOOLEANS:
        assert f'("{table}", "{column}",' in text, f"{table}.{column} missing from the migration"
    assert "ix_climate_ingestion_batches_uploaded_by_user" in text
    assert "SET NOT NULL" in text and "WHERE {column} IS NULL" in text   # NULLs are repaired before the column is tightened


def test_the_model_declares_the_index_too(db_session):
    names = {i["name"] for i in inspect(TEST_ENGINE).get_indexes("climate_ingestion_batches")}
    assert "ix_climate_ingestion_batches_uploaded_by_user" in names


def test_the_verification_script_checks_them():
    script = (BACKEND / "scripts" / "verify_db_constraints.py").read_text(encoding="utf-8")
    for table, column in BOOLEANS:
        assert re.search(rf'"{table}": \{{[^}}]*"{column}"', script), f"{table}.{column} not checked by verify_db_constraints.py"
    assert "ix_climate_ingestion_batches_uploaded_by_user" in script
