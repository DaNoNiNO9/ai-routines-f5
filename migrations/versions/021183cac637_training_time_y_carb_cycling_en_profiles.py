"""training_time y carb cycling en profiles

Revision ID: 021183cac637
Revises: 196ae6a460b6
Create Date: 2026-09-09 11:40:00

Hand-edited after autogenerate:
- server defaults so the columns can be added to tables that already hold rows;
- the enum CHECK is created explicitly (a plain String column plus
  ``create_check_constraint``) instead of relying on ``sa.Enum`` inside batch
  mode, which on SQLite produced a duplicated, unnamed constraint that then
  blocked the downgrade.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "021183cac637"
down_revision = "196ae6a460b6"
branch_labels = None
depends_on = None

TRAINING_TIME_VALUES = "training_time IN ('none', 'morning', 'midday', 'evening')"


def upgrade():
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "training_time", sa.String(length=32), nullable=False, server_default="none"
            )
        )
        batch_op.add_column(
            sa.Column(
                "wants_carb_cycling", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        # The naming convention turns this into ck_profiles_trainingtime.
        batch_op.create_check_constraint("trainingtime", TRAINING_TIME_VALUES)


def downgrade():
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.drop_constraint("trainingtime", type_="check")
        batch_op.drop_column("wants_carb_cycling")
        batch_op.drop_column("training_time")
