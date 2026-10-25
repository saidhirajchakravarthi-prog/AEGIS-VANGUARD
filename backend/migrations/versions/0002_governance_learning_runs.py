"""Persist governance learning snapshots and their traceable decision basis.

Revision ID: 0002_learning
Revises: 0001_adopt
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_learning"
down_revision = "0001_adopt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_learning_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("window_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("basis_json", sa.Text(), nullable=False),
        sa.Column("recommendations_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Governance learning snapshots are audit records; downgrade would destroy them.")
