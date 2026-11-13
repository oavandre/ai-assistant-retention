import sqlite3
import unittest
from collections import Counter
from contextlib import closing

import pandas as pd

from analysis import WEEKLY_SQL
from etl import cohort, normalize


class IncidentTest(unittest.TestCase):
    def test_browser_change_preserves_return_in_weekly_report(self):
        events = [
            ("ip-a", "Navegador A", "2023-11-20T12:00Z", "Brazil"),
            ("ip-a", "Navegador B", "2023-11-22T12:00Z", "Brazil"),
            ("ip-b", "Navegador A", "2023-11-21T12:00Z", "Brazil"),
            ("ip-b", "Navegador A", "2023-11-23T12:00Z", "Argentina"),
        ]
        audit = Counter()
        conversations = pd.DataFrame([
            normalize({
                "hashed_ip": ip, "header": {"user-agent": browser}, "timestamp": timestamp,
                "model": "gpt-4", "language": "Portuguese", "turn": 1,
                "conversation": [{"role": "user", "timestamp": timestamp}],
            }, audit)
            for ip, browser, timestamp, country in events if country == "Brazil"
        ])
        cutoff = pd.Timestamp("2023-11-30T00:00Z")
        with closing(sqlite3.connect(":memory:")) as db:
            for rule in ("ip", "ip_ua"):
                cohort(conversations, rule, cutoff).assign(regra=rule).to_sql(
                    "coortes", db, if_exists="append", index=False
                )
            week = "2023-11-20"
            split = db.execute(WEEKLY_SQL, ("ip_ua", week, week)).fetchone()
            corrected = db.execute(WEEKLY_SQL, ("ip", week, week)).fetchone()
            self.assertEqual(split, (week, 3, 3, 0, 0.0))
            self.assertEqual(corrected, (week, 2, 2, 1, 0.5))


if __name__ == "__main__":
    unittest.main()
