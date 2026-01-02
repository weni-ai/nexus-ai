import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Constantes
REPORT_UPDATE_INTERVAL = 60  # Atualizar relatório a cada 60 segundos
CONSUMER_REPORT_FILE = "sqs_consumer_report_consolidated.json"


class ConversationSQSConsumer:
    """Basic SQS Consumer for Conversation MS prototype."""

    def __init__(
        self,
        queue_url: Optional[str] = None,
        region: str = "us-east-1",
        processing_delay: float = 0.01,  # Reduzido para 10ms (mais rápido para testes)
        consumer_id: Optional[str] = None,  # ID único do consumer
        expected_total_messages: Optional[int] = None,  # Total esperado de mensagens
    ):
        """
        Initialize SQS Consumer.

        Args:
            queue_url: SQS FIFO queue URL (defaults to env var)
            region: AWS region (defaults to us-east-1)
            processing_delay: Delay in seconds to simulate DB insertion (default: 0.1s)
            consumer_id: ID único do consumer (default: gera automaticamente com PID + timestamp)
            expected_total_messages: Total esperado de mensagens para mostrar progresso
        """
        self.queue_url = queue_url or os.environ.get("SQS_CONVERSATION_QUEUE_URL", "")
        self.region = region
        self.processing_delay = float(os.environ.get("SQS_PROCESSING_DELAY", processing_delay))
        self.running = False

        # ID único do consumer (PID + timestamp)
        if consumer_id:
            self.consumer_id = consumer_id
        else:
            import os as os_module

            pid = os_module.getpid()
            timestamp = int(time.time())
            self.consumer_id = f"consumer_{pid}_{timestamp}"

        # Total esperado de mensagens
        self.expected_total_messages = expected_total_messages or int(
            os.environ.get("SQS_EXPECTED_TOTAL_MESSAGES", "0")
        )

        # Message counters for validation
        self.processed_messages = []
        self.processed_count = 0
        self.error_count = 0
        self.duplicate_count = 0
        self.out_of_order_count = 0
        self.out_of_order_messages = []
        self.last_test_index = {}  # Por Message Group ID para rastrear ordem
        self.start_time = None

        # Métricas de performance
        self.processing_times = []  # Tempo de processamento de cada mensagem
        # Arquivos com ID único do consumer
        base_report_file = os.environ.get("SQS_CONSUMER_REPORT_FILE", CONSUMER_REPORT_FILE)
        # Remover extensão e adicionar ID
        base_name = base_report_file.replace(".json", "")
        self.report_file = f"{base_name}_{self.consumer_id}.json"
        self.lock = threading.Lock()  # Para thread-safety
        self.empty_polls = 0  # Contador de polls vazios

        # Métricas de paralelismo (Message Group IDs e windows)
        self.message_group_ids = set()  # Rastrear Message Group IDs únicos processados
        self.window_counts = {}  # Contador de mensagens por window number
        self.message_groups_detail = {}  # Detalhes por Message Group ID

        if not self.queue_url:
            raise ValueError("SQS_CONVERSATION_QUEUE_URL must be set")

        logger.info(f"[ConversationSQSConsumer] Initializing SQS client (region: {self.region})...")
        import sys

        sys.stdout.flush()

        # Initialize SQS client
        try:
            self.sqs_client = boto3.client("sqs", region_name=self.region)
            logger.info("[ConversationSQSConsumer] SQS client initialized successfully")
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"[ConversationSQSConsumer] Error initializing SQS client: {e}")
            sys.stdout.flush()
            raise

        logger.info(
            "[ConversationSQSConsumer] Initialized",
            extra={
                "consumer_id": self.consumer_id,
                "queue_url": self.queue_url,
                "region": self.region,
                "processing_delay": self.processing_delay,
                "report_file": self.report_file,
                "expected_total_messages": self.expected_total_messages,
            },
        )
        sys.stdout.flush()

        logger.info(f"[ConversationSQSConsumer] Consumer ID: {self.consumer_id}")
        sys.stdout.flush()

        logger.info(f"[ConversationSQSConsumer] Report file: {self.report_file}")
        sys.stdout.flush()

        if self.expected_total_messages > 0:
            logger.info(f"[ConversationSQSConsumer] Expected total messages: {self.expected_total_messages:,}")
            sys.stdout.flush()

    def start_consuming(self):
        """Start consuming messages from SQS FIFO queue."""
        import sys

        sys.stdout.flush()

        self.running = True
        self.start_time = time.time()
        logger.info(f"[{self.consumer_id}] Starting to consume messages")
        sys.stdout.flush()

        if self.expected_total_messages > 0:
            logger.info(f"[{self.consumer_id}] Expected total messages: {self.expected_total_messages:,}")
            sys.stdout.flush()

        # Iniciar atualização periódica do relatório
        logger.info(f"[{self.consumer_id}] Starting periodic report updates...")
        sys.stdout.flush()

        self.start_periodic_report_update()

        logger.info(f"[{self.consumer_id}] Entering message consumption loop...")
        sys.stdout.flush()

        while self.running:
            try:
                # Receive messages from FIFO queue (processar até 10 mensagens por vez para melhor throughput)
                logger.debug(f"[{self.consumer_id}] Polling SQS for messages...")
                response = self.sqs_client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,  # Processar até 10 mensagens por vez (máximo do SQS)
                    WaitTimeSeconds=20,
                    MessageAttributeNames=["All"],
                )

                messages = response.get("Messages", [])

                if not messages:
                    self.empty_polls += 1
                    # Log a cada 3 polls vazios (aproximadamente 1 minuto)
                    if self.empty_polls % 3 == 0:
                        elapsed = time.time() - self.start_time if self.start_time else 0
                        progress_info = ""
                        if self.expected_total_messages > 0:
                            remaining = max(0, self.expected_total_messages - self.processed_count)
                            progress_pct = (
                                (self.processed_count / self.expected_total_messages) * 100
                                if self.expected_total_messages > 0
                                else 0
                            )
                            progress_info = f" | Progress: {self.processed_count:,}/{self.expected_total_messages:,} ({progress_pct:.1f}%) | Remaining: {remaining:,}"
                        logger.info(
                            f"[{self.consumer_id}] Waiting for messages... "
                            f"(empty polls: {self.empty_polls}, processed: {self.processed_count:,}, "
                            f"duration: {elapsed:.0f}s)" + progress_info
                        )
                    continue

                # Reset contador quando recebe mensagens
                self.empty_polls = 0

                # Log quando recebe batch de mensagens
                if len(messages) > 1:
                    logger.info(f"[ConversationSQSConsumer] Received batch of {len(messages)} messages")

                # Processar todas as mensagens do batch
                successful_messages = []  # Para batch delete
                failed_messages = []

                for message in messages:
                    try:
                        # _process_message agora retorna receipt_handle se sucesso
                        receipt_handle = self._process_message(message)
                        if receipt_handle:
                            successful_messages.append(
                                {
                                    "Id": message.get("MessageId", ""),
                                    "ReceiptHandle": receipt_handle,
                                }
                            )
                    except Exception as e:
                        self.error_count += 1
                        failed_messages.append(message)
                        logger.error(
                            "[ConversationSQSConsumer] Error processing message",
                            extra={
                                "message_id": message.get("MessageId"),
                                "error": str(e),
                            },
                            exc_info=True,
                        )

                # Deletar mensagens processadas com sucesso em batch (mais eficiente)
                if successful_messages:
                    try:
                        # SQS permite até 10 mensagens por batch delete
                        for i in range(0, len(successful_messages), 10):
                            batch = successful_messages[i : i + 10]
                            entries = [
                                {"Id": str(idx), "ReceiptHandle": msg["ReceiptHandle"]} for idx, msg in enumerate(batch)
                            ]
                            self.sqs_client.delete_message_batch(
                                QueueUrl=self.queue_url,
                                Entries=entries,
                            )
                    except Exception as e:
                        logger.error(
                            "[ConversationSQSConsumer] Error deleting messages in batch",
                            extra={"error": str(e)},
                            exc_info=True,
                        )
                        # Fallback: deletar uma por uma
                        for msg in successful_messages:
                            try:
                                self.sqs_client.delete_message(
                                    QueueUrl=self.queue_url,
                                    ReceiptHandle=msg["ReceiptHandle"],
                                )
                            except Exception as e2:
                                logger.error(
                                    "[ConversationSQSConsumer] Error deleting message",
                                    extra={"error": str(e2), "message_id": msg.get("Id")},
                                )

                # Deletar mensagens que falharam individualmente (para não reprocessar)
                for message in failed_messages:
                    try:
                        self.sqs_client.delete_message(
                            QueueUrl=self.queue_url,
                            ReceiptHandle=message.get("ReceiptHandle"),
                        )
                    except Exception:
                        pass  # Ignorar erros ao deletar mensagens que falharam

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                error_message = e.response.get("Error", {}).get("Message", str(e))

                logger.error(
                    "[ConversationSQSConsumer] SQS receive error",
                    extra={"error_code": error_code, "error_message": error_message},
                    exc_info=True,
                )

                time.sleep(5)

            except Exception as e:
                logger.error(
                    "[ConversationSQSConsumer] Unexpected error",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                time.sleep(5)

    def stop_consuming(self):
        """Stop consuming messages."""
        self.running = False
        elapsed = time.time() - self.start_time if self.start_time else 0
        throughput = self.processed_count / elapsed if elapsed > 0 else 0

        # Atualizar relatório final
        self.update_report_file()

        logger.info("=" * 80)
        logger.info("[ConversationSQSConsumer] Stopping consumer")
        logger.info(f"Total processed: {self.processed_count}")
        logger.info(f"Total errors: {self.error_count}")
        logger.info(f"Total duplicates: {self.duplicate_count}")
        logger.info(f"Total out of order: {self.out_of_order_count}")
        logger.info(f"Total duration: {elapsed:.2f} seconds")
        logger.info(f"Throughput: {throughput:.2f} msg/s")
        logger.info(f"Final report saved to: {self.report_file}")
        logger.info("=" * 80)

    def calculate_percentiles(self, values: List[float], percentiles: List[float]) -> Dict[float, float]:
        """Calcula percentis de uma lista de valores."""
        if not values:
            return {p: 0.0 for p in percentiles}

        sorted_values = sorted(values)
        result = {}
        for p in percentiles:
            index = int(len(sorted_values) * p / 100)
            result[p] = sorted_values[min(index, len(sorted_values) - 1)]
        return result

    def generate_consolidated_report(self) -> Dict:
        """
        Gera relatório consolidado com métricas atuais.

        Similar ao relatório do publisher, mas para o consumer.
        """
        if not self.start_time:
            return {}

        elapsed_time = time.time() - self.start_time

        # Copiar dados rapidamente com lock mínimo
        with self.lock:
            processing_times_copy = self.processing_times.copy()
            processed_count = self.processed_count
            error_count = self.error_count
            duplicate_count = self.duplicate_count
            out_of_order_count = self.out_of_order_count
            running = self.running
            unique_message_groups = len(self.message_group_ids)
            window_counts_copy = self.window_counts.copy()
            message_groups_detail_copy = {
                group_id: {
                    "message_count": details["message_count"],
                    "indices_count": len(details["indices"]),
                    "first_seen": details["first_seen"],
                    "last_seen": details["last_seen"],
                }
                for group_id, details in self.message_groups_detail.items()
            }

        # Processar fora do lock
        if len(processing_times_copy) > 10000:
            processing_times_copy = processing_times_copy[-10000:]

        # Calcular percentis de tempo de processamento
        percentiles = self.calculate_percentiles(processing_times_copy, [50, 95, 99])

        report = {
            "test_summary": {
                "test_timestamp": datetime.utcnow().isoformat(),
                "total_processed": processed_count,
                "elapsed_time_seconds": elapsed_time,
            },
            "consumer_metrics": {
                "total_processed": processed_count,
                "total_errors": error_count,
                "total_duplicates": duplicate_count,
                "total_out_of_order": out_of_order_count,
                "duration_seconds": elapsed_time,
                "throughput_msg_per_sec": processed_count / elapsed_time if elapsed_time > 0 else 0,
                "processing_time": {
                    "avg_ms": sum(processing_times_copy) / len(processing_times_copy) if processing_times_copy else 0,
                    "min_ms": min(processing_times_copy) if processing_times_copy else 0,
                    "max_ms": max(processing_times_copy) if processing_times_copy else 0,
                    "p50_ms": percentiles.get(50, 0),
                    "p95_ms": percentiles.get(95, 0),
                    "p99_ms": percentiles.get(99, 0),
                },
                "processing_time_seconds": {
                    "avg": (sum(processing_times_copy) / len(processing_times_copy) / 1000)
                    if processing_times_copy
                    else 0,
                    "min": (min(processing_times_copy) / 1000) if processing_times_copy else 0,
                    "max": (max(processing_times_copy) / 1000) if processing_times_copy else 0,
                    "p50": percentiles.get(50, 0) / 1000,
                    "p95": percentiles.get(95, 0) / 1000,
                    "p99": percentiles.get(99, 0) / 1000,
                },
            },
            "validation": {
                "duplicates_detected": duplicate_count > 0,
                "out_of_order_detected": out_of_order_count > 0,
                "errors_detected": error_count > 0,
            },
            "parallelism_metrics": {
                "unique_message_group_ids": unique_message_groups,
                "unique_windows_processed": len(window_counts_copy),
                "messages_per_window": window_counts_copy,
                "avg_messages_per_window": (processed_count / len(window_counts_copy) if window_counts_copy else 0),
                "message_groups_detail": message_groups_detail_copy,
            },
            "status": {
                "running": running,
            },
        }

        return report

    def update_report_file(self):
        """Atualiza o arquivo de relatório consolidado."""
        try:
            report = self.generate_consolidated_report()
            if report:
                temp_file = f"{self.report_file}.tmp"
                with open(temp_file, "w") as f:
                    json.dump(report, f, indent=2)
                os.replace(temp_file, self.report_file)

                logger.info(
                    f"[Report] Relatório atualizado: {report['consumer_metrics']['total_processed']} mensagens processadas"
                )
        except Exception as e:
            logger.error(f"[Report] Erro ao atualizar relatório: {e}", exc_info=True)

    def start_periodic_report_update(self):
        """Inicia atualização periódica do relatório."""

        def update_loop():
            while self.running:
                time.sleep(REPORT_UPDATE_INTERVAL)
                if self.running:
                    self.update_report_file()

        report_thread = threading.Thread(target=update_loop, daemon=True)
        report_thread.start()
        logger.info(f"[Report] Atualização periódica iniciada (a cada {REPORT_UPDATE_INTERVAL}s)")

    def get_stats(self) -> dict:
        """Get consumer statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        with self.lock:
            return {
                "consumer_id": self.consumer_id,
                "processed_count": self.processed_count,
                "error_count": self.error_count,
                "duplicate_count": self.duplicate_count,
                "out_of_order_count": self.out_of_order_count,
                "out_of_order_messages": self.out_of_order_messages,
                "duration_seconds": elapsed,
                "throughput_msg_per_sec": self.processed_count / elapsed if elapsed > 0 else 0,
                "processed_messages": self.processed_messages,  # Apenas campos essenciais (já otimizado)
                "note": "Only essential fields stored (test_index, correlation_id, message_group_id, window_number, processed_at, processing_time_ms) to reduce file size while maintaining full validation capability",
            }

    def _process_message(self, message: Dict) -> Optional[str]:
        """
        Process a single message from SQS.

        Args:
            message: SQS message dict

        Returns:
            ReceiptHandle if message was processed successfully, None otherwise
        """
        message_id = message.get("MessageId")
        receipt_handle = message.get("ReceiptHandle")
        body = message.get("Body", "")
        attributes = message.get("MessageAttributes", {})

        # Medir tempo de processamento
        process_start_time = time.time()

        # Log apenas a cada 100 mensagens para não poluir (batch processing é mais rápido)
        if self.processed_count % 100 != 0:
            logger.debug(
                "[ConversationSQSConsumer] Processing message",
                extra={"message_id": message_id},
            )

        try:
            event_data = json.loads(body)

            event_type = attributes.get("event_type", {}).get("StringValue") or event_data.get("event_type")

            # Extrair Message Group ID e window do timestamp da mensagem
            message_group_id = None
            window_number = None
            try:
                message_data = event_data.get("data", {})
                message_info = message_data.get("message", {})
                created_at_str = message_info.get("created_at")

                if created_at_str:
                    # Parse timestamp e calcular window (mesma lógica do publisher)
                    timestamp_str = created_at_str.replace("Z", "+00:00")
                    msg_timestamp = datetime.fromisoformat(timestamp_str)
                    if msg_timestamp.tzinfo is None:
                        msg_timestamp = msg_timestamp.replace(tzinfo=timezone.utc)
                    else:
                        msg_timestamp = msg_timestamp.astimezone(timezone.utc)

                    timestamp_seconds = int(msg_timestamp.timestamp())
                    window_number = timestamp_seconds // 20  # 20-second windows

                    # Construir Message Group ID (mesma lógica do publisher)
                    project_uuid = message_data.get("project_uuid", "")
                    contact_urn = message_data.get("contact_urn", "")
                    channel_uuid = message_data.get("channel_uuid")

                    base_id = f"{project_uuid}:{contact_urn}"
                    if channel_uuid:
                        base_id += f":{channel_uuid}"
                    message_group_id = f"{base_id}:window_{window_number}"
            except Exception as e:
                logger.debug(f"[ConversationSQSConsumer] Error extracting Message Group ID: {e}")

            # Check for duplicates
            correlation_id = event_data.get("correlation_id")
            if correlation_id in [msg.get("correlation_id") for msg in self.processed_messages]:
                self.duplicate_count += 1
                logger.warning(
                    "[ConversationSQSConsumer] Duplicate message detected",
                    extra={"correlation_id": correlation_id, "message_id": message_id},
                )
                # Return None para não deletar aqui (será deletado no batch)
                return None  # Duplicata não será processada

            # Validar ordem das mensagens baseado no test_index
            # IMPORTANTE: Com paralelismo, ordem é validada por Message Group ID, não globalmente
            test_index = event_data.get("data", {}).get("test_index")
            if test_index is not None:
                # Usar Message Group ID como chave para rastrear ordem (não apenas project:contact)
                # Isso garante que ordem seja validada dentro de cada janela/window
                if message_group_id:
                    group_key = message_group_id  # Usar Message Group ID completo
                else:
                    # Fallback: usar project:contact se não conseguir extrair Message Group ID
                    project_uuid = event_data.get("data", {}).get("project_uuid", "")
                    contact_urn = event_data.get("data", {}).get("contact_urn", "")
                    group_key = f"{project_uuid}:{contact_urn}"

                # Verificar se a mensagem está em ordem dentro do grupo
                # IMPORTANTE: Com paralelismo, cada grupo tem seu próprio rastreamento de índices
                # Não comparamos test_index globalmente, apenas dentro de cada grupo
                # Com paralelismo, cada mensagem está em um grupo diferente, então não há problema
                # de ordem entre grupos diferentes - apenas dentro do mesmo grupo
                with self.lock:
                    # Obter último índice processado para este grupo específico
                    last_index = self.last_test_index.get(group_key, -1)

                    # IMPORTANTE: Com paralelismo (--parallelism), cada mensagem está em um grupo diferente
                    # então não devemos validar ordem globalmente. Apenas validar se dentro do mesmo
                    # grupo há mensagens fora de ordem (o que não deveria acontecer com paralelismo).
                    # Se last_index == -1, é a primeira mensagem deste grupo, então está OK.
                    if last_index != -1 and test_index <= last_index:
                        # Mensagem fora de ordem detectada DENTRO do mesmo grupo!
                        # Isso só acontece se duas mensagens do mesmo grupo chegam fora de ordem
                        self.out_of_order_count += 1
                        out_of_order_info = {
                            "test_index": test_index,
                            "last_index": last_index,
                            "message_id": message_id,
                            "group_key": group_key,
                            "correlation_id": correlation_id,
                            "timestamp": time.time(),
                        }
                        self.out_of_order_messages.append(out_of_order_info)

                        logger.warning(
                            "[ConversationSQSConsumer] Message out of order detected within group",
                            extra={
                                "test_index": test_index,
                                "last_index": last_index,
                                "group_key": group_key,
                                "message_id": message_id,
                                "expected_next": last_index + 1,
                            },
                        )
                    else:
                        # Ordem correta dentro do grupo (ou primeira mensagem do grupo)
                        # Atualizar último índice processado para este grupo
                        self.last_test_index[group_key] = test_index

            if event_type == "message.received":
                self._handle_message_received(event_data)
            elif event_type == "message.sent":
                self._handle_message_sent(event_data)
            else:
                logger.warning(
                    "[ConversationSQSConsumer] Unknown event type",
                    extra={"event_type": event_type, "message_id": message_id},
                )

            # Simulate processing delay (e.g., DB insertion)
            time.sleep(self.processing_delay)

            # Calcular tempo de processamento
            process_end_time = time.time()
            processing_time_ms = (process_end_time - process_start_time) * 1000

            # Track processed message
            with self.lock:
                self.processed_count += 1
                self.processing_times.append(processing_time_ms)

                # Limitar tamanho da lista para evitar overhead
                if len(self.processing_times) > 20000:
                    self.processing_times = self.processing_times[-10000:]

                # Rastrear Message Group IDs e windows para métricas de paralelismo
                if message_group_id:
                    self.message_group_ids.add(message_group_id)
                    self.window_counts[window_number] = self.window_counts.get(window_number, 0) + 1

                    # Detalhes por Message Group ID
                    if message_group_id not in self.message_groups_detail:
                        self.message_groups_detail[message_group_id] = {
                            "message_count": 0,
                            "indices": [],
                            "first_seen": time.time(),
                            "last_seen": time.time(),
                        }
                    self.message_groups_detail[message_group_id]["message_count"] += 1
                    if test_index is not None:
                        self.message_groups_detail[message_group_id]["indices"].append(test_index)
                    self.message_groups_detail[message_group_id]["last_seen"] = time.time()

                # Salvar apenas campos essenciais para validação (reduz tamanho do arquivo drasticamente)
                # Mantém todos os dados necessários para validação completa
                essential_message_data = {
                    "test_index": test_index,
                    "correlation_id": correlation_id,
                    "message_group_id": message_group_id,
                    "window_number": window_number,
                    "processed_at": time.time(),
                    "processing_time_ms": processing_time_ms,
                }
                self.processed_messages.append(essential_message_data)

            # Log progress every 100 messages
            if self.processed_count % 100 == 0:
                elapsed = time.time() - self.start_time if self.start_time else 0
                throughput = self.processed_count / elapsed if elapsed > 0 else 0
                avg_processing_time = (
                    sum(self.processing_times[-100:]) / len(self.processing_times[-100:])
                    if len(self.processing_times) >= 100
                    else sum(self.processing_times) / len(self.processing_times)
                    if self.processing_times
                    else 0
                )

                # Calcular progresso se total esperado foi informado
                progress_info = ""
                if self.expected_total_messages > 0:
                    remaining = max(0, self.expected_total_messages - self.processed_count)
                    progress_pct = (self.processed_count / self.expected_total_messages) * 100
                    progress_info = f" | Progress: {self.processed_count:,}/{self.expected_total_messages:,} ({progress_pct:.1f}%) | Remaining: {remaining:,}"

                logger.info(
                    f"[{self.consumer_id}] Processed {self.processed_count:,} messages "
                    f"(throughput: {throughput:.2f} msg/s, avg processing: {avg_processing_time:.2f}ms, "
                    f"duplicates: {self.duplicate_count}, out of order: {self.out_of_order_count})" + progress_info
                )

            # Retornar receipt_handle para deleção em batch (mais eficiente)
            # Log apenas a cada 100 mensagens
            if self.processed_count % 100 == 0:
                logger.debug(
                    "[ConversationSQSConsumer] Message processed successfully",
                    extra={"message_id": message_id, "event_type": event_type},
                )

            return receipt_handle  # Retornar para deleção em batch

        except json.JSONDecodeError as e:
            logger.error(
                "[ConversationSQSConsumer] Invalid JSON in message body",
                extra={"message_id": message_id, "error": str(e)},
            )
            self.sqs_client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)

        except Exception as e:
            logger.error(
                "[ConversationSQSConsumer] Error processing message",
                extra={"message_id": message_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def _handle_message_received(self, event_data: Dict):
        """
        Handle message.received event.

        Args:
            event_data: Event data dictionary
        """
        from conversation_ms.services.message_service import MessageService

        logger.info(
            "[ConversationSQSConsumer] Handling message.received event",
            extra={
                "correlation_id": event_data.get("correlation_id"),
                "project_uuid": event_data.get("data", {}).get("project_uuid"),
                "contact_urn": event_data.get("data", {}).get("contact_urn"),
            },
        )

        # Processar mensagem usando MessageService
        message_service = MessageService()
        message_service.process_message_received(event_data)

    def _handle_message_sent(self, event_data: Dict):
        """
        Handle message.sent event.

        Args:
            event_data: Event data dictionary
        """
        from conversation_ms.services.message_service import MessageService

        logger.info(
            "[ConversationSQSConsumer] Handling message.sent event",
            extra={
                "correlation_id": event_data.get("correlation_id"),
                "project_uuid": event_data.get("data", {}).get("project_uuid"),
                "contact_urn": event_data.get("data", {}).get("contact_urn"),
            },
        )

        # Processar mensagem usando MessageService
        message_service = MessageService()
        message_service.process_message_sent(event_data)
