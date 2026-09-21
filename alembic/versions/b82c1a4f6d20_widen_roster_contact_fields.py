"""widen roster contact fields

Revision ID: b82c1a4f6d20
Revises: 779fe47e76fd
Create Date: 2026-09-21

The source roster sometimes contains notes or multiple numbers in phone/mobile.
Preserve the source value instead of truncating it.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b82c1a4f6d20"
down_revision: Union[str, Sequence[str], None] = "779fe47e76fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("members") as batch_op:
        batch_op.alter_column(
            "phone",
            existing_type=sa.String(length=40),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "mobile",
            existing_type=sa.String(length=40),
            type_=sa.Text(),
            existing_nullable=True,
        )
    with op.batch_alter_table("member_import_rows") as batch_op:
        batch_op.alter_column(
            "mobile",
            existing_type=sa.String(length=40),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("member_import_rows") as batch_op:
        batch_op.alter_column(
            "mobile",
            existing_type=sa.Text(),
            type_=sa.String(length=40),
            existing_nullable=True,
        )
    with op.batch_alter_table("members") as batch_op:
        batch_op.alter_column(
            "mobile",
            existing_type=sa.Text(),
            type_=sa.String(length=40),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "phone",
            existing_type=sa.Text(),
            type_=sa.String(length=40),
            existing_nullable=True,
        )
