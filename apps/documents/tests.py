from django.test import Client, TestCase
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
