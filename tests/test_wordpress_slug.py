import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wordpress
from wordpress import build_post_slug, create_draft, find_draft_by_slug


class WordPressSlugTests(unittest.TestCase):
    def test_uses_editorial_title_not_branded_seo_title(self):
        post = SimpleNamespace(
            title="Observación en Casa de Niños",
            seo_title="Observación en Casa de Niños | Asociación Montessori de México",
        )
        self.assertEqual(build_post_slug(post), "observacion-en-casa-de-ninos")

    @patch("wordpress._sync_aioseo")
    @patch("wordpress._resolve_author_id", return_value=9)
    @patch("wordpress._resolve_terms", side_effect=([3], [4]))
    @patch("wordpress.httpx.Client")
    def test_create_draft_http_payload_uses_editorial_slug_and_draft_status(
        self,
        client_class,
        resolve_terms,
        resolve_author,
        sync_aioseo,
    ):
        post = SimpleNamespace(
            title="Observación en Casa de Niños",
            body="<p>Contenido editorial.</p>",
            excerpt="Resumen editorial.",
            categories=["Casa de Niños"],
            tags=["observación"],
            seo_title=(
                "Observación en Casa de Niños | Asociación Montessori de México"
            ),
            seo_description="Descripción editorial.",
        )
        response = Mock(status_code=201)
        response.json.return_value = {"id": 321}
        client = client_class.return_value.__enter__.return_value
        client.post.return_value = response

        with patch.multiple(
            wordpress.config,
            WP_SITE_URL="https://wordpress.example.test",
            WP_USERNAME="test-user",
            WP_APP_PASSWORD="test-password",
        ):
            post_id = create_draft(post, media_id=88, author_name="Roxana Muñoz")

        self.assertEqual(post_id, 321)
        client.post.assert_called_once()
        request_url = client.post.call_args.args[0]
        payload = client.post.call_args.kwargs["json"]
        expected_slug = build_post_slug(post)
        self.assertEqual(request_url, "https://wordpress.example.test/wp-json/wp/v2/posts")
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["slug"], expected_slug)
        self.assertEqual(expected_slug, "observacion-en-casa-de-ninos")
        branded_slug = build_post_slug(SimpleNamespace(title=post.seo_title))
        self.assertNotEqual(payload["slug"], branded_slug)
        sync_aioseo.assert_called_once_with(321, post)

    def test_find_draft_by_slug_requires_matching_featured_media(self):
        response = Mock()
        response.json.return_value = [
            {"id": 320, "slug": "observacion-montessori", "featured_media": 77},
            {"id": 321, "slug": "observacion-montessori", "featured_media": 88},
        ]

        with patch.object(wordpress, "_request", return_value=response) as request:
            self.assertEqual(
                find_draft_by_slug("Observación Montessori", expected_media_id=88),
                321,
            )

        request.assert_called_once_with(
            "get",
            "posts",
            params={
                "slug": "observacion-montessori",
                "status": "draft",
                "context": "edit",
                "per_page": 10,
            },
            retry_on_500=False,
        )

    def test_find_draft_by_slug_does_not_reuse_wrong_featured_media(self):
        response = Mock()
        response.json.return_value = [
            {"id": 320, "slug": "observacion-montessori", "featured_media": 77}
        ]
        with patch.object(wordpress, "_request", return_value=response):
            self.assertIsNone(
                find_draft_by_slug("observacion-montessori", expected_media_id=88)
            )

    def test_find_draft_by_slug_fails_closed_when_wordpress_is_unavailable(self):
        with patch.object(wordpress, "_request", return_value=None):
            with self.assertRaises(wordpress.DraftLookupUnavailable):
                find_draft_by_slug("observacion-montessori", expected_media_id=88)


if __name__ == "__main__":
    unittest.main()
