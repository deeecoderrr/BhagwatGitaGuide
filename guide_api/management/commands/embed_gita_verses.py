"""Generate OpenAI embeddings for verses and store them in DB."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from openai import OpenAI

from guide_api.models import Verse


def _embedding_text(verse: Verse) -> str:
    """Create embedding input text from verse content and themes."""
    themes = ", ".join(verse.themes) if verse.themes else "none"
    return (
        f"Chapter {verse.chapter} Verse {verse.verse}\n"
        f"Translation: {verse.translation}\n"
        f"Commentary: {verse.commentary}\n"
        f"Themes: {themes}"
    )


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

    def handle(self, *args, **options):
        """Batch verses through embeddings API and persist vectors."""
        if not settings.OPENAI_API_KEY:
            raise CommandError("OPENAI_API_KEY is not set.")

        limit = options["limit"]
        overwrite = options["overwrite"]
        batch_size = options["batch_size"]
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
            inputs = [_embedding_text(verse) for verse in batch]
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
