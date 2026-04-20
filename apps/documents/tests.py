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
