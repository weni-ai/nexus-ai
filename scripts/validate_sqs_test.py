#!/usr/bin/env python
"""
Script de validação para comparar mensagens enviadas vs processadas.

Valida que:
- Nenhuma mensagem foi perdida
- Nenhuma mensagem foi duplicada
- Todas as mensagens foram processadas corretamente
"""

import argparse
import json
import logging
import sys
from collections import Counter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_json_file(filepath: str) -> dict:
    """Load JSON file."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in file {filepath}: {e}")
        sys.exit(1)


def validate_test_results(load_test_file: str, consumer_stats_file: str):
    """
    Valida os resultados do teste comparando mensagens enviadas vs processadas.

    Args:
        load_test_file: Caminho para o arquivo de resultados do load test
        consumer_stats_file: Caminho para o arquivo de stats do consumer
    """
    logger.info("=" * 80)
    logger.info("VALIDATING SQS TEST RESULTS")
    logger.info("=" * 80)

    # Load files
    load_test_results = load_json_file(load_test_file)
    consumer_stats = load_json_file(consumer_stats_file)

    # Extract data
    sent_messages = load_test_results.get("sent_messages", [])
    processed_messages = consumer_stats.get("processed_messages", [])

    logger.info(f"Sent messages: {len(sent_messages)}")
    logger.info(f"Processed messages: {len(processed_messages)}")
    logger.info(f"Consumer errors: {consumer_stats.get('error_count', 0)}")
    logger.info(f"Consumer duplicates: {consumer_stats.get('duplicate_count', 0)}")

    # Create lookup dictionaries
    sent_by_correlation = {msg["correlation_id"]: msg for msg in sent_messages}
    sent_by_index = {msg["index"]: msg for msg in sent_messages if "index" in msg}

    processed_by_correlation = {}
    processed_by_index = {}
    correlation_counts = Counter()

    for msg in processed_messages:
        corr_id = msg.get("correlation_id")
        test_index = msg.get("test_index")

        if corr_id:
            correlation_counts[corr_id] += 1
            if corr_id not in processed_by_correlation:
                processed_by_correlation[corr_id] = msg

        if test_index is not None:
            processed_by_index[test_index] = msg

    # Validation checks
    issues = []
    warnings = []

    # 1. Check for lost messages
    missing_correlations = set(sent_by_correlation.keys()) - set(processed_by_correlation.keys())
    if missing_correlations:
        issues.append(f"❌ LOST MESSAGES: {len(missing_correlations)} messages were sent but not processed")
        logger.error(f"Missing correlation IDs: {list(missing_correlations)[:10]}...")

    # 2. Check for duplicates
    duplicates = [corr_id for corr_id, count in correlation_counts.items() if count > 1]
    if duplicates:
        issues.append(f"❌ DUPLICATE MESSAGES: {len(duplicates)} messages were processed multiple times")
        logger.error(f"Duplicate correlation IDs: {duplicates[:10]}...")

    # 3. Check for extra messages (not sent but processed)
    extra_correlations = set(processed_by_correlation.keys()) - set(sent_by_correlation.keys())
    if extra_correlations:
        warnings.append(f"⚠️  EXTRA MESSAGES: {len(extra_correlations)} messages were processed but not in sent list")

    # 4. Check by test_index if available
    if sent_by_index:
        missing_indices = set(sent_by_index.keys()) - set(processed_by_index.keys())
        if missing_indices:
            issues.append(f"❌ MISSING INDICES: {len(missing_indices)} test indices were not processed")
            logger.error(f"Missing indices: {sorted(list(missing_indices))[:20]}...")

    # Summary
    logger.info("=" * 80)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 80)

    if not issues and not warnings:
        logger.info("✅ ALL VALIDATIONS PASSED!")
        logger.info(f"✅ All {len(sent_messages)} sent messages were processed")
        logger.info("✅ No duplicates found")
        logger.info("✅ No messages lost")
    else:
        if issues:
            logger.error("VALIDATION FAILED:")
            for issue in issues:
                logger.error(issue)
        if warnings:
            logger.warning("WARNINGS:")
            for warning in warnings:
                logger.warning(warning)

    # Statistics
    logger.info("=" * 80)
    logger.info("STATISTICS")
    logger.info("=" * 80)
    logger.info(f"Total sent: {len(sent_messages)}")
    logger.info(f"Total processed: {len(processed_messages)}")
    logger.info(f"Success rate: {len(processed_messages) / len(sent_messages) * 100:.2f}%" if sent_messages else "N/A")
    logger.info(f"Lost messages: {len(missing_correlations)}")
    logger.info(f"Duplicate messages: {len(duplicates)}")
    logger.info(f"Consumer errors: {consumer_stats.get('error_count', 0)}")
    logger.info(f"Consumer throughput: {consumer_stats.get('throughput_msg_per_sec', 0):.2f} msg/s")
    logger.info("=" * 80)

    # Performance comparison
    load_duration = load_test_results.get("total_duration_seconds", 0)
    consumer_duration = consumer_stats.get("duration_seconds", 0)

    if load_duration > 0 and consumer_duration > 0:
        logger.info("PERFORMANCE COMPARISON")
        logger.info(f"Load test duration: {load_duration:.2f}s")
        logger.info(f"Consumer duration: {consumer_duration:.2f}s")
        logger.info(f"Load test throughput: {load_test_results.get('overall_throughput_msg_per_sec', 0):.2f} msg/s")
        logger.info(f"Consumer throughput: {consumer_stats.get('throughput_msg_per_sec', 0):.2f} msg/s")
        logger.info("=" * 80)

    # Return exit code
    return 0 if not issues else 1


def main():
    parser = argparse.ArgumentParser(description="Validate SQS Test Results")
    parser.add_argument(
        "--load-test-file",
        type=str,
        required=True,
        help="Path to load test results JSON file",
    )
    parser.add_argument(
        "--consumer-stats-file",
        type=str,
        required=True,
        help="Path to consumer stats JSON file",
    )

    args = parser.parse_args()

    exit_code = validate_test_results(args.load_test_file, args.consumer_stats_file)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
