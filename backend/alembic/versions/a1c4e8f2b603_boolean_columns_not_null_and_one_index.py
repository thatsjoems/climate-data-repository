"""true/false columns may no longer be empty, and one missing foreign-key index
Revision ID: a1c4e8f2b603
Revises: f3a7c1e5b829

Four true/false columns allowed NULL, a third answer that means nothing: institutions.is_active, users.is_active, submission_records.is_valid and
notifications.is_read. Every row the application writes carries a value, so no row is expected to change; to be safe, any NULL is first set to the
column's own default (active, valid, unread), then the column is made NOT NULL with a default. Also adds the index on
climate_ingestion_batches.uploaded_by_user_id (the only foreign key without one).

Nothing is deleted. On PostgreSQL, SET NOT NULL scans the table once and holds a short lock: negligible now, and the reason to do it while
submission_records is small. SQLite (the tests) is built from the models and is only given the data fix and the index. Idempotent.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "a1c4e8f2b603"
down_revision = "f3a7c1e5b829"
branch_labels = None
depends_on = None

BOOLEANS = [
    ("institutions", "is_active", True),
    ("users", "is_active", True),
    ("submission_records", "is_valid", True),
    ("notifications", "is_read", False),
]
INDEX = ("ix_climate_ingestion_batches_uploaded_by_user", "climate_ingestion_batches", ["uploaded_by_user_id"])


def upgrade() -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column, default in BOOLEANS:
        if table not in tables or column not in {c["name"] for c in inspector.get_columns(table)}:
            continue
        literal = ("TRUE" if default else "FALSE") if postgres else ("1" if default else "0")
        op.execute(f"UPDATE {table} SET {column} = {literal} WHERE {column} IS NULL")
        if postgres:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {literal}")
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")
    name, table, columns = INDEX
    if table in tables and name not in {i["name"] for i in inspector.get_indexes(table)}:
        op.create_index(name, table, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    name, table, _ = INDEX
    if table in tables and name in {i["name"] for i in inspector.get_indexes(table)}:
        op.drop_index(name, table_name=table)
    if bind.dialect.name == "postgresql":
        for table, column, _ in BOOLEANS:
            if table in tables:
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
