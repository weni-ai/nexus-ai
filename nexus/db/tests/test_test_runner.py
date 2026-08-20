from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner

from nexus.db.test_runner import NexusTestRunner


class NexusTestRunnerTests(SimpleTestCase):
    def test_terminate_leftover_connections_targets_test_database(self):
        cursor = MagicMock()

        @contextmanager
        def nodb_cursor():
            yield cursor

        connection = MagicMock()
        connection.settings_dict = {"NAME": "test_nexus"}
        connection._nodb_cursor = nodb_cursor

        NexusTestRunner._terminate_leftover_connections(connection)

        cursor.execute.assert_called_once()
        sql, params = cursor.execute.call_args[0]
        self.assertIn("pg_terminate_backend", sql)
        self.assertIn("pg_stat_activity", sql)
        self.assertEqual(params, ["test_nexus"])

    def test_terminate_leftover_connections_swallows_errors(self):
        connection = MagicMock()
        connection.settings_dict = {"NAME": "test_nexus"}
        connection._nodb_cursor.side_effect = RuntimeError("permission denied")

        with self.assertLogs("nexus.db.test_runner", level="WARNING") as logs:
            NexusTestRunner._terminate_leftover_connections(connection)

        self.assertTrue(any("Failed to terminate leftover connections" in message for message in logs.output))

    def test_teardown_databases_terminates_postgres_before_super(self):
        runner = NexusTestRunner(verbosity=0, interactive=False)
        connection = MagicMock()
        connection.vendor = "postgresql"
        connection.settings_dict = {"NAME": "test_nexus"}
        old_config = [(connection, "nexus", True)]

        with (
            patch.object(NexusTestRunner, "_terminate_leftover_connections") as terminate,
            patch("nexus.db.test_runner.connections.close_all") as close_all,
            patch.object(DiscoverRunner, "teardown_databases", return_value=None) as super_teardown,
        ):
            runner.teardown_databases(old_config)

        close_all.assert_called_once_with()
        terminate.assert_called_once_with(connection)
        super_teardown.assert_called_once()

    def test_teardown_continues_when_terminate_fails(self):
        runner = NexusTestRunner(verbosity=0, interactive=False)
        connection = MagicMock()
        connection.vendor = "postgresql"
        connection.settings_dict = {"NAME": "test_nexus"}
        connection._nodb_cursor.side_effect = RuntimeError("boom")
        old_config = [(connection, "nexus", True)]

        with (
            patch("nexus.db.test_runner.connections.close_all"),
            patch.object(DiscoverRunner, "teardown_databases", return_value=None) as super_teardown,
            self.assertLogs("nexus.db.test_runner", level="WARNING"),
        ):
            runner.teardown_databases(old_config)

        super_teardown.assert_called_once()

    def test_teardown_databases_skips_non_postgres(self):
        runner = NexusTestRunner(verbosity=0, interactive=False)
        connection = MagicMock()
        connection.vendor = "sqlite"
        old_config = [(connection, "db.sqlite3", True)]

        with (
            patch.object(NexusTestRunner, "_terminate_leftover_connections") as terminate,
            patch("nexus.db.test_runner.connections.close_all"),
            patch.object(DiscoverRunner, "teardown_databases", return_value=None),
        ):
            runner.teardown_databases(old_config)

        terminate.assert_not_called()
