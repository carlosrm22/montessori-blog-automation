import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import config
import manual_image_queue as queue
import resume_manual_image
from content import GeneratedPost


def _post() -> GeneratedPost:
    return GeneratedPost(
        title="Lenguaje Montessori en el ambiente preparado",
        body="<p>Contenido completo.</p>",
        excerpt="Aplicaciones prácticas del lenguaje Montessori.",
        categories=["Lenguaje"],
        tags=["lenguaje", "Montessori"],
        seo_title="Lenguaje Montessori | AMMAC",
        seo_description="Lenguaje Montessori aplicado al ambiente preparado.",
        focus_keyphrase="lenguaje Montessori",
        og_title="Lenguaje Montessori",
        og_description="Lenguaje Montessori aplicado al ambiente preparado.",
        twitter_title="Lenguaje Montessori",
        twitter_description="Lenguaje Montessori aplicado al ambiente preparado.",
        social_image_source="featured_media",
        image_prompt="Montessori language materials in a prepared classroom",
        image_alt_text="Materiales de lenguaje Montessori en el ambiente",
        conversion_intent="casa",
        commercial_relevance="medium",
    )


def _enqueue() -> dict:
    return queue.enqueue_manual_image(
        kind="article",
        source_url="https://source.example.test/language",
        source_title="Language source",
        source_score=0.87,
        topic_id="language",
        terminal_status="published_draft",
        topic_name="Lenguaje",
        author_name="Roxana Muñoz",
        brand_id="ammac",
        post=_post(),
        truseo_score=84,
        headline_score=79,
        conversion_intent="casa",
        commercial_relevance="medium",
        destination_url="https://certificacionmontessori.com/diplomados/casa-de-ninos/",
    )


class ResumeManualImageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.queue_patch = patch.object(
            config,
            "MANUAL_IMAGE_QUEUE_DIR",
            Path(self.tempdir.name) / "queue",
        )
        self.queue_patch.start()
        self.addCleanup(self.queue_patch.stop)

    def _place_image(self, job_id: str) -> Path:
        path = queue.expected_input_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1600, 900), (180, 150, 110)).save(path, "PNG")
        return path

    def test_resume_creates_featured_draft_marks_state_and_archives_job(self):
        job = _enqueue()
        image = self._place_image(job["job_id"])

        with (
            patch.object(resume_manual_image, "upload_media", return_value=77) as upload,
            patch.object(resume_manual_image, "find_draft_by_slug", return_value=None),
            patch.object(resume_manual_image, "create_draft", return_value=123) as draft,
            patch.object(resume_manual_image.state, "mark_processed") as marked,
            patch.object(resume_manual_image, "notify_draft_created") as notified,
        ):
            post_id = resume_manual_image.resume_manual_job(job_id=job["job_id"])

        self.assertEqual(post_id, 123)
        self.assertFalse(image.exists())
        self.assertEqual(queue.pending_job_ids(), [])
        completed = queue.completed_dir() / job["job_id"]
        self.assertTrue((completed / "cover.jpg").is_file())
        self.assertTrue(any(path.name.startswith("original") for path in completed.iterdir()))
        self.assertEqual(upload.call_args.kwargs["alt_text"], _post().image_alt_text)
        self.assertEqual(draft.call_args.kwargs["media_id"], 77)
        self.assertEqual(marked.call_args.kwargs["status"], "published_draft")
        notified.assert_called_once()

    def test_uploaded_media_can_resume_without_input_image(self):
        job = _enqueue()
        queue.update_job_progress(
            job["job_id"], status="image_prepared", input_name=f"{job['job_id']}.png"
        )
        queue.update_job_progress(job["job_id"], status="media_uploaded", media_id=77)

        with (
            patch.object(resume_manual_image, "upload_media") as upload,
            patch.object(resume_manual_image, "find_draft_by_slug", return_value=None),
            patch.object(resume_manual_image, "create_draft", return_value=124),
            patch.object(resume_manual_image.state, "mark_processed"),
            patch.object(resume_manual_image, "notify_draft_created"),
        ):
            post_id = resume_manual_image.resume_manual_job(job_id=job["job_id"])

        self.assertEqual(post_id, 124)
        upload.assert_not_called()
        self.assertEqual(queue.pending_job_ids(), [])

    def test_existing_matching_draft_is_reused_after_interruption(self):
        job = _enqueue()
        queue.update_job_progress(
            job["job_id"], status="image_prepared", input_name=f"{job['job_id']}.png"
        )
        queue.update_job_progress(job["job_id"], status="media_uploaded", media_id=77)

        with (
            patch.object(resume_manual_image, "upload_media") as upload,
            patch.object(resume_manual_image, "find_draft_by_slug", return_value=125) as find,
            patch.object(resume_manual_image, "create_draft") as draft,
            patch.object(resume_manual_image.state, "mark_processed"),
            patch.object(resume_manual_image, "notify_draft_created"),
        ):
            post_id = resume_manual_image.resume_manual_job(job_id=job["job_id"])

        self.assertEqual(post_id, 125)
        upload.assert_not_called()
        draft.assert_not_called()
        self.assertEqual(find.call_args.kwargs["expected_media_id"], 77)

    def test_unavailable_draft_lookup_fails_closed_before_create(self):
        job = _enqueue()
        queue.update_job_progress(
            job["job_id"], status="image_prepared", input_name=f"{job['job_id']}.png"
        )
        queue.update_job_progress(job["job_id"], status="media_uploaded", media_id=77)

        with (
            patch.object(
                resume_manual_image,
                "find_draft_by_slug",
                side_effect=resume_manual_image.DraftLookupUnavailable("offline"),
            ),
            patch.object(resume_manual_image, "create_draft") as draft,
            patch.object(resume_manual_image.state, "mark_processed") as marked,
        ):
            with self.assertRaises(resume_manual_image.ManualResumeError):
                resume_manual_image.resume_manual_job(job_id=job["job_id"])

        draft.assert_not_called()
        marked.assert_not_called()
        self.assertEqual(queue.load_pending_job(job["job_id"])["status"], "media_uploaded")

    def test_upload_failure_keeps_prepared_job_retryable(self):
        job = _enqueue()
        image = self._place_image(job["job_id"])

        with (
            patch.object(resume_manual_image, "upload_media", return_value=None),
            patch.object(resume_manual_image, "create_draft") as draft,
            patch.object(resume_manual_image.state, "mark_processed") as marked,
        ):
            with self.assertRaises(resume_manual_image.ManualResumeError):
                resume_manual_image.resume_manual_job(job_id=job["job_id"])

        self.assertTrue(image.exists())
        pending = queue.load_pending_job(job["job_id"])
        self.assertEqual(pending["status"], "image_prepared")
        self.assertTrue((queue.job_directory(job["job_id"]) / "cover.jpg").is_file())
        draft.assert_not_called()
        marked.assert_not_called()

    def test_retry_cleans_recorded_inbox_image_after_upload_recovers(self):
        job = _enqueue()
        image = self._place_image(job["job_id"])

        with patch.object(resume_manual_image, "upload_media", return_value=None):
            with self.assertRaises(resume_manual_image.ManualResumeError):
                resume_manual_image.resume_manual_job(job_id=job["job_id"])

        self.assertTrue(image.exists())
        with (
            patch.object(resume_manual_image, "upload_media", return_value=77),
            patch.object(resume_manual_image, "find_draft_by_slug", return_value=None),
            patch.object(resume_manual_image, "create_draft", return_value=126),
            patch.object(resume_manual_image.state, "mark_processed"),
            patch.object(resume_manual_image, "notify_draft_created"),
        ):
            post_id = resume_manual_image.resume_manual_job(job_id=job["job_id"])

        self.assertEqual(post_id, 126)
        self.assertFalse(image.exists())

    def test_if_ready_without_pending_job_is_a_successful_noop(self):
        self.assertIsNone(resume_manual_image.resume_manual_job(if_ready=True))

    def test_invalid_image_fails_before_wordpress(self):
        job = _enqueue()
        image = queue.expected_input_path(job["job_id"])
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_text("invalid", encoding="utf-8")

        with (
            patch.object(resume_manual_image, "upload_media") as upload,
            patch.object(resume_manual_image, "create_draft") as draft,
        ):
            with self.assertRaises(resume_manual_image.ManualResumeError):
                resume_manual_image.resume_manual_job(job_id=job["job_id"])

        upload.assert_not_called()
        draft.assert_not_called()
        self.assertEqual(queue.load_pending_job(job["job_id"])["status"], "waiting_image")


if __name__ == "__main__":
    unittest.main()
