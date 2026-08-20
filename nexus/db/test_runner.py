from django.db import connections
from django.test.runner import DiscoverRunner


class NexusTestRunner(DiscoverRunner):
    """
    DiscoverRunner that terminates leftover PostgreSQL sessions before dropping
    the test database.

    Async observers and asgiref's thread-sensitive executor can leave open
    connections on worker threads after tests finish. PostgreSQL then refuses
    DROP DATABASE with "is being accessed by other users", which fails CI even
    when every test passed.
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
        with connection.creation._nodb_cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s
                  AND pid <> pg_backend_pid()
                """,
                [test_database_name],
            )
