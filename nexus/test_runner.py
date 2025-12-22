import time

from django.db import close_old_connections, connections
from django.test.runner import DiscoverRunner


class NexusTestRunner(DiscoverRunner):
    """Custom test runner that closes database connections after tests."""

    def teardown_databases(self, old_config, **kwargs):
        """Close all database connections before destroying test database."""
        # Shutdown ThreadPoolExecutor from nexus.events if it exists
        # This prevents background threads from keeping database connections open
        try:
            from nexus.events import _executor

            _executor.shutdown(wait=True, timeout=5)
        except (ImportError, AttributeError):
            pass
        except Exception:
            pass

        # Close all connections multiple times to ensure they're closed
        # This is necessary because PostgreSQL may have connections in different states
        for attempt in range(3):
            for alias in connections:
                conn = connections[alias]
                try:
                    # Rollback any pending transactions
                    if conn.in_atomic_block:
                        conn.rollback()

                    # Close the connection
                    conn.close()

                    # If it's a PostgreSQL connection, also close the underlying connection
                    if hasattr(conn, "connection") and conn.connection:
                        try:
                            conn.connection.close()
                            conn.connection = None
                        except Exception:
                            pass
                except Exception:
                    pass

            # Use Django's close_old_connections utility
            close_old_connections()

            # Small delay to allow connections to close
            if attempt < 2:
                time.sleep(0.1)

        # Final cleanup - ensure all connections are closed
        for alias in connections:
            try:
                connections[alias].close()
            except Exception:
                pass

        # Then proceed with normal teardown
        super().teardown_databases(old_config, **kwargs)
