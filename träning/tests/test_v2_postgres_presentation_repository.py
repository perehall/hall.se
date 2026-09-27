#!/usr/bin/env python3
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training_core.repositories.presentation import PostgresPresentationRepository


class Cursor:
    def __init__(self, rows): self.rows=rows; self.query=""
    def execute(self,q,p): self.query=q; self.params=p
    def fetchall(self): return self.rows
    def __enter__(self): return self
    def __exit__(self,*args): pass
class Conn:
    def __init__(self,rows): self.rows=rows
    def cursor(self): return Cursor(self.rows)
    def __enter__(self): return self
    def __exit__(self,*args): pass


class PostgresPresentationRepositoryTests(unittest.TestCase):
    def test_plans_are_read_only_from_current_relational_rows(self):
        rows=[(date(2026,9,27),"Löpning · 60 min","run","conditional","fixed",False,"Skäl","Fokus",{})]
        repo=PostgresPresentationRepository(lambda: Conn(rows))
        days=repo.planned_days(date(2026,9,27),date(2026,10,4))
        self.assertEqual(days[0].session,"Löpning · 60 min")
        self.assertEqual(days[0].planning_status,"fixed")

    def test_activity_override_label_is_already_resolved_by_repository(self):
        rows=[("42",date(2026,9,26),"Enduro","enduro",6062,26611.2)]
        repo=PostgresPresentationRepository(lambda: Conn(rows))
        activities=repo.completed_activities(date(2026,9,26),date(2026,9,26))
        self.assertEqual(activities[0].label,"Enduro")
        self.assertEqual(activities[0].distance_m,26611.2)

    def test_provider_vocabulary_is_normalized_before_presentation(self):
        rows=[("42",date(2026,9,26),"Swim","swim",3822,3000.0)]
        repo=PostgresPresentationRepository(lambda: Conn(rows))
        activities=repo.completed_activities(date(2026,9,26),date(2026,9,26))
        self.assertEqual(activities[0].label,"Simning")



if __name__ == "__main__":
    unittest.main()
