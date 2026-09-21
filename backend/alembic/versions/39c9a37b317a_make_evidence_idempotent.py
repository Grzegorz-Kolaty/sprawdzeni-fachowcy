"""make evidence idempotent

Revision ID: 39c9a37b317a
Revises: 234845c28809
Create Date: 2026-09-21 08:13:06.180739
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39c9a37b317a"
down_revision: str | Sequence[str] | None = "234845c28809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column(
            "last_observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # W bazie istnieją już powtórzone obserwacje tego samego faktu.
    # Zostawiamy rekord o najwyższym ID, czyli najnowszy.
    op.execute(
        """
        DELETE FROM evidence AS older
            USING evidence AS newer
        WHERE older.id < newer.id
          AND older.company_id = newer.company_id
          AND older.source_id = newer.source_id
          AND older.evidence_type = newer.evidence_type
          AND older.normalized_value
            IS NOT DISTINCT FROM newer.normalized_value
        """
    )

    op.create_unique_constraint(
        "uq_evidence_company_source_type_value",
        "evidence",
        [
            "company_id",
            "source_id",
            "evidence_type",
            "normalized_value",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_evidence_company_source_type_value",
        "evidence",
        type_="unique",
    )

    op.drop_column(
        "evidence",
        "last_observed_at",
    )
