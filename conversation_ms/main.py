#!/usr/bin/env python
"""
Entry point for Conversation MS SQS Consumer (Prototype).

This is a simple script to run the SQS consumer for testing purposes.
In production, this would be replaced with a proper service/daemon.
"""

import json
import logging
import signal
import sys
import time
from pathlib import Path

# Load environment variables from .env file (same way as Django settings)
import environ

# Load .env file from project root
project_root = Path(__file__).resolve().parent.parent
env_file = project_root / ".env"
if env_file.exists():
    environ.Env.read_env(env_file=str(env_file))
    logging.info(f"[main] Loaded environment from {env_file}")

from conversation_ms.consumers.sqs_consumer import ConversationSQSConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("[main] Received shutdown signal, stopping consumer...")
    if hasattr(signal_handler, "consumer"):
        consumer = signal_handler.consumer
        consumer.stop_consuming()

        # Save stats to file (backup)
        stats = consumer.get_stats()
        stats_file = f"sqs_consumer_stats_{int(time.time())}.json"
        with open(stats_file, "w") as f:
            json.dump(stats, f, indent=2)
        logger.info(f"[main] Stats saved to: {stats_file}")
        logger.info(f"[main] Consolidated report: {consumer.report_file}")

    sys.exit(0)


def main():
    """Main entry point for the consumer."""
    logger.info("[main] Starting Conversation MS SQS Consumer (Prototype)")

    try:
        consumer = ConversationSQSConsumer()
        signal_handler.consumer = consumer

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start consuming
        consumer.start_consuming()

    except KeyboardInterrupt:
        logger.info("[main] Interrupted by user")
        if hasattr(signal_handler, "consumer"):
            consumer = signal_handler.consumer
            consumer.stop_consuming()
            stats = consumer.get_stats()
            stats_file = f"sqs_consumer_stats_{int(time.time())}.json"
            with open(stats_file, "w") as f:
                json.dump(stats, f, indent=2)
            logger.info(f"[main] Stats saved to: {stats_file}")
            logger.info(f"[main] Consolidated report: {consumer.report_file}")
    except Exception as e:
        logger.error("[main] Fatal error", extra={"error": str(e)}, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
