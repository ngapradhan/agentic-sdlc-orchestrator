"""Initial links, analytics and rate-limit storage. Explicit reversible schema."""

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "links",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("destination", sa.String(2048), nullable=False),
        sa.Column("owner_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("permanent", sa.Boolean(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.Column("last_clicked_at", sa.Float(), nullable=True),
    )
    op.create_index("ix_links_owner_hash", "links", ["owner_hash"])
    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), sa.ForeignKey("links.code"), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
    )
    op.create_index("ix_clicks_code", "clicks", ["code"])
    op.create_index("ix_clicks_timestamp", "clicks", ["timestamp"])
    op.create_table(
        "rate_windows",
        sa.Column("principal", sa.String(64), primary_key=True),
        sa.Column("bucket", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rate_windows")
    op.drop_table("clicks")
    op.drop_table("links")
