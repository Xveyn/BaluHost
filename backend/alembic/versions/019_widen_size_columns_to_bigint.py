"""Widen file/VCL/upload size columns to BigInteger

Files > 2 GB cause psycopg2.errors.NumericValueOutOfRange because
PostgreSQL INTEGER max = 2,147,483,647 (~2.1 GB).
This widens all size_bytes-style columns that were still INTEGER.

PostgreSQL can ALTER COLUMN ... TYPE BIGINT in-place (metadata-only
change for int->bigint), so this is safe and fast on production data.

Revision ID: 019_size_bigint
Revises: 018_seq_perms
Create Date: 2026-02-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '019_size_bigint'
down_revision: Union[str, None] = '018_seq_perms'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs to widen from INTEGER to BIGINT
_COLUMNS = [
    ("file_metadata", "size_bytes"),
    ("version_blobs", "original_size"),
    ("version_blobs", "compressed_size"),
    ("vcl_file_versions", "file_size"),
    ("vcl_file_versions", "compressed_size"),
    ("chunked_uploads", "total_size"),
    ("chunked_uploads", "uploaded_bytes"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
