import logging

from django.db import connections
from django.test.runner import DiscoverRunner

logger = logging.getLogger(__name__)


class NexusTestRunner(DiscoverRunner):
    """
    DiscoverRunner that terminates leftover PostgreSQL sessions before dropping
    the test database.

    Async observers and asgiref's thread-sensitive executor can leave open
    connections on worker threads after tests finish. PostgreSQL then refuses
    DROP DATABASE with "is being accessed by other users", which fails CI even
    when every test passed.

    Requirements:
    - The database role used in CI/tests must be allowed to call
      ``pg_terminate_backend`` on other backends for the test database
      (superuser or a role with that privilege). The official Postgres image
      ``POSTGRES_USER`` is a superuser, which covers GitHub Actions CI.

    Notes:
    - After ``connections.close_all()``, any remaining sessions are treated as
      leftovers and force-terminated. That is intentional during teardown so
      DROP DATABASE can proceed; there is no graceful per-connection cleanup
      for threads we no longer control.
    - Uses ``connection._nodb_cursor()``, the same helper Django uses for test
      database create/drop.
    """

    def teardown_databases(self, old_config, **kwargs):
        connections.close_all()
        for connection, _old_name, destroy in old_config:
            if destroy and connection.vendor == "postgresql":
                self._terminate_leftover_connections(connection)
        return super().teardown_databases(old_config, **kwargs)

    @staticmethod
    def _terminate_leftover_connections(connection):
        test_database_name = connection.settings_dict["NAME"]
        try:
            with connection._nodb_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid()
                    """,
                    [test_database_name],
                )
        except Exception:
            logger.warning(
                "Failed to terminate leftover connections for test database %r; " "continuing with teardown",
                test_database_name,
                exc_info=True,
            )
