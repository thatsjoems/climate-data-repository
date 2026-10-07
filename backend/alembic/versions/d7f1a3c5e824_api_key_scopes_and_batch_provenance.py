"""API key scopes, and which key delivered a climate batch
Revision ID: d7f1a3c5e824
Revises: c6e9b2d4f713

Adds two columns and two CHECK constraints; deletes and rewrites nothing.

    api_clients.scope                                  READ (every existing key keeps reading) | INGEST_TMA | INGEST_PMO
    ck_api_clients_scope_valid                         scope is one of those three
    climate_ingestion_batches.uploaded_by_api_client_id  which key delivered the batch (NULL for every existing batch)
    ck_climate_ingestion_batches_one_uploader          a batch has a person or a key as uploader, never both

Both constraints hold for every existing row (the new columns are READ / NULL), so they are validated at once.
Idempotent: a column or constraint that already exists (by name) is skipped.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "d7f1a3c5e824"
down_revision = "c6e9b2d4f713"
branch_labels = None
depends_on = None

SCOPE_CHECK = ("api_clients", "ck_api_clients_scope_valid", "scope IN ('READ', 'INGEST_TMA', 'INGEST_PMO')")
UPLOADER_CHECK = ("climate_ingestion_batches", "ck_climate_ingestion_batches_one_uploader",
                  "uploaded_by_user_id IS NULL OR uploaded_by_api_client_id IS NULL")


def _columns(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)}


def _add_check(bind, inspector, table, name, condition):
    if name in {c["name"] for c in inspector.get_check_constraints(table)}:
        return
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")
    else:
        with op.batch_alter_table(table) as batch_op:
            batch_op.create_check_constraint(name, condition)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "api_clients" not in tables or "climate_ingestion_batches" not in tables:
        return

    if "scope" not in _columns(inspector, "api_clients"):
        if bind.dialect.name == "postgresql":
            op.execute("ALTER TABLE api_clients ADD COLUMN scope VARCHAR(20) NOT NULL DEFAULT 'READ'")
        else:
            with op.batch_alter_table("api_clients") as batch_op:
                batch_op.add_column(sa.Column("scope", sa.String(length=20), nullable=False, server_default="READ"))

    if "uploaded_by_api_client_id" not in _columns(inspector, "climate_ingestion_batches"):
        if bind.dialect.name == "postgresql":
            op.execute("ALTER TABLE climate_ingestion_batches ADD COLUMN uploaded_by_api_client_id VARCHAR REFERENCES api_clients(id)")
        else:
            with op.batch_alter_table("climate_ingestion_batches") as batch_op:
                batch_op.add_column(sa.Column("uploaded_by_api_client_id", sa.String(), sa.ForeignKey("api_clients.id"), nullable=True))
        op.create_index("ix_climate_ingestion_batches_uploaded_by_api_client_id", "climate_ingestion_batches", ["uploaded_by_api_client_id"], unique=False)

    inspector = inspect(bind)
    _add_check(bind, inspector, *SCOPE_CHECK)
    _add_check(bind, inspector, *UPLOADER_CHECK)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "climate_ingestion_batches" in tables:
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE climate_ingestion_batches DROP CONSTRAINT IF EXISTS {UPLOADER_CHECK[1]}")
            op.execute("DROP INDEX IF EXISTS ix_climate_ingestion_batches_uploaded_by_api_client_id")
            op.execute("ALTER TABLE climate_ingestion_batches DROP COLUMN IF EXISTS uploaded_by_api_client_id")
        else:
            with op.batch_alter_table("climate_ingestion_batches") as batch_op:
                try:
                    batch_op.drop_constraint(UPLOADER_CHECK[1], type_="check")
                except Exception:
                    pass
                batch_op.drop_column("uploaded_by_api_client_id")
    if "api_clients" in tables:
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE api_clients DROP CONSTRAINT IF EXISTS {SCOPE_CHECK[1]}")
            op.execute("ALTER TABLE api_clients DROP COLUMN IF EXISTS scope")
        else:
            with op.batch_alter_table("api_clients") as batch_op:
                try:
                    batch_op.drop_constraint(SCOPE_CHECK[1], type_="check")
                except Exception:
                    pass
                batch_op.drop_column("scope")
