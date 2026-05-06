"""037_add_webinar_variants

Support running A/B tests where two webinars share the same user-facing
`number` but live on different WebinarGeek accounts. Adds:

- `connector_credentials.name` so a single provider (e.g. webinargeek) can
  hold multiple credentials, picked per webinar variant. Existing rows
  backfill to 'default'; the (provider, name) pair becomes the new unique key.

- `webinars.variant_label` (free-text — operator names variants like
  "Account A" / "WG-Skarpe") and `webinars.webinargeek_credential_id`
  (FK → connector_credentials.id) so each variant points at its own
  WebinarGeek account.

- Two partial unique indexes on `webinars` instead of the old single-column
  unique on (user_id, number):
    - one row per number with NULL variant_label (preserves existing rows)
    - any number of variants per number when variant_label is NOT NULL,
      labels unique within a number

Revision ID: 037
Revises: 036
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── connector_credentials.name ───────────────────────────────────────
    # Add nullable first so the backfill can set it, then enforce NOT NULL.
    op.add_column(
        "connector_credentials",
        sa.Column("name", sa.Text(), nullable=True),
    )
    op.execute("UPDATE connector_credentials SET name = 'default' WHERE name IS NULL")
    op.alter_column("connector_credentials", "name", nullable=False, server_default="default")
    # Replace the single-column unique on `provider` with (provider, name).
    op.drop_constraint("connector_credentials_provider_key", "connector_credentials", type_="unique")
    op.create_unique_constraint(
        "uq_connector_credentials_provider_name",
        "connector_credentials",
        ["provider", "name"],
    )

    # ── webinars.variant_label + webinargeek_credential_id ───────────────
    op.add_column(
        "webinars",
        sa.Column("variant_label", sa.Text(), nullable=True),
    )
    op.add_column(
        "webinars",
        sa.Column(
            "webinargeek_credential_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("connector_credentials.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_webinars_wg_credential",
        "webinars",
        ["webinargeek_credential_id"],
    )

    # Replace the old (user_id, number) unique with two partial indexes:
    #   - exactly one row per number with NULL variant_label  (preserves
    #     all existing webinars; they'll keep variant_label = NULL)
    #   - any number of variants per number when label is NOT NULL,
    #     labels unique within a number
    op.drop_constraint("uq_webinars_user_number", "webinars", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_webinars_user_number_no_variant
            ON webinars (user_id, number)
            WHERE variant_label IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_webinars_user_number_variant
            ON webinars (user_id, number, variant_label)
            WHERE variant_label IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_webinars_user_number_variant")
    op.execute("DROP INDEX IF EXISTS uq_webinars_user_number_no_variant")
    op.create_unique_constraint(
        "uq_webinars_user_number",
        "webinars",
        ["user_id", "number"],
    )
    op.drop_index("ix_webinars_wg_credential", table_name="webinars")
    op.drop_column("webinars", "webinargeek_credential_id")
    op.drop_column("webinars", "variant_label")

    op.drop_constraint(
        "uq_connector_credentials_provider_name",
        "connector_credentials",
        type_="unique",
    )
    op.create_unique_constraint(
        "connector_credentials_provider_key",
        "connector_credentials",
        ["provider"],
    )
    op.drop_column("connector_credentials", "name")
