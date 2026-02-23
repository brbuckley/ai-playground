"""Add batch_reservations table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create batch_reservations table."""
    op.create_table(
        "batch_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("reserved_qty", sa.Float(), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=True),
        sa.Column("reserved_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_batch_reservations_batch_id",
        "batch_reservations",
        ["batch_id"],
    )
    op.create_index(
        "ix_batch_reservations_released_at",
        "batch_reservations",
        ["released_at"],
    )


def downgrade() -> None:
    """Drop batch_reservations table."""
    op.drop_index("ix_batch_reservations_released_at", table_name="batch_reservations")
    op.drop_index("ix_batch_reservations_batch_id", table_name="batch_reservations")
    op.drop_table("batch_reservations")
