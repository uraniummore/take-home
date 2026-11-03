"""create payments table

Revision ID: c663831161c6
Revises: 
Create Date: 2026-11-03 08:41:58.189709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c663831161c6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cart_id", sa.UUID, sa.ForeignKey("carts.id"), nullable=False),
        sa.Column("payment_method_id", sa.UUID, sa.ForeignKey("user_payment_methods.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("provider_charge_id", sa.Text, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name="payments_status_check"),
        sa.CheckConstraint("amount > 0", name="payments_amount_check"),
    )

    op.create_index(
        "uq_payments_cart_id_active",
        "payments",
        ["cart_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'succeeded')"),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_cart_id_active")
    op.drop_table("payments")
