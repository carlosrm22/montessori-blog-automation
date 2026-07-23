import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import config
import manual_image_queue as queue
from content import GeneratedPost
from image_gen import InvalidCoverImage, prepare_manual_cover_image


def _post() -> GeneratedPost:
    return GeneratedPost(
        title="Observación Montessori y ambiente preparado",
        body="<p>Contenido editorial.</p>",
        excerpt="Una guía breve para observar el ambiente.",
        categories=["Educación Montessori"],
        tags=["observación", "ambiente"],
        seo_title="Observación Montessori | AMMAC",
        seo_description="Observación Montessori aplicada al ambiente preparado.",
        focus_keyphrase="observación Montessori",
        og_title="Observación Montessori",
        og_description="Observación Montessori aplicada al ambiente preparado.",
        twitter_title="Observación Montessori",
        twitter_description="Observación Montessori aplicada al ambiente preparado.",
        social_image_source="featured_media",
        image_prompt="A Montessori guide observing a prepared classroom",
        image_alt_text="Guía Montessori observando un ambiente preparado",
        conversion_intent="casa",
        commercial_relevance="medium",
    )


def _enqueue() -> dict:
    return queue.enqueue_manual_image(
        kind="article",
        source_url="https://source.example.test/article",
        source_title="Fuente editorial",
        source_score=0.91,
        topic_id="casa",
        terminal_status="published_draft",
        topic_name="Casa de Niños",
        author_name="Roxana Muñoz",
        brand_id="ammac",
        post=_post(),
        truseo_score=88,
        headline_score=81,
        conversion_intent="casa",
        commercial_relevance="medium",
        destination_url="https://certificacionmontessori.com/diplomados/casa-de-ninos/",
    )


class ManualImageQueueTests(unittest.TestCase):
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

    def test_enqueue_persists_exact_package_and_blocks_second_job(self):
        job = _enqueue()
        job_id = job["job_id"]

        loaded = queue.load_pending_job(job_id)
        self.assertEqual(queue.pending_job_ids(), [job_id])
        self.assertEqual(queue.deserialize_post(loaded), _post())
        self.assertEqual(
            (queue.job_directory(job_id) / "prompt.txt").read_text(encoding="utf-8").strip(),
            job["image"]["full_prompt"],
        )
        self.assertEqual(queue.expected_input_path(job_id).name, f"{job_id}.png")
        with self.assertRaises(queue.PendingJobExists):
            _enqueue()

    def test_progress_is_persisted_and_completed_job_is_archived(self):
        job = _enqueue()
        job_id = job["job_id"]
        queue.update_job_progress(job_id, status="image_prepared", input_name="cover.png")
        queue.update_job_progress(job_id, status="media_uploaded", media_id=77)
        updated = queue.update_job_progress(job_id, status="draft_created", post_id=123)
        self.assertEqual(updated["wordpress"], {"media_id": 77, "post_id": 123})

        completed = queue.complete_job(job_id)
        self.assertTrue((completed / "job.json").is_file())
        self.assertEqual(queue.pending_job_ids(), [])

    def test_progress_cannot_skip_or_reverse_stages_or_replace_ids(self):
        job = _enqueue()
        job_id = job["job_id"]

        with self.assertRaises(queue.ManualImageQueueError):
            queue.update_job_progress(job_id, status="media_uploaded", media_id=77)

        queue.update_job_progress(
            job_id, status="image_prepared", input_name=f"{job_id}.png"
        )
        queue.update_job_progress(job_id, status="media_uploaded", media_id=77)

        with self.assertRaises(queue.ManualImageQueueError):
            queue.update_job_progress(job_id, status="image_prepared")
        with self.assertRaises(queue.ManualImageQueueError):
            queue.update_job_progress(job_id, status="media_uploaded", media_id=78)

        queue.update_job_progress(job_id, status="draft_created", post_id=123)
        with self.assertRaises(queue.ManualImageQueueError):
            queue.update_job_progress(job_id, status="draft_created", post_id=124)

    def test_corrupt_package_fails_closed(self):
        job = _enqueue()
        path = queue.job_directory(job["job_id"]) / "job.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["wordpress"]["post_id"] = 123
        path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaises(queue.ManualImageQueueError):
            queue.load_pending_job(job["job_id"])

    def test_find_input_requires_exactly_one_supported_file(self):
        job = _enqueue()
        job_id = job["job_id"]
        queue.ensure_queue_dirs()
        first = queue.inbox_dir() / f"{job_id}.png"
        second = queue.inbox_dir() / f"{job_id}.jpg"
        first.write_bytes(b"one")
        self.assertEqual(queue.find_input_image(job_id), first)
        second.write_bytes(b"two")
        with self.assertRaises(queue.ManualImageNotReady):
            queue.find_input_image(job_id)

    def test_manual_image_is_cropped_and_saved_as_optimized_jpeg(self):
        source = Path(self.tempdir.name) / "source.png"
        output = Path(self.tempdir.name) / "cover.jpg"
        Image.new("RGB", (1600, 900), (120, 180, 220)).save(source, "PNG")

        with patch.multiple(
            config,
            MANUAL_IMAGE_MAX_MB=20,
            BRAND_LOGO_ENABLED=False,
        ):
            result = prepare_manual_cover_image(source, output, brand_id="ammac")

        self.assertEqual(result, output)
        with Image.open(output) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1200, 630))

    def test_manual_image_rejects_non_image_content(self):
        source = Path(self.tempdir.name) / "fake.png"
        source.write_text("not an image", encoding="utf-8")
        with self.assertRaises(InvalidCoverImage):
            prepare_manual_cover_image(
                source,
                Path(self.tempdir.name) / "cover.jpg",
                brand_id="ammac",
            )


if __name__ == "__main__":
    unittest.main()
