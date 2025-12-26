#!/usr/bin/env python
"""
Script de teste de carga para SQS com batch sending.

Envia mensagens em batches de 10 até 100k mensagens para testar escalabilidade e confiabilidade do SQS.
Atualiza o relatório consolidado a cada 1 minuto durante a execução.
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import django

from nexus.event_driven.publisher.sqs_publisher import SQSPublisher

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")
django.setup()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constantes
SQS_BATCH_SIZE = 10  # Limite máximo do SQS para SendMessageBatch
REPORT_UPDATE_INTERVAL = 60  # Atualizar relatório a cada 60 segundos
REPORT_FILE = "sqs_test_report_consolidated.json"


class SQSLoadTester:
    """Teste de carga para SQS com batch sending."""

    def __init__(self, report_file: str = REPORT_FILE, use_parallelism: bool = False):
        self.publisher = SQSPublisher()
        self.sent_messages = []
        self.latencies = []
        self.report_file = report_file
        self.start_time = None
        self.total_sent = 0
        self.total_failed = 0
        self.batches_processed = 0
        self.total_batches = 0
        self.start_index = 0  # Índice inicial (para continuar de onde parou)
        self.lock = threading.Lock()  # Para thread-safety
        self.report_timer = None
        self.running = False
        self.use_parallelism = use_parallelism  # Flag para testar paralelismo

    def generate_test_message(self, index: int, use_parallelism: bool = False) -> dict:
        """
        Gera uma mensagem de teste.

        IMPORTANTE: Usa o mesmo project_uuid, contact_urn e channel_uuid para todas as mensagens.

        Com window-based Message Group ID (20 segundos):
        - Se use_parallelism=False: Todas as mensagens terão timestamps próximos (mesma janela)
          → Mesmo Message Group ID → Processamento sequencial (ordem garantida)
        - Se use_parallelism=True: Mensagens terão timestamps espaçados (janelas diferentes)
          → Diferentes Message Group IDs → Processamento paralelo possível
        """
        correlation_id = str(uuid.uuid4())

        # Usar valores fixos para garantir mesmo base Message Group ID
        TEST_PROJECT_UUID = "test-project-uuid-12345"
        TEST_CONTACT_URN = "whatsapp:+5511999999999"
        TEST_CHANNEL_UUID = "test-channel-uuid-12345"

        # Gerar timestamp baseado no índice para testar paralelismo
        if use_parallelism:
            # Espaçar timestamps em 25 segundos para garantir janelas diferentes (20s window)
            # Isso permite testar paralelismo entre diferentes Message Group IDs
            from datetime import timedelta

            base_time = datetime.utcnow()
            message_timestamp = base_time + timedelta(seconds=index * 25)
        else:
            # Todas as mensagens com timestamp próximo (mesma janela de 20s)
            # Isso garante ordem sequencial para validação
            message_timestamp = datetime.utcnow()

        return {
            "event_type": "message.received",
            "correlation_id": correlation_id,
            "timestamp": message_timestamp.isoformat(),
            "data": {
                "project_uuid": TEST_PROJECT_UUID,
                "contact_urn": TEST_CONTACT_URN,
                "channel_uuid": TEST_CHANNEL_UUID,
                "message": {
                    "message_id": str(uuid.uuid4()),
                    "text": f"Test message {index}",
                    "source": "user",
                    "created_at": message_timestamp.isoformat(),
                },
                "test_index": index,  # Sequencial: 0, 1, 2, 3... para validação de ordem
            },
        }

    def prepare_batch_messages(self, start_index: int, batch_size: int) -> List[Dict]:
        """
        Prepara uma lista de mensagens formatadas para send_message_batch.

        Args:
            start_index: Índice inicial
            batch_size: Tamanho do batch (máximo 10)

        Returns:
            Lista de dicts formatados para send_message_batch
        """
        messages = []
        for i in range(min(batch_size, SQS_BATCH_SIZE)):
            index = start_index + i
            msg = self.generate_test_message(index, use_parallelism=self.use_parallelism)
            messages.append(
                {
                    "body": msg,
                    "event_type": "message.received",
                    "project_uuid": msg["data"]["project_uuid"],
                    "contact_urn": msg["data"]["contact_urn"],
                    "channel_uuid": msg["data"]["channel_uuid"],
                    "correlation_id": msg["correlation_id"],
                }
            )
        return messages

    def send_batch(self, start_index: int, batch_size: int) -> dict:
        """
        Envia um batch de mensagens usando SendMessageBatch.

        Args:
            start_index: Índice inicial das mensagens
            batch_size: Tamanho do batch (máximo 10)

        Returns:
            Dict com estatísticas do batch
        """
        batch_start_time = time.time()

        # Preparar mensagens para o batch
        messages = self.prepare_batch_messages(start_index, batch_size)

        # Enviar batch
        successful_count, failed_count, message_ids = self.publisher.send_message_batch(messages)

        batch_end_time = time.time()
        batch_duration = batch_end_time - batch_start_time
        batch_latency_ms = batch_duration * 1000  # Latência total do batch

        # Atualizar estatísticas
        with self.lock:
            self.total_sent += successful_count
            self.total_failed += failed_count
            self.batches_processed += 1
            self.latencies.append(batch_latency_ms)

            if len(self.latencies) > 20000:
                self.latencies = self.latencies[-10000:]

            # Salvar metadados das mensagens enviadas
            for idx, msg_data in enumerate(messages):
                if idx < successful_count:
                    self.sent_messages.append(
                        {
                            "index": start_index + idx,
                            "message_id": message_ids[idx] if idx < len(message_ids) else None,
                            "correlation_id": msg_data["correlation_id"],
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

        stats = {
            "batch_start": start_index,
            "batch_end": start_index + batch_size - 1,
            "successful": successful_count,
            "failed": failed_count,
            "duration_seconds": batch_duration,
            "latency_ms": batch_latency_ms,
            "throughput_msg_per_sec": successful_count / batch_duration if batch_duration > 0 else 0,
        }

        logger.info(
            f"Batch {start_index}-{start_index + batch_size - 1}: "
            f"{successful_count} successful, {failed_count} failed, "
            f"latency: {batch_latency_ms:.2f}ms, "
            f"throughput: {stats['throughput_msg_per_sec']:.2f} msg/s"
        )

        return stats

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

        Otimizado para não impactar latência:
        - Lock mínimo (apenas para copiar dados)
        - Processamento fora do lock
        - Limitação de dados processados
        """
        if not self.start_time:
            return {}

        elapsed_time = time.time() - self.start_time

        # Copiar dados rapidamente com lock mínimo para evitar race conditions
        # e não bloquear a thread principal durante processamento
        with self.lock:
            # Criar cópias rápidas dos dados para processar fora do lock
            latencies_copy = self.latencies.copy()  # Shallow copy é rápido
            total_sent = self.total_sent
            total_failed = self.total_failed
            batches_processed = self.batches_processed
            total_batches = self.total_batches
            start_index = self.start_index
            running = self.running

        # Processar fora do lock para não bloquear a thread principal
        # Limitar cálculo de percentis para evitar overhead com listas muito grandes
        if len(latencies_copy) > 10000:
            # Para listas grandes, usar apenas últimas 10k latências (mais representativas)
            latencies_copy = latencies_copy[-10000:]

        # Calcular percentis de latência (fora do lock)
        percentiles = self.calculate_percentiles(latencies_copy, [50, 95, 99])

        # Calcular previsão de tempo restante baseado na taxa de processamento atual
        eta_seconds = None
        eta_formatted = None
        progress_percent = 0.0
        batches_per_second = 0.0

        if total_batches > 0 and batches_processed > 0 and elapsed_time > 0:
            progress_percent = (batches_processed / total_batches) * 100
            batches_per_second = batches_processed / elapsed_time
            batches_remaining = total_batches - batches_processed

            if batches_per_second > 0:
                eta_seconds = batches_remaining / batches_per_second
                # Formatar ETA em horas:minutos:segundos
                hours = int(eta_seconds // 3600)
                minutes = int((eta_seconds % 3600) // 60)
                seconds = int(eta_seconds % 60)
                eta_formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        report = {
            "test_summary": {
                "test_timestamp": datetime.utcnow().isoformat(),
                "total_messages": total_sent + total_failed,
                "total_messages_sent_this_run": total_sent + total_failed,
                "start_index": start_index,
                "batch_size": SQS_BATCH_SIZE,
                "elapsed_time_seconds": elapsed_time,
            },
            "publisher_metrics": {
                "total_sent": total_sent,
                "total_failed": total_failed,
                "duration_seconds": elapsed_time,
                "throughput_msg_per_sec": total_sent / elapsed_time if elapsed_time > 0 else 0,
                "latency": {
                    "avg_ms": sum(latencies_copy) / len(latencies_copy) if latencies_copy else 0,
                    "min_ms": min(latencies_copy) if latencies_copy else 0,
                    "max_ms": max(latencies_copy) if latencies_copy else 0,
                    "p50_ms": percentiles.get(50, 0),
                    "p95_ms": percentiles.get(95, 0),
                    "p99_ms": percentiles.get(99, 0),
                },
                "latency_seconds": {
                    "avg": (sum(latencies_copy) / len(latencies_copy) / 1000) if latencies_copy else 0,
                    "min": (min(latencies_copy) / 1000) if latencies_copy else 0,
                    "max": (max(latencies_copy) / 1000) if latencies_copy else 0,
                    "p50": percentiles.get(50, 0) / 1000,
                    "p95": percentiles.get(95, 0) / 1000,
                    "p99": percentiles.get(99, 0) / 1000,
                },
            },
            "status": {
                "running": running,
                "progress_percent": round(progress_percent, 2),
                "batches_processed": batches_processed,
                "total_batches": total_batches,
                "batches_per_second": round(batches_per_second, 2),
                "eta_seconds": round(eta_seconds, 2) if eta_seconds else None,
                "eta_formatted": eta_formatted,
            },
        }

        return report

    def update_report_file(self):
        """
        Atualiza o arquivo de relatório consolidado.

        Otimizado para I/O não-bloqueante:
        - Escreve em arquivo temporário primeiro
        - Renomeia atomicamente (mais rápido e seguro)
        """
        try:
            report = self.generate_consolidated_report()
            if report:
                temp_file = f"{self.report_file}.tmp"
                with open(temp_file, "w") as f:
                    json.dump(report, f, indent=2)
                os.replace(temp_file, self.report_file)

                # Log com informações de progresso e ETA
                status = report.get("status", {})
                eta_info = ""
                if status.get("eta_formatted"):
                    eta_info = f", ETA: {status['eta_formatted']}"
                logger.info(
                    f"[Report] Relatório atualizado: {report['publisher_metrics']['total_sent']} mensagens enviadas "
                    f"({status.get('progress_percent', 0):.1f}% completo{eta_info})"
                )
        except Exception as e:
            logger.error(f"[Report] Erro ao atualizar relatório: {e}", exc_info=True)

    def find_last_sent_index(self) -> int:
        """
        Encontra o último índice enviado baseado em arquivos de resultados existentes.

        Returns:
            Último índice enviado + 1 (para continuar), ou 0 se não houver resultados anteriores
        """
        last_index = -1

        # Tentar ler do relatório consolidado
        if os.path.exists(self.report_file):
            try:
                with open(self.report_file) as f:
                    report = json.load(f)
                    total_sent = report.get("publisher_metrics", {}).get("total_sent", 0)
                    if total_sent > 0:
                        # O test_index começa em 0, então total_sent = último índice + 1
                        last_index = total_sent - 1
                        logger.info(f"[Resume] Encontrado relatório consolidado: {total_sent} mensagens já enviadas")
            except Exception as e:
                logger.warning(f"[Resume] Erro ao ler relatório consolidado: {e}")

        # Tentar ler de arquivos de resultados anteriores
        results_dir = Path(".")
        result_files = sorted(
            results_dir.glob("sqs_load_test_results_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for result_file in result_files:
            try:
                with open(result_file) as f:
                    results = json.load(f)
                    sent_messages = results.get("sent_messages", [])
                    if sent_messages:
                        # Encontrar o maior índice
                        max_index = max(msg.get("index", -1) for msg in sent_messages)
                        if max_index > last_index:
                            last_index = max_index
                            logger.info(
                                f"[Resume] Encontrado arquivo de resultados: {result_file.name}, "
                                f"último índice: {max_index}"
                            )
            except Exception as e:
                logger.warning(f"[Resume] Erro ao ler {result_file}: {e}")
                continue

        if last_index >= 0:
            logger.info(
                f"[Resume] Continuando a partir do índice {last_index + 1} " f"({last_index + 1} mensagens já enviadas)"
            )
            return last_index + 1
        else:
            logger.info("[Resume] Nenhum resultado anterior encontrado, iniciando do zero")
            return 0

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

    def run_load_test(self, total_messages: int, resume: bool = True):
        """
        Executa teste de carga completo com batch sending.

        Args:
            total_messages: Total de mensagens a enviar (até 100k)
            resume: Se True, continua de onde parou. Se False, inicia do zero.
        """
        if total_messages > 100000:
            logger.warning(f"Total de mensagens ({total_messages}) excede 100k, limitando a 100k")
            total_messages = 100000

        # Verificar se deve continuar de onde parou
        if resume:
            self.start_index = self.find_last_sent_index()
        else:
            self.start_index = 0
            logger.info("[Resume] Modo resume desabilitado, iniciando do zero")

        # Ajustar total de mensagens se já foram enviadas algumas
        remaining_messages = total_messages - self.start_index
        if remaining_messages <= 0:
            logger.info(
                f"[Resume] Todas as {total_messages} mensagens já foram enviadas "
                f"(último índice: {self.start_index - 1})"
            )
            return

        logger.info(
            f"Starting load test: {remaining_messages} mensagens restantes "
            f"(índice {self.start_index} até {total_messages - 1}) "
            f"em batches de {SQS_BATCH_SIZE}"
        )

        self.start_time = time.time()
        self.running = True

        # Calcular número de batches necessários para as mensagens restantes
        num_batches = (remaining_messages + SQS_BATCH_SIZE - 1) // SQS_BATCH_SIZE
        self.total_batches = num_batches

        # Iniciar atualização periódica do relatório
        self.start_periodic_report_update()

        try:
            for batch_num in range(num_batches):
                start_index = self.start_index + (batch_num * SQS_BATCH_SIZE)
                current_batch_size = min(SQS_BATCH_SIZE, total_messages - start_index)

                if batch_num % 100 == 0:
                    logger.info(
                        f"Progress: Batch {batch_num + 1}/{num_batches} "
                        f"({self.start_index + self.total_sent}/{total_messages} mensagens enviadas no total)"
                    )

                self.send_batch(start_index, current_batch_size)

                # Pequena pausa entre batches para não sobrecarregar
                if batch_num < num_batches - 1:
                    time.sleep(0.01)

        finally:
            self.running = False

        test_end_time = time.time()
        total_duration = test_end_time - self.start_time

        # Estatísticas finais
        logger.info("=" * 80)
        logger.info("LOAD TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"Total messages: {total_messages}")
        logger.info(f"Total successful: {self.total_sent}")
        logger.info(f"Total failed: {self.total_failed}")
        logger.info(f"Total duration: {total_duration:.2f} seconds")
        logger.info(f"Overall throughput: {self.total_sent / total_duration:.2f} msg/s")
        if self.latencies:
            logger.info(f"Average latency: {sum(self.latencies) / len(self.latencies):.2f}ms")
            logger.info(f"Min latency: {min(self.latencies):.2f}ms")
            logger.info(f"Max latency: {max(self.latencies):.2f}ms")
        logger.info("=" * 80)

        # Salvar resultados finais
        results_file = f"sqs_load_test_results_{int(time.time())}.json"
        results = {
            "test_timestamp": datetime.utcnow().isoformat(),
            "total_messages": total_messages,
            "batch_size": SQS_BATCH_SIZE,
            "total_successful": self.total_sent,
            "total_failed": self.total_failed,
            "total_duration_seconds": total_duration,
            "overall_throughput_msg_per_sec": self.total_sent / total_duration if total_duration > 0 else 0,
            "latency_stats": {
                "avg_ms": sum(self.latencies) / len(self.latencies) if self.latencies else 0,
                "min_ms": min(self.latencies) if self.latencies else 0,
                "max_ms": max(self.latencies) if self.latencies else 0,
                "p50_ms": sorted(self.latencies)[len(self.latencies) // 2] if self.latencies else 0,
                "p95_ms": sorted(self.latencies)[int(len(self.latencies) * 0.95)] if self.latencies else 0,
                "p99_ms": sorted(self.latencies)[int(len(self.latencies) * 0.99)] if self.latencies else 0,
            },
            "sent_messages": self.sent_messages,
        }

        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Results saved to: {results_file}")

        # Atualizar relatório final
        self.update_report_file()
        logger.info(f"Final report saved to: {self.report_file}")

        return results


def main():
    parser = argparse.ArgumentParser(description="SQS Load Test Script with Batch Sending")
    parser.add_argument(
        "--messages",
        type=int,
        default=1000,
        help="Total number of messages to send (default: 1000, max: 100000)",
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=REPORT_FILE,
        help=f"Path to consolidated report file (default: {REPORT_FILE})",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Don't resume from previous run, start from zero",
    )
    parser.add_argument(
        "--parallelism",
        action="store_true",
        help="Enable parallelism test: messages will have different timestamps (25s apart) "
        "to test parallel processing with different Message Group IDs. "
        "Without this flag, all messages use same timestamp (sequential processing).",
    )

    args = parser.parse_args()

    tester = SQSLoadTester(report_file=args.report_file, use_parallelism=args.parallelism)
    tester.run_load_test(args.messages, resume=not args.no_resume)


if __name__ == "__main__":
    main()
