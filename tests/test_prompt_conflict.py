import unittest
from plepa_engine.prompt_pipeline import (
    find_tag_conflicts,
    normalize_tag,
    remove_conflicting_tags_from_negative,
    split_tags,
    default_sdxl_pipeline,
    PromptContext,
)
from plepa_engine.models import CharacterConfig, CharacterAppearance, PoseEntry


class TestTagConflicts(unittest.TestCase):
    def test_normalize_tag(self):
        self.assertEqual(normalize_tag(" (looking at viewer:1.2) "), "looking at viewer")
        self.assertEqual(normalize_tag("((smile))"), "smile")
        self.assertEqual(normalize_tag("[[blue eyes]]"), "blue eyes")

    def test_split_tags(self):
        text = "masterpiece, (1girl:1.2), BREAK solo, cute smile"
        tags = split_tags(text)
        self.assertIn("masterpiece", tags)
        self.assertIn("1girl", tags)
        self.assertIn("solo", tags)
        self.assertIn("cute smile", tags)

    def test_find_tag_conflicts(self):
        pos = "1girl, looking at viewer, blue eyes, smile"
        neg = "worst quality, (looking at viewer:1.3), bad hands, (blue eyes:1.1)"
        conflicts = find_tag_conflicts(pos, neg)
        self.assertEqual(conflicts, ["blue eyes", "looking at viewer"])

    def test_remove_conflicting_tags_from_negative(self):
        pos = "1girl, smile, red hair"
        neg = "worst quality, (smile:1.2), bad hands, red hair, lowres"
        cleaned_neg, conflicts = remove_conflicting_tags_from_negative(pos, neg)
        self.assertEqual(sorted(conflicts), ["red hair", "smile"])
        self.assertNotIn("smile", cleaned_neg)
        self.assertNotIn("red hair", cleaned_neg)
        self.assertIn("worst quality", cleaned_neg)
        self.assertIn("bad hands", cleaned_neg)

    def test_pipeline_integration(self):
        char = CharacterConfig(
            prefix="test",
            name="TestChar",
            gender="female",
            appearance=CharacterAppearance(face_and_hair="", physique="", outfit=""),
            sdxl_positive="masterpiece BREAK 1girl, cute smile, blue hair",
            sdxl_negative="worst quality, cute smile, blue hair, bad hands",
        )
        pose = PoseEntry(code="001", section="poses", label="test", prompt="standing")
        ctx = PromptContext(char=char, pose=pose)
        pos, neg, is_nude = default_sdxl_pipeline.execute(ctx)
        # Verify that cute smile and blue hair were purged from negative
        self.assertNotIn("cute smile", neg)
        self.assertNotIn("blue hair", neg)
        self.assertIn("worst quality", neg)


if __name__ == "__main__":
    unittest.main()
