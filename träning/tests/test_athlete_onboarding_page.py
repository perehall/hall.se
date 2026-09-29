import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "onboarding" / "index.html"


class AthleteOnboardingPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_onboarding_has_core_declared_inputs(self):
        for text in (
            "Vad vill du få ut av din träning?",
            "Hur ofta vill du normalt träna?",
            "När kan träningen få plats?",
            "Två pass samma dag",
            "Helt träningsfria dagar",
            "Vad finns redan i kalendern?",
            "Hur mycket frihet ska coachen ha?",
            "Så här har jag förstått dig.",
        ):
            self.assertIn(text, self.page)

    def test_draft_resume_and_durable_api_are_present(self):
        self.assertIn('const API="/träning/training-api/profile"', self.page)
        self.assertIn('await fetch(API,{method:"PUT"', self.page)
        self.assertIn('const response=await fetch(API', self.page)
        self.assertIn('await persist("draft")', self.page)
        self.assertIn('await persist("complete")', self.page)

    def test_page_does_not_claim_completed_profile_has_replanned(self):
        self.assertNotIn("omplanering är köad", self.page)
        self.assertIn("beständigt sparad", self.page)


if __name__ == "__main__":
    unittest.main()
