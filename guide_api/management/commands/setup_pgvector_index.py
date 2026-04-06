"""Create pgvector extension and ANN index table for verse embeddings."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    """Initialize pgvector extension/table/index on Postgres."""

    help = (
        "Create pgvector extension, verse embedding index table, and ivfflat "
        "index. Safe to run multiple times."
    )

    def handle(self, *args, **options):
        """Run idempotent SQL setup for pgvector retrieval infrastructure."""
        if connection.vendor != "postgresql":
            raise CommandError("setup_pgvector_index requires PostgreSQL.")

        table_name = str(getattr(settings, "PGVECTOR_TABLE", "")).strip()
        dim = int(getattr(settings, "PGVECTOR_EMBEDDING_DIM", 1536))
        if not table_name:
            raise CommandError("PGVECTOR_TABLE is empty.")
        if dim <= 0:
            raise CommandError("PGVECTOR_EMBEDDING_DIM must be positive.")

        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    verse_id BIGINT PRIMARY KEY
                        REFERENCES guide_api_verse(id)
                        ON DELETE CASCADE,
                    embedding vector({dim}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {table_name}_embedding_ivfflat_idx
                ON {table_name}
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )

        self.stdout.write(
            self.style.SUCCESS(
                "pgvector index setup complete "
                f"(table={table_name}, dim={dim})"
            )
        )

