"""Integração com Parquet sintético, sem rede ou alteração da base do usuário."""
from pathlib import Path
from contextlib import closing
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

import etl


class PipelineTest(unittest.TestCase):
    def test_raw_to_database_and_failed_load_preserves_previous_snapshot(self):
        with TemporaryDirectory() as folder:
            data = Path(folder)
            source = data / "fixture.parquet"
            database = data / "retencao.sqlite"
            rows = []
            for ip, when, country in [
                ("a", "2023-11-01T12:00Z", "Brazil"),
                ("a", "2023-11-03T12:00Z", "Brazil"),
                ("b", "2023-11-02T12:00Z", "Brazil"),
                ("b", "2023-11-04T12:00Z", "Argentina"),
                ("c", "2023-11-10T12:00Z", "Brazil"),
            ]:
                rows.append(dict(country=country, state="SP", hashed_ip=ip,
                                 header={"user-agent": "browser"}, timestamp=when,
                                 model="gpt-4", language="Portuguese", turn=1,
                                 conversation=[{"role": "user", "content": "Explique Python",
                                                "timestamp": when, "turn_identifier": ip + when}]))
            pq.write_table(pa.Table.from_pylist(rows + [rows[0]]), source)
            with patch.object(etl, "DATA", data), patch.object(etl, "DB", database), \
                    patch.object(etl, "source_files", return_value=[source]):
                etl.build()
                with closing(sqlite3.connect(database)) as db:
                    self.assertEqual(db.execute("SELECT count(*), sum(elegivel), sum(voltou) "
                                                "FROM coortes WHERE regra='ip'").fetchone(), (3, 2, 1))
                    self.assertEqual(db.execute("SELECT sum(conversas) FROM volume_semanal").fetchone()[0], 4)
                    self.assertEqual(db.execute("SELECT valor FROM auditoria WHERE item='duplicatas exatas removidas'").fetchone()[0], "1")
                    columns = {r[1] for r in db.execute("PRAGMA table_info(coortes)")}
                    self.assertTrue(columns.isdisjoint({"ip", "ip_ua", "content", "hashed_ip", "header"}))
                before = database.read_bytes()
                with patch.object(etl, "cohort", side_effect=RuntimeError("falha simulada")):
                    with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                        etl.build()
                self.assertEqual(before, database.read_bytes())


if __name__ == "__main__":
    unittest.main()
