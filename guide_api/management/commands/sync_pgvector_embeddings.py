"""Sync Verse.embedding JSON vectors into pgvector index table."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from guide_api.models import Verse


def _to_pgvector_literal(vector: list[float]) -> str:
    """Convert Python float vector to pgvector literal representation."""
    return "[" + ",".join(f"{float(value):.8f}" for value in vector) + "]"


class Command(BaseCommand):
    """Upsert verse embeddings into pgvector index table."""

    help = (
        "Copy Verse.embedding vectors into pgvector table for fast semantic "
        "retrieval."
    )

    def add_arguments(self, parser):
        """Define optional limit and overwrite controls."""
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of verse rows to sync (0 = all).",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete existing rows from pgvector index table before sync.",
        )

    def handle(self, *args, **options):
        """Validate environment and sync embedding rows into pgvector index."""
        if connection.vendor != "postgresql":
            raise CommandError("sync_pgvector_embeddings requires PostgreSQL.")

        table_name = str(getattr(settings, "PGVECTOR_TABLE", "")).strip()
        dim = int(getattr(settings, "PGVECTOR_EMBEDDING_DIM", 1536))
        if not table_name:
            raise CommandError("PGVECTOR_TABLE is empty.")

        limit = int(options["limit"])
        truncate = bool(options["truncate"])

        queryset = Verse.objects.exclude(embedding=[]).order_by("chapter", "verse")
        if limit > 0:
            queryset = queryset[:limit]
        verses = list(queryset)
        if not verses:
            self.stdout.write(self.style.WARNING("No verse embeddings to sync."))
            return

        synced = 0
        skipped = 0

        with connection.cursor() as cursor:
            if truncate:
                cursor.execute(f"TRUNCATE TABLE {table_name}")

            for verse in verses:
                embedding = verse.embedding if isinstance(verse.embedding, list) else []
                if len(embedding) != dim:
                    skipped += 1
                    continue

                vector_literal = _to_pgvector_literal(embedding)
                cursor.execute(
                    f"""
                    INSERT INTO {table_name} (verse_id, embedding, updated_at)
                    VALUES (%s, %s::vector, NOW())
                    ON CONFLICT (verse_id)
                    DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """,
                    [verse.id, vector_literal],
                )
                synced += 1

        self.stdout.write(
            self.style.SUCCESS(
                "pgvector sync complete "
                f"(synced={synced}, skipped={skipped}, table={table_name})"
            )
        )

