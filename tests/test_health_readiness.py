import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from bisnu_x import db
from bisnu_x.app import app


class DatabaseConnectionCheckTests(TestCase):
    def test_database_check_executes_query_and_reports_sqlite(self):
        class Result:
            def fetchone(self):
                return {"healthcheck": 1}

        class Connection:
            closed = False

            def execute(self, statement):
                self.statement = statement
                return Result()

            def close(self):
                self.closed = True

        connection = Connection()
        with (
            patch.object(db, "connection", return_value=connection),
            patch.object(db, "DATABASE_URL", ""),
        ):
            status = db.check_database()

        self.assertEqual(connection.statement, "SELECT 1 AS healthcheck")
        self.assertTrue(connection.closed)
        self.assertEqual(
            status,
            {"backend": "sqlite", "connected": True},
        )

    def test_database_check_does_not_fall_back_to_sqlite_when_required(self):
        with tempfile.TemporaryDirectory() as directory:
            sqlite_path = Path(directory) / "must-not-be-created.sqlite3"
            with (
                patch.object(db, "DATABASE_URL", ""),
                patch.object(db, "REQUIRE_PERSISTENT_DATABASE", True),
                patch.object(db, "DB_PATH", sqlite_path),
            ):
                with self.assertRaises(db.DatabaseHealthError):
                    db.check_database()
            self.assertFalse(sqlite_path.exists())


class ProductionHealthTests(TestCase):
    def test_health_reports_connected_postgresql(self):
        with patch.object(
            db,
            "check_database",
            return_value={"backend": "postgresql", "connected": True},
        ):
            with TestClient(app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database_backend"], "postgresql")
        self.assertTrue(response.json()["database_connected"])

    def test_health_is_unavailable_when_database_check_fails(self):
        with patch.object(
            db,
            "check_database",
            side_effect=db.DatabaseHealthError("Database health check failed."),
        ):
            with TestClient(app) as client:
                response = client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Persistent database unavailable.",
        )
