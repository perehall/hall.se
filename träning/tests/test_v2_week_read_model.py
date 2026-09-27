#!/usr/bin/env python3
import sys, unittest
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from training_core.presentation.today import CompletedActivity, PlannedDay
from training_core.presentation.week import build_week_read_model

class WeekReadModelTests(unittest.TestCase):
    def test_multiple_activities_are_one_training_day_but_two_activities(self):
        start=date(2026,9,21); end=date(2026,9,27)
        plan=[PlannedDay(date(2026,9,26),"Simning · 4 000 m","swim","planned")]
        acts=[
            CompletedActivity("1",date(2026,9,26),"Enduro","enduro"),
            CompletedActivity("2",date(2026,9,26),"Simning","swim"),
        ]
        model=build_week_read_model(start=start,end=end,plan=plan,activities=acts)
        self.assertEqual(model.training_day_count,1)
        self.assertEqual(model.completed_activity_count,2)
        self.assertEqual(model.days[0].actual_labels,("Enduro","Simning"))
        self.assertEqual(model.days[0].state,"completed")

if __name__=="__main__": unittest.main()
