import inspect
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import config
import main
import notifier
import run_cuadernillos
from content import GeneratedPost
from conversion_funnel import resolve_conversion_decision
from cuadernillo_source import Cuadernillo
from search import SearchResult
from topics import TopicProfile
from wordpress import build_post_slug


def _post() -> GeneratedPost:
    return GeneratedPost(
        title="Observación en Casa de Niños",
        body="<p>Cuerpo inicial.</p><p>Segundo párrafo.</p>",
        excerpt="Una guía práctica para observar el ambiente.",
        categories=["Original"],
        tags=["observación", "Montessori"],
        seo_title=(
            "Observación en Casa de Niños | Asociación Montessori de México"
        ),
        seo_description="Cómo observar y acompañar un ambiente Montessori.",
        focus_keyphrase="observación Montessori",
        og_title="Observación en Casa de Niños",
        og_description="Una mirada práctica a la observación Montessori.",
        twitter_title="Observación en Casa de Niños",
        twitter_description="Una mirada práctica a la observación Montessori.",
        social_image_source="featured_media",
        image_prompt="Editorial classroom photograph",
        image_alt_text="Guía observando un ambiente Montessori",
        conversion_intent="casa",
        commercial_relevance="medium",
    )


def _topic() -> TopicProfile:
    return TopicProfile(
        topic_id="casa",
        name="Casa de Niños",
        author_name="Roxana Muñoz",
        brand_kit="ammac",
        queries=["observación Montessori"],
        categories=["Casa de Niños"],
        min_score=0.5,
        post_template="post_prompt.txt",
        scoring_guidelines="",
        writing_guidelines="",
    )


def _cuadernillo() -> Cuadernillo:
    return Cuadernillo(
        materia_id="observacion",
        materia_name="Observación",
        session_n=3,
        slug="observacion-casa-ninos",
        topic_label="Observación en Casa de Niños",
        source_text="La observación orienta la preparación del ambiente.",
        author_name="Roxana Muñoz",
        tone_file="",
        brand_kit="ammac",
        categories=["Casa de Niños"],
    )


def _score_report():
    return SimpleNamespace(score=90, to_dict=lambda: {"score": 90})


def _config_patch():
    return patch.multiple(
        config,
        QUALITY_RECENT_POSTS_COUNT=6,
        RECENT_POSTS_GALLERY_COUNT=2,
        TITLE_SIMILARITY_MAX=0.82,
        CERTIFICATION_SITE_URL="https://certificacionmontessori.com",
        CONVERSION_CTA_ENABLED=True,
        PREFERRED_EXTERNAL_LINKS=[],
        PREFERRED_EXTERNAL_LINK_EVERY=0,
        LOCAL_SEO_RULES_ENABLED=True,
        TRUSEO_MIN_SCORE=70,
        HEADLINE_MIN_SCORE=65,
        POST_TITLE_MAX_LEN=60,
        SEO_STRICT_PHRASE=False,
        WP_SITE_DOMAIN="montessorimexico.org",
        WP_SITE_URL="https://montessorimexico.org",
        DRY_RUN=False,
        NOTIFICATIONS_ENABLED=True,
        NOTIFY_WEBHOOK_URL="https://hooks.example.test/draft",
        TELEGRAM_BOT_TOKEN="",
        TELEGRAM_CHAT_ID="",
    )


class E5PipelineIntegrationTests(unittest.TestCase):
    def test_main_accepted_flow_reuses_recent_posts_and_records_failed_notification(self):
        article = SearchResult(
            title="Fuente editorial",
            url="https://source.example.test/article",
            snippet="Resumen",
        )
        post = _post()
        recent = [
            {"title": "Matemáticas con materiales", "url": "https://blog.test/1"},
            {"title": "El ambiente preparado", "url": "https://blog.test/2"},
            {"title": "Lenguaje y movimiento", "url": "https://blog.test/3"},
        ]
        expected_slug = build_post_slug(post)
        events = []

        def strip_body(html):
            events.append("strip")
            return f"{html}|stripped", 1

        def sanitize_body(**kwargs):
            events.append("sanitize")
            self.assertEqual(kwargs["recent_posts"], recent[:2])
            self.assertTrue(kwargs["html"].endswith("|stripped"))
            return f'{kwargs["html"]}|sanitized', {}

        def apply_funnel(html, decision):
            events.append("apply")
            self.assertEqual(decision.post_slug, expected_slug)
            self.assertIn(f"utm_content={expected_slug}", decision.attributed_url)
            self.assertTrue(html.endswith("|sanitized"))
            return f"{html}|funnel", {}

        def create_draft(post_arg, **kwargs):
            events.append("draft")
            self.assertEqual(build_post_slug(post_arg), expected_slug)
            self.assertTrue(post_arg.body.endswith("|funnel"))
            return 123

        def mark_processed(*args, **kwargs):
            events.append(f'mark:{kwargs["status"]}')

        def fail_delivery(*args, **kwargs):
            events.append("notify_failed")
            return False

        with ExitStack() as stack:
            stack.enter_context(_config_patch())
            dotenv = stack.enter_context(patch("dotenv.load_dotenv"))
            stack.enter_context(patch.object(main, "search_all", return_value=[article]))
            stack.enter_context(
                patch.object(main, "select_best", return_value=(article, 0.91))
            )
            stack.enter_context(patch.object(main, "enrich_article", return_value=article))
            stack.enter_context(patch.object(main, "generate_post", return_value=post))
            recent_fetch = stack.enter_context(
                patch.object(main, "list_recent_published_posts", return_value=recent)
            )
            decision = stack.enter_context(
                patch.object(
                    main,
                    "resolve_conversion_decision",
                    wraps=resolve_conversion_decision,
                )
            )
            stack.enter_context(
                patch.object(
                    main, "strip_uncontrolled_commercial_links", side_effect=strip_body
                )
            )
            stack.enter_context(
                patch.object(main, "sanitize_and_enrich_body", side_effect=sanitize_body)
            )
            stack.enter_context(
                patch.object(main, "apply_conversion_funnel", side_effect=apply_funnel)
            )
            truseo = stack.enter_context(
                patch.object(
                    main,
                    "analyze_truseo",
                    return_value={"overall": _score_report()},
                )
            )
            stack.enter_context(
                patch.object(main, "analyze_headline", return_value=_score_report())
            )
            stack.enter_context(patch.object(main.state, "save_seo_report"))
            stack.enter_context(
                patch.object(
                    main,
                    "generate_cover_image",
                    side_effect=lambda *args, **kwargs: (
                        events.append("image") or Path("/tmp/e5-cover.jpg")
                    ),
                )
            )
            stack.enter_context(
                patch.object(
                    main,
                    "upload_media",
                    side_effect=lambda *args, **kwargs: events.append("upload") or 77,
                )
            )
            stack.enter_context(
                patch.object(main, "create_draft", side_effect=create_draft)
            )
            stack.enter_context(
                patch.object(main.state, "mark_processed", side_effect=mark_processed)
            )
            delivery = stack.enter_context(
                patch.object(notifier, "_post_json", side_effect=fail_delivery)
            )

            result = main.run_topic_pipeline(_topic())

        self.assertTrue(result)
        dotenv.assert_not_called()
        recent_fetch.assert_called_once_with(limit=6)
        decision.assert_called_once_with(
            "casa", "medium", expected_slug, post.title
        )
        self.assertEqual(truseo.call_args.kwargs["slug"], expected_slug)
        delivery.assert_called_once()
        self.assertEqual(
            events,
            [
                "strip",
                "sanitize",
                "apply",
                "image",
                "upload",
                "draft",
                "mark:published_draft",
                "notify_failed",
            ],
        )

    def test_cuadernillo_accepted_flow_reuses_recent_posts_and_records_failed_notification(self):
        item = _cuadernillo()
        post = _post()
        recent = [
            {"title": "Matemáticas con materiales", "url": "https://blog.test/1"},
            {"title": "El ambiente preparado", "url": "https://blog.test/2"},
            {"title": "Lenguaje y movimiento", "url": "https://blog.test/3"},
        ]
        expected_slug = build_post_slug(post)
        events = []

        def strip_body(html):
            events.append("strip")
            return f"{html}|stripped", 1

        def sanitize_body(**kwargs):
            events.append("sanitize")
            self.assertEqual(kwargs["recent_posts"], recent[:2])
            self.assertTrue(kwargs["html"].endswith("|stripped"))
            return f'{kwargs["html"]}|sanitized', {}

        def apply_funnel(html, decision):
            events.append("apply")
            self.assertEqual(decision.post_slug, expected_slug)
            self.assertIn(f"utm_content={expected_slug}", decision.attributed_url)
            self.assertTrue(html.endswith("|sanitized"))
            return f"{html}|funnel", {}

        def create_draft(post_arg, **kwargs):
            events.append("draft")
            self.assertEqual(build_post_slug(post_arg), expected_slug)
            self.assertTrue(post_arg.body.endswith("|funnel"))
            return 124

        def mark_processed(*args, **kwargs):
            events.append(f'mark:{kwargs["status"]}')

        def fail_delivery(*args, **kwargs):
            events.append("notify_failed")
            return False

        with ExitStack() as stack:
            stack.enter_context(_config_patch())
            dotenv = stack.enter_context(patch("dotenv.load_dotenv"))
            stack.enter_context(
                patch.object(run_cuadernillos, "generate_post", return_value=post)
            )
            recent_fetch = stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "list_recent_published_posts",
                    return_value=recent,
                )
            )
            decision = stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "resolve_conversion_decision",
                    wraps=resolve_conversion_decision,
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "strip_uncontrolled_commercial_links",
                    side_effect=strip_body,
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "sanitize_and_enrich_body",
                    side_effect=sanitize_body,
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "apply_conversion_funnel",
                    side_effect=apply_funnel,
                )
            )
            truseo = stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "analyze_truseo",
                    return_value={"overall": _score_report()},
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "analyze_headline",
                    return_value=_score_report(),
                )
            )
            stack.enter_context(
                patch.object(run_cuadernillos.state, "save_seo_report")
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "generate_cover_image",
                    side_effect=lambda *args, **kwargs: (
                        events.append("image") or Path("/tmp/e5-cover.jpg")
                    ),
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "upload_media",
                    side_effect=lambda *args, **kwargs: events.append("upload") or 78,
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos, "create_draft", side_effect=create_draft
                )
            )
            stack.enter_context(
                patch.object(
                    run_cuadernillos.state,
                    "mark_processed",
                    side_effect=mark_processed,
                )
            )
            delivery = stack.enter_context(
                patch.object(notifier, "_post_json", side_effect=fail_delivery)
            )

            result = run_cuadernillos._process_one(item, dry_run=False)

        self.assertTrue(result)
        dotenv.assert_not_called()
        recent_fetch.assert_called_once_with(limit=6)
        decision.assert_called_once_with(
            "casa", "medium", expected_slug, post.title
        )
        self.assertEqual(truseo.call_args.kwargs["slug"], expected_slug)
        delivery.assert_called_once()
        self.assertEqual(
            events,
            [
                "strip",
                "sanitize",
                "apply",
                "image",
                "upload",
                "draft",
                f"mark:{run_cuadernillos.STATUS_DRAFT}",
                "notify_failed",
            ],
        )

    def test_main_novelty_rejection_stops_before_side_effects(self):
        article = SearchResult(
            title="Fuente editorial",
            url="https://source.example.test/article",
            snippet="Resumen",
        )
        post = _post()
        forbidden_names = (
            "strip_uncontrolled_commercial_links",
            "sanitize_and_enrich_body",
            "apply_conversion_funnel",
            "generate_cover_image",
            "upload_media",
            "create_draft",
            "notify_draft_created",
        )
        with ExitStack() as stack:
            stack.enter_context(_config_patch())
            dotenv = stack.enter_context(patch("dotenv.load_dotenv"))
            stack.enter_context(patch.object(main, "search_all", return_value=[article]))
            stack.enter_context(
                patch.object(main, "select_best", return_value=(article, 0.91))
            )
            stack.enter_context(patch.object(main, "enrich_article", return_value=article))
            stack.enter_context(patch.object(main, "generate_post", return_value=post))
            recent_fetch = stack.enter_context(
                patch.object(
                    main,
                    "list_recent_published_posts",
                    return_value=[{"title": post.title}],
                )
            )
            forbidden = {
                name: stack.enter_context(patch.object(main, name))
                for name in forbidden_names
            }
            marked = stack.enter_context(patch.object(main.state, "mark_processed"))

            result = main.run_topic_pipeline(_topic())

        self.assertFalse(result)
        dotenv.assert_not_called()
        recent_fetch.assert_called_once_with(limit=6)
        for mocked in forbidden.values():
            mocked.assert_not_called()
        self.assertEqual(marked.call_args.kwargs["status"], "quality_failed")

    def test_cuadernillo_novelty_rejection_stops_before_side_effects(self):
        item = _cuadernillo()
        post = _post()
        forbidden_names = (
            "strip_uncontrolled_commercial_links",
            "sanitize_and_enrich_body",
            "apply_conversion_funnel",
            "generate_cover_image",
            "upload_media",
            "create_draft",
            "notify_draft_created",
        )
        with ExitStack() as stack:
            stack.enter_context(_config_patch())
            dotenv = stack.enter_context(patch("dotenv.load_dotenv"))
            stack.enter_context(
                patch.object(run_cuadernillos, "generate_post", return_value=post)
            )
            recent_fetch = stack.enter_context(
                patch.object(
                    run_cuadernillos,
                    "list_recent_published_posts",
                    return_value=[{"title": post.title}],
                )
            )
            forbidden = {
                name: stack.enter_context(patch.object(run_cuadernillos, name))
                for name in forbidden_names
            }
            marked = stack.enter_context(
                patch.object(run_cuadernillos.state, "mark_processed")
            )

            result = run_cuadernillos._process_one(item, dry_run=False)

        self.assertFalse(result)
        dotenv.assert_not_called()
        recent_fetch.assert_called_once_with(limit=6)
        for mocked in forbidden.values():
            mocked.assert_not_called()
        self.assertEqual(marked.call_args.kwargs["status"], "cuad_quality_failed")

    def test_draft_runners_have_no_indexnow_path(self):
        runner_source = "\n".join(
            (inspect.getsource(main), inspect.getsource(run_cuadernillos))
        ).lower()
        self.assertNotIn("indexnow", runner_source)


if __name__ == "__main__":
    unittest.main()
