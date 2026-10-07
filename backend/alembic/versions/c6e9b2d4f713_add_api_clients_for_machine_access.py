"""add the api_clients table: read-only keys for external systems
Revision ID: c6e9b2d4f713
Revises: b5d8a3c6e102

Creates api_clients (see ApiClient in models.py). Only the hash of each key is stored. Four CHECK constraints
(expiry after creation, a non-blank name, a 64-character hash, a revoker only on a revoked key) and two unique
indexes (the public key prefix, and the name among live keys only).

Safe on a database that already holds data: it only adds a table, deletes and rewrites nothing, and is idempotent
(if api_clients already exists it does nothing). The restricted role cdr_app receives the same rights as on every
other table through the default privileges set by database/roles/create_app_role.sql (no DELETE).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c6e9b2d4f713"
down_revision = "b5d8a3c6e102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "api_clients" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "api_clients",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("expires_at > created_at", name="ck_api_clients_expiry_after_creation"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_api_clients_name_not_blank"),
        sa.CheckConstraint("length(key_hash) = 64", name="ck_api_clients_key_hash_length"),
        sa.CheckConstraint("revoked_by_user_id IS NULL OR revoked_at IS NOT NULL", name="ck_api_clients_revoker_needs_revocation"),
    )
    op.create_index("ix_api_clients_created_by_user_id", "api_clients", ["created_by_user_id"], unique=False)
    op.create_index("ix_api_clients_revoked_by_user_id", "api_clients", ["revoked_by_user_id"], unique=False)
    op.create_index("uq_api_clients_key_prefix", "api_clients", ["key_prefix"], unique=True)
    op.create_index(
        "uq_api_clients_active_name", "api_clients", ["name"], unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"), sqlite_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    if "api_clients" in inspect(op.get_bind()).get_table_names():
        op.drop_table("api_clients")
