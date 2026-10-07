"""an optional list of allowed addresses for each API key
Revision ID: e9b3c7a1d5f2
Revises: d7f1a3c5e824

Adds api_clients.allowed_networks (NULL = the key works from any address, exactly as before) and one CHECK constraint
(ck_api_clients_allowed_networks_not_blank: a list is either absent or not blank). Deletes and rewrites nothing; every
existing key keeps working from anywhere. Idempotent: a column or constraint that already exists is skipped.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "e9b3c7a1d5f2"
down_revision = "d7f1a3c5e824"
branch_labels = None
depends_on = None

CHECK = ("api_clients", "ck_api_clients_allowed_networks_not_blank", "allowed_networks IS NULL OR length(trim(allowed_networks)) > 0")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "api_clients" not in inspector.get_table_names():
        return
    if "allowed_networks" not in {c["name"] for c in inspector.get_columns("api_clients")}:
        if bind.dialect.name == "postgresql":
            op.execute("ALTER TABLE api_clients ADD COLUMN allowed_networks VARCHAR(500)")
        else:
            with op.batch_alter_table("api_clients") as batch_op:
                batch_op.add_column(sa.Column("allowed_networks", sa.String(length=500), nullable=True))
    inspector = inspect(bind)
    table, name, condition = CHECK
    if name not in {c["name"] for c in inspector.get_check_constraints(table)}:
        if bind.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")
        else:
            with op.batch_alter_table(table) as batch_op:
                batch_op.create_check_constraint(name, condition)


def downgrade() -> None:
    bind = op.get_bind()
    if "api_clients" not in inspect(bind).get_table_names():
        return
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE api_clients DROP CONSTRAINT IF EXISTS {CHECK[1]}")
        op.execute("ALTER TABLE api_clients DROP COLUMN IF EXISTS allowed_networks")
    else:
        with op.batch_alter_table("api_clients") as batch_op:
            try:
                batch_op.drop_constraint(CHECK[1], type_="check")
            except Exception:
                pass
            batch_op.drop_column("allowed_networks")
