import concurrent.futures
import logging
import os
import re
from datetime import datetime

import pandas as pd
import pendulum
import requests
from django.conf import settings
from django.core.mail import EmailMessage
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm

logger = logging.getLogger(__name__)


# Constants
API_VERSION = "v2"
CONTACTS_ENDPOINT = "contacts.json"
MESSAGES_ENDPOINT = "messages.json"
DATE_FORMAT_API = "%Y-%m-%dT%H:%M:%S.%f%z"  # Assumes TZ info is present like 'Z' or +HH:MM
DATE_FORMAT_API_FALLBACK = "%Y-%m-%dT%H:%M:%S"
DATE_FORMAT_BR = "%d/%m/%Y %H:%M:%S"
MAX_WORKERS = 10

BASE_URL = settings.FLOWS_REST_ENDPOINT

# --- Classification Groups ---
groups = {
    "Cancelamentos/Estorno": [
        "Cancelamento",
        "Cancelar para aproveitar outra promoção",
        "Cancelamento por arrependimento",
        "Cancelamento por insatisfação",
        "Chargeback",
        "Solicitado o estorno",
        "Estorno do valor do frete",
        "Estorno realizado",
        "Cancelou mas não estornou - Estorno solicitado",
        "Chatbot Retido no Chatbot",
        "Cliente com dúvidas sobre onde e como comprar?",
        "Quiosque",
        "Entrega internacional",
        "Compras",
        "Cliente solicita algo impertinente ao SAC?",
        "Compra realizada em outro site",
        "E-mail recrutamento",
        "Cliente solicita devolução",
        "Insatisfação",
        "Defeito/Má qualidade - Sem devolução (exceção)",
        "Prazo excedido para devolução",
        "Desistiu de devolver",
        "Arrependimento",
        "Avaria - Sem devolução (exceção)",
        "Itens errados - Link de pagamento",
        "Defeito/Má qualidade - Estorno",
        "Defeito/Má qualidade - Envio",
        "Avaria - Envio",
        "Avaria - Estorno",
        "Itens errados - Estorno",
        "Itens errados - Envio",
    ],
    "Dados cadastrais": [
        "Alteração de e-mail",
        "Cadastrou endereço de entrega errado",
        "Erro no cadastro",
        "Assinatura",
        "Dados insuficientes",
        "Cadastro",
        "Dúvida momento da compra",
        "Disponibilidade de produto",
        "Ajuda para comprar",
        "Valor do frete",
        "Valor do produto alterado",
        "Dúvida sobre regulamento da promoção",
        "Contraindicações",
        "Composição",
        "Dúvidas sobre comercial",
        "Franquias",
        "Revenda",
        "Parceria/Publi - Orientada",
        "Dúvidas sobre utilização? Recomendações de uso",
        "Encerramento BOT Encerramento BOT",
        "Erro mensageria",
        "Disparo recebido",
        "Erro de disparo",
    ],
    "Experiência do cliente?": [
        "Atrito - Envio de presente (exceção)",
        "Atrito - Cupom de desconto",
        "Brinde",
        "Reclamações - Produtos indisponíveis",
        "Reclamações - Atendimento",
        "Reclamações - Qualidade do produto",
        "Reclamações - Mídias Sociais",
        "Reclamações - Processos",
        "Reclamações - Quiosques",
        "Reclamações - Logística",
        "Falta de interação com cliente? Qual motivo?",
        "SPAM",
        "Cliente atendido por outro canal/ Especialista",
        "Interação",
        "Fãs/Trote",
        "Canais de atendimento",
        "Agradecimentos/Elogios",
        "Menção instagram",
        "Término de expediente",
    ],
    "LIVE": [
        "Interagiu com ação LIVE",
    ],
    "Preventivo Transportes": [
        "Problemas com a entrega?",
        "Solicitada reentrega",
        "Itens faltantes – Estorno",
        "Devolvido ao remetente",
        "Aguardando retirada",
        "Extravio - Envio",
        "Embalagem violada",
        "Reenvio",
        "Atraso com o transportador",
        "Avaria por transporte",
        "Resolvido pelo transportador",
        "Envio",
        "Solicitado o envio",
        "Pesagem correta",
        "Itens faltantes - Envio",
        "Acareação - Não reconhece entrega",
        "Pesagem divergente",
        "Sem movimentação",
        "Insucesso de entrega",
        "Em devolução",
        "Resolvido para devolução",
        "Extravio - Estorno",
        "Redespacho - Correios",
    ],
    "Promoções": [
        "Brinde não incluso",
        "Promoções ativas no momento",
        "Reações do produto",
        "Alergia - Com laudo",
        "Reações do produto",
        "Alergia",
        "Resoluções RA",
        "ACOMPANHAMENTO - RECLAME AQUI",
        "Resoluções RA",
        "Reclame Aqui",
    ],
    "Sem grupo": [
        "Teste sistema (utilização interna)",
        "Site fora do ar (Incidente Outubro 2024)",
        "Site",
        "WPink Suplementos",
        "Site Fake",
        "Produto indisponível no site",
        "Site",
        "Plataforma",
        "Erros no site",
        "Status de pagamento",
        "Pagamento pendente",
        "Erros no pagamento",
    ],
    "Status de solicitação": [
        "Solicitado dados bancários",
        "Solicitação fora do prazo - Movidesk",
        "Troquecommerce",
        "Solicitação fora do prazo - Troquecommerce",
        "Solicitação dentro do prazo - Troquecommerce",
        "Não utilizou o código de postagem",
        "Solicitação dentro do prazo - Movidesk",
        "Status do pedido",
        "Pedido não localizado",
        "Cancelamento automático – Mediador financeiro",
        "Barragem de entrega",
        "Dentro do prazo",
        "Desistiu de cancelar",
        "Pedido entregue - Consta em sistema",
        "Fora do prazo",
        "Fora do prazo - Aguardando estoque",
        "Fora do prazo - Ruptura",
        "Troca de um produto por outro",
        "Informativo de rastreio",
        "Confirmação de entrega",
        "Confirmação de compra",
        "Solicita NF",
        "Chatbot- Troca do Item",
        "Chatbot - Desejou aguardar",
    ],
}
# --- End Classification Groups ---


def format_datetime_br(datetime_str):
    """Formats an ISO 8601 string (with potential Z) to Brazilian format."""
    if not datetime_str:
        return None
    try:
        if datetime_str.endswith("Z"):
            datetime_str = datetime_str[:-1] + "+00:00"
        dt_obj = datetime.strptime(datetime_str, DATE_FORMAT_API)
    except ValueError:
        try:
            dt_obj = datetime.strptime(datetime_str, DATE_FORMAT_API_FALLBACK)
        except ValueError:
            try:
                dt_obj = datetime.strptime(datetime_str.replace("T", " "), DATE_FORMAT_API_FALLBACK)
            except ValueError:
                logger.error("Could not parse date string", extra={"datetime_str": datetime_str})
                return None
    return dt_obj.strftime(DATE_FORMAT_BR)


def get_paginated_data(url, headers):
    """Fetches all data from a paginated API endpoint."""
    results = []
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        results.extend(data.get("results", []))
        url = data.get("next")
    return results


def get_contact_messages(contact_uuid, base_url, headers):
    """Fetches all messages for a specific contact."""
    messages_url = (
        f"{base_url}/api/{API_VERSION}/{MESSAGES_ENDPOINT}?contact={contact_uuid}&after=2025-05-15T00:00:00.000Z"
    )
    return get_paginated_data(messages_url, headers)


def classify_conversation(messages_list, groups_dict, similarity_threshold=0.1):
    """Classifies conversation based on TF-IDF cosine similarity to subgroup phrases."""
    if not messages_list:
        return "Não Classificado", "Sem Mensagens"

    conversation_text = " ".join([msg.get("text", "") for msg in messages_list if msg.get("text")]).lower()

    if not conversation_text.strip():
        return "Não Classificado", "Mensagens Sem Texto"

    all_subgroups_lower = []
    group_mapping = []
    for group, subgroups in groups_dict.items():
        for subgroup in subgroups:
            all_subgroups_lower.append(subgroup.lower())
            group_mapping.append((group, subgroup))

    if not all_subgroups_lower:
        return "Não Classificado", "Dicionário de Grupos Vazio"

    vectorizer = TfidfVectorizer()
    all_docs = [conversation_text] + all_subgroups_lower

    try:
        tfidf_matrix = vectorizer.fit_transform(all_docs)

        cosine_similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])

        if cosine_similarities.size == 0:
            return "Não Classificado", "Erro no Cálculo de Similaridade"

        best_match_index = cosine_similarities.argmax()
        max_similarity = cosine_similarities[0, best_match_index]

        if max_similarity >= similarity_threshold:
            return group_mapping[best_match_index]
        else:
            return "Não Classificado", "Não Classificado (Similaridade Baixa)"

    except ValueError as e:
        logger.error("Error during TF-IDF/Similarity calculation", extra={"error": str(e)})
        if "empty vocabulary" in str(e):
            return "Não Classificado", "Texto Vazio ou Apenas Stopwords"
        return "Não Classificado", "Erro na Classificação"

    return "Não Classificado", "Erro Inesperado na Classificação"


def process_contact(contact, base_url, headers, groups):
    """Process a single contact and return its report data."""
    contact_uuid = contact.get("uuid")
    if not contact_uuid:
        logger.warning("Skipping contact due to missing UUID", extra={"contact": contact})
        return None

    messages = get_contact_messages(contact_uuid, base_url, headers)
    conversation_group = "Não Classificado"
    conversation_tabulation = "Erro ao buscar mensagens"
    last_message_date_br = None

    if messages is None:
        logger.warning(
            "Failed to fetch messages for contact. Skipping classification.", extra={"contact_uuid": contact_uuid}
        )
    else:
        conversation_group, conversation_tabulation = classify_conversation(messages, groups)

        if messages:
            try:
                valid_messages = [m for m in messages if m.get("created_on")]
                valid_messages.sort(key=lambda m: m["created_on"], reverse=True)
                if valid_messages:
                    last_message = valid_messages[0]
                    last_message_date_str = last_message.get("created_on")
                    last_message_date_br = format_datetime_br(last_message_date_str)
                else:
                    logger.warning(
                        "No valid 'created_on' date found in messages for contact.",
                        extra={"contact_uuid": contact_uuid},
                    )

            except Exception as e:
                logger.error(
                    "Error processing message dates for contact", extra={"contact_uuid": contact_uuid, "error": str(e)}
                )

    cliente = contact.get("name")
    urns = contact.get("urns", [])
    numero_cliente = None
    if urns:
        first_urn = urns[0]
        if first_urn:
            if first_urn.startswith("whatsapp:"):
                numero_cliente = first_urn.replace("whatsapp:", "")
            elif first_urn.startswith("tel:"):
                numero_cliente = first_urn.replace("tel:", "")
            else:
                numero_cliente = re.sub(r"\D", "", first_urn)

    cpf = contact.get("fields", {}).get("document")
    created_on_str = contact.get("created_on")
    data_entrada_br = format_datetime_br(created_on_str)

    return {
        "UUID": contact_uuid,
        "Cliente": cliente,
        "Número do Cliente": numero_cliente,
        "CPF": cpf,
        "Assuntos da conversa": conversation_group,
        "Tabulação": conversation_tabulation,
        "Data da entrada": data_entrada_br,
        "Data de fim": last_message_date_br,
    }


def main(auth_token: str, start_date: str = None, end_date: str = None):
    try:
        if not auth_token:
            error_message = (
                "flows_token not found in environment variables or .env file. "
                "Ensure a .env file exists or set flows_token environment variable."
            )
            logger.error(error_message)
            raise ValueError(error_message)

        base_url = BASE_URL.rstrip("/")
        headers = {"Authorization": f"Token {auth_token}"}

        contacts_url = f"{base_url}/api/{API_VERSION}/{CONTACTS_ENDPOINT}"

        if start_date and end_date:
            start_date = pendulum.parse(start_date)
            end_date = pendulum.parse(end_date)
            contacts_url += f"?after={start_date.to_iso8601_string()}&before={end_date.to_iso8601_string()}"
            email_body = (
                f'The attached file contains the report from {start_date.format("DD/MM/YYYY HH:mm")} '
                f'to {end_date.format("DD/MM/YYYY HH:mm")}.'
            )
        else:
            now = pendulum.now()
            yesterday = now.subtract(days=1)
            contacts_url += f"?after={yesterday.to_iso8601_string()}&before={now.to_iso8601_string()}"
            email_body = "The attached file contains the report from the last 24 hours."

        logger.info("Fetching contacts", extra={"url": contacts_url})
        all_contacts = get_paginated_data(contacts_url, headers)

        if all_contacts is None:
            error_message = "Failed to fetch contacts."
            logger.error(error_message)
            raise RuntimeError(error_message)

        logger.info("Fetched contacts", extra={"count": len(all_contacts)})

        report_data = []
        total_contacts = len(all_contacts)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_contact = {
                executor.submit(process_contact, contact, base_url, headers, groups): contact
                for contact in all_contacts
            }

            for future in tqdm(
                concurrent.futures.as_completed(future_to_contact), total=total_contacts, desc="Processing contacts"
            ):
                contact = future_to_contact[future]
                try:
                    result = future.result()
                    if result:
                        report_data.append(result)
                except Exception as exc:
                    contact_uuid = contact.get("uuid", "unknown")
                    logger.error("Error processing contact", extra={"contact_uuid": contact_uuid, "error": str(exc)})

        if not report_data:
            logger.warning("No data processed")
            return []

        columns_order = [
            "UUID",
            "Cliente",
            "Número do Cliente",
            "CPF",
            "Assuntos da conversa",
            "Tabulação",
            "Data da entrada",
            "Data de fim",
        ]

        filename = f"contacts_report-{pendulum.yesterday().format('DD-MM-YYYY')}.csv"
        filepath = os.path.join("/tmp", filename)

        logger.info("Generating CSV report", extra={"filename": filename})
        df = pd.DataFrame(report_data, columns=columns_order)

        df.to_csv(filepath, index=False, encoding="utf-8")
        logger.info("Successfully generated report", extra={"filepath": filepath})

        email = EmailMessage(
            subject="Contacts Report",
            body=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=settings.REPORT_RECIPIENT_EMAILS,
        )

        with open(filepath, "rb") as file:
            email.attach(filename, file.read(), "text/csv")

        email.send()
        logger.info("Successfully sent report via email", extra={"filename": filename})

        return True

    except Exception as e:
        if "401 Client Error" in str(e):
            body = (
                "An error occurred while generating or sending the contacts report: "
                "Invalid or expired authentication token. Please provide a valid token"
            )
        else:
            body = (
                "An error occurred while generating or sending the contacts report.\n\n"
                "Please try again or contact someone from Weni."
            )

        error_message = f"Error processing or sending report: {e}"
        logger.error(error_message)
        try:
            error_email = EmailMessage(
                subject="Error in Contacts Report Generation",
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=settings.REPORT_RECIPIENT_EMAILS,
            )
            error_email.extra_headers = {
                "From": f"Nexus AI Reports {settings.DEFAULT_FROM_EMAIL}",
            }
            error_email.send()
            logger.error("Sent error notification email")
        except Exception as email_error:
            logger.error("Failed to send error notification email", extra={"error": str(email_error)})

        raise Exception(error_message) from None


if __name__ == "__main__":
    main()
