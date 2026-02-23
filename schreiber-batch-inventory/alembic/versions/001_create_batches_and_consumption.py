"""Create batches and consumption_records tables.

Revision ID: 001
Revises:
Create Date: 2026-02-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial tables."""
    # Create batches table
    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_code", sa.String(length=20), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("shelf_life_days", sa.Integer(), nullable=False),
        sa.Column("expiry_date", sa.DateTime(), nullable=False),
        sa.Column("volume_liters", sa.Float(), nullable=False),
        sa.Column("fat_percent", sa.Float(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_code"),
    )

    # Create indexes on batches
    op.create_index("ix_batches_batch_code", "batches", ["batch_code"])
    op.create_index("ix_batches_expiry_date", "batches", ["expiry_date"])
    op.create_index("ix_batches_deleted_at", "batches", ["deleted_at"])
    op.create_index("ix_batches_received_at", "batches", ["received_at"])

    # Create consumption_records table
    op.create_table(
        "consumption_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes on consumption_records
    op.create_index(
        "ix_consumption_records_batch_id", "consumption_records", ["batch_id"]
    )
    op.create_index(
        "ix_consumption_records_order_id", "consumption_records", ["order_id"]
    )
    op.create_index(
        "ix_consumption_records_consumed_at", "consumption_records", ["consumed_at"]
    )


def downgrade() -> None:
    """Drop initial tables."""
    op.drop_index("ix_consumption_records_consumed_at", table_name="consumption_records")
    op.drop_index("ix_consumption_records_order_id", table_name="consumption_records")
    op.drop_index("ix_consumption_records_batch_id", table_name="consumption_records")
    op.drop_table("consumption_records")

    op.drop_index("ix_batches_received_at", table_name="batches")
    op.drop_index("ix_batches_deleted_at", table_name="batches")
    op.drop_index("ix_batches_expiry_date", table_name="batches")
    op.drop_index("ix_batches_batch_code", table_name="batches")
    op.drop_table("batches")
