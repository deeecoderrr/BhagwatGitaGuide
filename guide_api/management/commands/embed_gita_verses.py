"""Generate OpenAI embeddings for verses and store them in DB."""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from openai import OpenAI

from guide_api.models import Verse
from guide_api.services import verse_embedding_document


class Command(BaseCommand):
    """Management command to generate embeddings in batches."""

    help = "Generate and store embeddings for Bhagavad Gita verses."

    def add_arguments(self, parser):
        """Define limit/overwrite/batch-size options for embedding job."""
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum number of verses to embed (0 = all).",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Recompute embeddings for verses that already have one.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Embedding batch size for API calls.",
        )
        parser.add_argument(
            "--sync-pgvector",
            action="store_true",
            help=(
                "After generating embeddings, sync them into pgvector table "
                "(PostgreSQL only)."
            ),
        )

    def handle(self, *args, **options):
        """Batch verses through embeddings API and persist vectors."""
        if not settings.OPENAI_API_KEY:
            raise CommandError("OPENAI_API_KEY is not set.")

        limit = options["limit"]
        overwrite = options["overwrite"]
        batch_size = options["batch_size"]
        sync_pgvector = options["sync_pgvector"]
        model = settings.OPENAI_EMBEDDING_MODEL

        queryset = Verse.objects.all().order_by("chapter", "verse")
        if not overwrite:
            queryset = queryset.filter(embedding=[])
        if limit > 0:
            queryset = queryset[:limit]

        verses = list(queryset)
        if not verses:
            self.stdout.write(self.style.SUCCESS("No verses to embed."))
            return

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        updated = 0

        for start in range(0, len(verses), batch_size):
            batch = verses[start: start + batch_size]
            inputs = [verse_embedding_document(verse) for verse in batch]
            response = client.embeddings.create(model=model, input=inputs)
            embeddings = [item.embedding for item in response.data]

            for verse, embedding in zip(batch, embeddings):
                verse.embedding = embedding
                updated += 1

            Verse.objects.bulk_update(batch, ["embedding"])
            completed = min(start + batch_size, len(verses))
            self.stdout.write(
                f"Embedded {completed}/{len(verses)}",
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Embedding complete. updated={updated} model={model}",
            )
        )
        if sync_pgvector:
            call_command("sync_pgvector_embeddings")
