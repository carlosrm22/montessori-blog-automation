import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import wordpress
from wordpress import build_post_slug, create_draft


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


if __name__ == "__main__":
    unittest.main()
