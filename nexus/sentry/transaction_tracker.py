import logging
from contextlib import contextmanager
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@contextmanager
def track_transaction(
    name: str,
    op: str,
    tags: Optional[Dict[str, str]] = None,
    set_measurement: bool = True,
):
    import time
    import sentry_sdk

    transaction = None
    start_time = time.time()
    status = "ok"
    error = None

    try:
        transaction = sentry_sdk.start_transaction(
            name=name,
            op=op,
            sampled=True,
        )

        if transaction:
            transaction_sampled = getattr(transaction, "sampled", None)
            if transaction_sampled is False:
                logger.warning(
                    f"Transaction {name} was created but NOT sampled - will not be sent to Sentry",
                    extra={"transaction_name": name, "transaction_op": op},
                )

            if tags:
                for key, value in tags.items():
                    transaction.set_tag(key, value)

    except Exception as e:
        logger.debug(f"Failed to start Sentry transaction {name}: {e}", exc_info=True)

    try:
        yield transaction
    except Exception as e:
        status = "internal_error"
        error = str(e)
        raise
    finally:
        if transaction:
            try:
                duration = time.time() - start_time

                if set_measurement:
                    transaction.set_measurement("duration", duration, unit="second")

                transaction.set_status(status)

                if error:
                    transaction.set_data("error", error)

                transaction.finish()

            except Exception as e:
                logger.debug(f"Failed to finish Sentry transaction {name}: {e}", exc_info=True)
