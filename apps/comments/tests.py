from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from apps.comments.models import Comment


class CommentsHomeTests(TestCase):
    def test_home_includes_comments_section(self) -> None:
        c = Client()
        r = c.get(reverse("marketing:home"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="comments-home')

    def test_post_requires_login(self) -> None:
        c = Client()
        r = c.post(
            reverse("comments:post"),
            {"body": "hello", "page_slug": Comment.PAGE_HOME},
        )
        self.assertEqual(r.status_code, 302)

    def test_post_creates_comment(self) -> None:
        u = User.objects.create_user("commenter", "c@test.com", "pwd1234567890123456789")
        c = Client()
        self.assertTrue(c.login(username="commenter", password="pwd1234567890123456789"))
        r = c.post(
            reverse("comments:post"),
            {"body": "First note", "page_slug": Comment.PAGE_HOME},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.endswith("?comments=open"))
        self.assertEqual(Comment.objects.filter(page_slug=Comment.PAGE_HOME).count(), 1)
