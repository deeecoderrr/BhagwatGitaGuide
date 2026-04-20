"""Tests for infrastructure middleware."""

from django.test import Client, TestCase, override_settings

_CANONICAL_TEST_HOSTS = [
    "localhost",
    "127.0.0.1",
    "testserver",
    "example.com",
    "www.example.com",
    "myapp.fly.dev",
    "myapp.onrender.com",
    ".fly.dev",
    ".onrender.com",
]


class CanonicalHostMiddlewareTests(TestCase):
    def test_no_redirect_when_debug(self) -> None:
        c = Client()
        r = c.get("/", HTTP_HOST="localhost")
        self.assertEqual(r.status_code, 200)

    @override_settings(
        DEBUG=False,
        CANONICAL_HOST="example.com",
        ALLOWED_HOSTS=list(_CANONICAL_TEST_HOSTS),
    )
    def test_redirects_www_to_apex(self) -> None:
        c = Client()
        r = c.get("/pricing/", HTTP_HOST="www.example.com")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].startswith("https://example.com/"))

    @override_settings(
        DEBUG=False,
        CANONICAL_HOST="example.com",
        ALLOWED_HOSTS=list(_CANONICAL_TEST_HOSTS),
    )
    def test_redirects_fly_dev_platform_host(self) -> None:
        c = Client()
        r = c.get("/", HTTP_HOST="myapp.fly.dev")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].startswith("https://example.com/"))

    @override_settings(
        DEBUG=False,
        CANONICAL_HOST="example.com",
        ALLOWED_HOSTS=list(_CANONICAL_TEST_HOSTS),
    )
    def test_redirects_onrender_platform_host(self) -> None:
        c = Client()
        r = c.get("/", HTTP_HOST="myapp.onrender.com")
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].startswith("https://example.com/"))

    @override_settings(
        DEBUG=False,
        CANONICAL_HOST="example.com",
        ALLOWED_HOSTS=list(_CANONICAL_TEST_HOSTS),
    )
    def test_no_redirect_when_host_matches_canonical(self) -> None:
        c = Client()
        r = c.get("/", HTTP_HOST="example.com")
        self.assertEqual(r.status_code, 200)
