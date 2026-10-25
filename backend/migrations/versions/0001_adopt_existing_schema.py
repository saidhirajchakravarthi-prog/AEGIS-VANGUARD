"""Adopt existing SQLite workspaces and create missing Aegis tables.

Revision ID: 0001_adopt
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from main import Base, BrandRuleModel, RuleRevisionModel, DEFAULT_RULES, record_rule_revision

revision = "0001_adopt"
down_revision = None
branch_labels = None
depends_on = None


def _backfill_rules(bind) -> None:
    with Session(bind=bind) as db:
        if db.scalar(select(func.count()).select_from(BrandRuleModel)) == 0:
            db.add_all(BrandRuleModel(**rule) for rule in DEFAULT_RULES)
            db.flush()
        rules_without_history = list(db.scalars(
            select(BrandRuleModel).where(
                ~BrandRuleModel.id.in_(select(RuleRevisionModel.rule_id))
            )
        ))
        for rule in rules_without_history:
            record_rule_revision(db, rule, "Aegis system")
        db.flush()


def upgrade() -> None:
    # One-time bridge from the pre-Alembic schema. Future changes must use
    # explicit, immutable revisions rather than changing this adoption step.
    bind = op.get_bind()
    baseline_tables = [
        table for table in Base.metadata.sorted_tables
        if table.name != "governance_learning_runs"
    ]
    existing = set(sa.inspect(bind).get_table_names())
    if not existing:
        Base.metadata.create_all(bind=bind, tables=baseline_tables)
        _backfill_rules(bind)
        return

    Base.metadata.create_all(bind=bind, tables=baseline_tables, checkfirst=True)
    legacy_columns = {
        "analysis_runs": {
            "failure_code": sa.Column("failure_code", sa.String(length=40), nullable=True),
            "evidence_version": sa.Column(
                "evidence_version", sa.Integer(), nullable=False, server_default="0"
            ),
        },
        "findings": {
            "policy_id": sa.Column("policy_id", sa.Integer(), nullable=True),
        },
    }
    inspector = sa.inspect(bind)
    for table_name, columns in legacy_columns.items():
        if table_name not in inspector.get_table_names():
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column in columns.items():
            if column_name not in existing_columns:
                op.add_column(table_name, column)
    _backfill_rules(bind)


def downgrade() -> None:
    # This baseline may adopt user data and cannot safely be reversed.
    pass
