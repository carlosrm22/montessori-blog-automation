import unittest
from types import SimpleNamespace

from wordpress import build_post_slug


class WordPressSlugTests(unittest.TestCase):
    def test_uses_editorial_title_not_branded_seo_title(self):
        post = SimpleNamespace(
            title="Observación en Casa de Niños",
            seo_title="Observación en Casa de Niños | Asociación Montessori de México",
        )
        self.assertEqual(build_post_slug(post), "observacion-en-casa-de-ninos")


if __name__ == "__main__":
    unittest.main()
