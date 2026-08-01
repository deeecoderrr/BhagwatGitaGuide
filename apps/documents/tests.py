from django.test import Client, TestCase, override_settings
from django.urls import reverse


class NormalizeTests(TestCase):
    def test_pan(self):
        from apps.extractors.utils.normalize import normalize_pan

        self.assertEqual(normalize_pan("PAN is ABCDE1234F ok"), "ABCDE1234F")


class MarketingPagesTests(TestCase):
    def test_home_ok(self) -> None:
        c = Client()
        r = c.get(reverse("marketing:home"))
        self.assertEqual(r.status_code, 200)

    def test_documents_redirects_when_anonymous(self) -> None:
        c = Client()
        r = c.get(reverse("documents:list"), follow=False)
        self.assertEqual(r.status_code, 302)


class WorkspaceAuthTests(TestCase):
    def test_documents_list_requires_login(self) -> None:
        from django.contrib.auth.models import User

        u = User.objects.create_user("t", "t@test.com", "pwd12345")
        c = Client()
        list_url = reverse("documents:list")
        r = c.get(list_url)
        self.assertEqual(r.status_code, 302)
        c.login(username="t", password="pwd12345")
        self.assertEqual(c.get(list_url).status_code, 200)


class BetaTryTests(TestCase):
    """Homepage ephemeral JSON→PDF when ``ITR_BETA_RELEASE`` is enabled."""

    @override_settings(ITR_BETA_RELEASE=False)
    def test_beta_try_post_disabled_returns_404(self) -> None:
        c = Client(enforce_csrf_checks=False)
        url = reverse("documents:beta_try")
        r = c.post(url, {})
        self.assertEqual(r.status_code, 404)

    @override_settings(ITR_BETA_RELEASE=True)
    def test_beta_try_get_redirects_to_home(self) -> None:
        c = Client()
        url = reverse("documents:beta_try")
        r = c.get(url, follow=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("marketing:home"), r["Location"])


class StaleJsonRetentionTests(TestCase):
    """Stale JSON upload retention (lazy purge on upload)."""

    def setUp(self) -> None:
        from django.core.cache import cache

        from apps.documents.retention import _STALE_JSON_PURGE_CACHE_KEY

        cache.delete(_STALE_JSON_PURGE_CACHE_KEY)

    def _doc(self, *, age_days: int, name: str = "old.json"):
        from datetime import timedelta

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone

        from apps.documents.models import Document

        doc = Document.objects.create(
            uploaded_file=SimpleUploadedFile(name, b'{"ITR":{}}'),
            original_filename=name,
            file_hash="abc",
            status=Document.STATUS_REVIEW_REQUIRED,
            upload_source=Document.UPLOAD_JSON,
        )
        Document.objects.filter(pk=doc.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
        doc.refresh_from_db()
        return doc

    @override_settings(ITR_INPUT_RETENTION_DAYS=7)
    def test_purge_removes_json_older_than_retention(self) -> None:
        from apps.documents.retention import purge_stale_json_uploads

        old = self._doc(age_days=8)
        recent = self._doc(age_days=2, name="new.json")
        n = purge_stale_json_uploads()
        self.assertEqual(n, 1)
        old.refresh_from_db()
        recent.refresh_from_db()
        self.assertFalse(old.uploaded_file)
        self.assertTrue(recent.uploaded_file)

    @override_settings(ITR_INPUT_RETENTION_DAYS=7)
    def test_maybe_purge_runs_at_most_once_per_day(self) -> None:
        from apps.documents.retention import maybe_purge_stale_json_uploads_on_upload

        self._doc(age_days=10)
        first = maybe_purge_stale_json_uploads_on_upload()
        second = maybe_purge_stale_json_uploads_on_upload()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)

    @override_settings(ITR_INPUT_RETENTION_DAYS=7)
    def test_maybe_purge_runs_again_after_cache_expires(self) -> None:
        from django.core.cache import cache

        from apps.documents.retention import (
            _STALE_JSON_PURGE_CACHE_KEY,
            maybe_purge_stale_json_uploads_on_upload,
        )

        self._doc(age_days=10, name="a.json")
        self.assertEqual(maybe_purge_stale_json_uploads_on_upload(), 1)
        cache.delete(_STALE_JSON_PURGE_CACHE_KEY)
        self._doc(age_days=10, name="b.json")
        self.assertEqual(maybe_purge_stale_json_uploads_on_upload(), 1)
