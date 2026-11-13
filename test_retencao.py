import unittest
from collections import Counter

import pandas as pd

from etl import cohort, normalize


class RetentionTest(unittest.TestCase):
    def test_assistant_time_when_user_time_is_missing(self):
        audit = Counter()
        normalized = normalize({
            "hashed_ip": "example", "header": None,
            "timestamp": "2023-11-20T12:00Z", "model": "gpt-4", "language": "Portuguese",
            "turn": 2, "conversation": [
                {"role": "user", "content": "Explique este exercício"},
                {"role": "assistant", "content": "Resposta", "timestamp": "2023-11-20T12:00Z"},
                {"role": "user", "content": "E agora?"},
                {"role": "assistant", "content": "Outra resposta", "timestamp": "2023-11-20T12:02Z"},
            ],
        }, audit)
        self.assertEqual(normalized["inicio"], pd.Timestamp("2023-11-20T12:00Z"))
        self.assertEqual(normalized["fim"], pd.Timestamp("2023-11-20T12:02Z"))
        self.assertEqual(normalized["resposta_chars"], 8)
        self.assertEqual(normalized["tema"], "Estudo")

    def test_session_merging_boundary_censoring_and_identity(self):
        start = pd.Timestamp("2023-11-20T12:00Z")
        rows = []

        def add(ip, agent, offset, duration=0):
            time = start + pd.Timedelta(offset)
            rows.append(dict(chave=str(len(rows)), ip=ip, ip_ua=f"{ip}/{agent}",
                             inicio=time, fim=time + pd.Timedelta(minutes=duration),
                             modelo="GPT-4", idioma="Portuguese", tema="Código", turnos=1,
                             resposta_chars=200, resposta="Resposta registrada"))

        add("a", 1, "0min", 40)
        add("a", 1, "60min", 10)
        add("a", 2, "7d")
        add("b", 1, "0min")
        add("b", 1, "7d 1s")
        add("c", 1, "8d")
        data = pd.DataFrame(rows)
        cutoff = start + pd.Timedelta(days=10)
        primary = cohort(data, "ip", cutoff)
        alternative = cohort(data, "ip_ua", cutoff)
        self.assertEqual(len(primary), 3)
        self.assertEqual(primary.elegivel.sum(), 2)
        self.assertEqual(primary.voltou.sum(), 1)
        self.assertTrue(primary.loc[primary.elegivel.eq(0), "voltou"].isna().all())
        self.assertEqual(len(alternative), 4)
        self.assertEqual(alternative.voltou.sum(), 0)


if __name__ == "__main__":
    unittest.main()
