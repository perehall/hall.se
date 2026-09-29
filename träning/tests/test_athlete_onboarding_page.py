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
            "Var står du idag?",
            "Hur många dagar per vecka vill du normalt träna?",
            "När kan träningen få plats?",
            "Två pass samma dag",
            "Helt träningsfria dagar",
            "Vilka återkommande aktiviteter ska planen ta hänsyn till?",
            "Hur mycket frihet ska coachen ha?",
            "Så här har jag förstått dig.",
        ):
            self.assertIn(text, self.page)

    def test_starting_state_backend_failure_fails_closed(self):
        self.assertIn("starting_state_backend_unavailable", self.page)
        self.assertIn("Startläget kunde inte laddas", self.page)
        self.assertIn("Inga antaganden görs", self.page)
        self.assertIn("if(!startingStateBackendReady)", self.page)

    def test_starting_state_is_adaptive_and_explicitly_confirmed(self):
        self.assertIn('const STARTING_STATE_API="/träning/training-api/profile/starting-state"', self.page)
        self.assertIn("Jag kan redan se din senaste träning", self.page)
        self.assertIn("Ja, detta är representativt", self.page)
        self.assertIn("Nej, jag vill beskriva nuläget själv", self.page)
        self.assertIn("Självrapporterad nivå används bara för en konservativ första etablering", self.page)
        self.assertIn('await persistStartingState("confirmed")', self.page)
        self.assertIn('profile.status==="complete"&&startingState.status!=="confirmed"', self.page)

    def test_observed_starting_state_shows_capacity_markers_not_only_volume(self):
        self.assertIn("Observerade kapacitetsmarkörer", self.page)
        self.assertIn("Löptröskel", self.page)
        self.assertIn("Längsta lugna löpning", self.page)
        self.assertIn("längsta observerade pass", self.page)
        self.assertIn("absorberad", self.page)
        self.assertIn("tolererad", self.page)

    def test_manual_starting_state_has_sport_specific_fields(self):
        for marker in (
            "Ungefär km/vecka",
            "Längre pass",
            "Typisk passdistans",
            "Bassänglängd",
            "FTP, om känd",
            "Terrängvana",
        ):
            self.assertIn(marker, self.page)

    def test_frequency_is_expressed_as_preferred_plus_normal_range(self):
        self.assertIn("Helst", self.page)
        self.assertIn("Vanligt spann", self.page)
        self.assertIn('id="preferredDays"', self.page)
        self.assertIn('id="minDays"', self.page)
        self.assertIn('id="maxDays"', self.page)
        self.assertNotIn("Minst acceptabelt", self.page)
        self.assertNotIn("Som mest normalt", self.page)

    def test_indoor_cycling_is_an_explicit_capability(self):
        self.assertIn('["indoor_bike","Cykeltrainer / inomhuscykel"]', self.page)

    def test_summary_uses_regular_body_weight_and_visual_hierarchy(self):
        self.assertIn(".summary-value{color:var(--text);font-size:.95rem;font-weight:400", self.page)
        self.assertIn('class="summary-label"', self.page)
        self.assertIn('class="summary-value summary-goals"', self.page)
        self.assertNotIn(".summary-row strong", self.page)

    def test_summary_is_editable_and_generation_is_explicit(self):
        self.assertIn('class="summary-edit"', self.page)
        self.assertIn('data-edit-step', self.page)
        self.assertIn("Skapa min träningsplan", self.page)
        self.assertIn('const GENERATE_API="/träning/training-api/profile/generate"', self.page)
        self.assertIn("Planeringskörning köad", self.page)
        self.assertIn("Coachmotorn bygger träningsblock och vecka", self.page)
        self.assertIn("Planen är genererad och publicering är startad", self.page)

    def test_generation_status_is_polled_from_backend(self):
        self.assertIn("pollGeneration", self.page)
        self.assertIn('fetch(GENERATE_API+"?id="', self.page)
        self.assertIn('body.status==="completed"||body.status==="failed"', self.page)

    def test_draft_resume_and_durable_api_are_present(self):
        self.assertIn('const API="/träning/training-api/profile"', self.page)
        self.assertIn('await fetch(API,{method:"PUT"', self.page)
        self.assertIn('const response=await fetch(API', self.page)
        self.assertIn('await persist("draft")', self.page)
        self.assertIn('await persist("complete")', self.page)

    def test_page_uses_real_generation_states_instead_of_fake_completion(self):
        self.assertNotIn("omplanering är köad", self.page)
        self.assertIn("Du kan lämna sidan; körningen fortsätter beständigt i backend.", self.page)
        self.assertIn("Ingen ny plan ska betraktas som publicerad.", self.page)


if __name__ == "__main__":
    unittest.main()
