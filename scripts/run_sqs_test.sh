#!/bin/bash
# Helper script para executar testes SQS completos

set -e

echo "=========================================="
echo "SQS Load Test Helper"
echo "=========================================="
echo ""

# Default values
MESSAGES=${1:-1000}
BATCH_SIZE=${2:-1000}
PROCESSING_DELAY=${3:-0.1}

echo "Configuration:"
echo "  Messages: $MESSAGES"
echo "  Batch size: $BATCH_SIZE"
echo "  Processing delay: ${PROCESSING_DELAY}s"
echo ""

# Check if consumer is running
echo "⚠️  Make sure the consumer is running in another terminal:"
echo "   python conversation_ms/main.py"
echo ""
read -p "Press Enter when consumer is ready..."

# Run load test
echo "Starting load test..."
python scripts/test_sqs_load.py --messages $MESSAGES --batch-size $BATCH_SIZE

echo ""
echo "✅ Load test completed!"
echo ""
echo "Wait for consumer to finish processing, then press Ctrl+C in consumer terminal"
echo "to save stats, then run validation:"
echo ""
echo "  python scripts/validate_sqs_test.py \\"
echo "    --load-test-file sqs_load_test_results_*.json \\"
echo "    --consumer-stats-file sqs_consumer_stats_*.json"
echo ""
