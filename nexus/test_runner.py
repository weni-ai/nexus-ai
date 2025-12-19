from django.db import connections
from django.test.runner import DiscoverRunner


class NexusTestRunner(DiscoverRunner):
    """Custom test runner that closes database connections after tests."""

    def teardown_databases(self, old_config, **kwargs):
        """Close all database connections before destroying test database."""
        # Close all connections first to prevent "database is being accessed" error
        for conn in connections.all():
            try:
                conn.close()
            except Exception:
                pass
        # Then proceed with normal teardown
        super().teardown_databases(old_config, **kwargs)
