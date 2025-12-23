import json
import re
import uuid
from typing import Any, List, Optional, Tuple

from agents import FunctionTool, RunContextWrapper
from pydantic import BaseModel, Field, field_validator

# # from prompts.formatter_prompt_5_1 import TOOLS_DESCRIPTION


def smart_text_split(text: str, limit: int) -> Tuple[str, str]:
    """
    Divide texto mantendo APENAS a(s) última(s) frase(s) no componente.
    Prioriza componente pequeno, respeitando limites (componente: limit, simple_text: 4096).
    """
    SIMPLE_TEXT_LIMIT = 4096

    if len(text) <= limit:
        return "", text

    # Divide mantendo pontuação
    sentences = re.split(r"(?<=[.!?])\s+", text)

    # Tenta pegar 1 a 3 frases finais
    max_sentences_to_take = 3

    for num_sentences in range(1, min(max_sentences_to_take + 1, len(sentences) + 1)):
        candidate_sentences = sentences[-num_sentences:]
        candidate_text = " ".join(candidate_sentences)

        remaining_sentences = sentences[:-num_sentences]
        simple_text_candidate = " ".join(remaining_sentences)

        if len(candidate_text) <= limit and len(simple_text_candidate) <= SIMPLE_TEXT_LIMIT:
            return simple_text_candidate.strip(), candidate_text.strip()

    # Se falhar, move mais frases para o componente para salvar o simple_text
    for num_sentences in range(4, len(sentences) + 1):
        candidate_sentences = sentences[-num_sentences:]
        candidate_text = " ".join(candidate_sentences)

        remaining_sentences = sentences[:-num_sentences]
        simple_text_candidate = " ".join(remaining_sentences)

        if len(simple_text_candidate) <= SIMPLE_TEXT_LIMIT:
            if len(candidate_text) <= limit:
                return simple_text_candidate.strip(), candidate_text.strip()
            else:
                return simple_text_candidate.strip(), candidate_text[:limit].strip()

    # Fallback: última frase muito longa
    ultima_frase = sentences[-1]

    if len(ultima_frase) > limit:
        partes = re.split(r",\s*", ultima_frase)

        if len(partes) > 1:
            for num_partes in range(1, min(3, len(partes) + 1)):
                candidate_partes = partes[-num_partes:]
                candidate_text = ", ".join(candidate_partes)

                if len(candidate_text) <= limit:
                    antes_ultima_frase = " ".join(sentences[:-1])
                    partes_antes = ", ".join(partes[:-num_partes])

                    if antes_ultima_frase and partes_antes:
                        simple_text = antes_ultima_frase + " " + partes_antes
                    elif antes_ultima_frase:
                        simple_text = antes_ultima_frase
                    else:
                        simple_text = partes_antes

                    if len(simple_text) <= SIMPLE_TEXT_LIMIT:
                        return simple_text.strip(), candidate_text.strip()

    # Último recurso: corte forçado
    if len(sentences) > 1:
        simple_text = " ".join(sentences[:-1])[:SIMPLE_TEXT_LIMIT]
        ultima_truncada = ultima_frase[:limit].strip()
        return simple_text.strip(), ultima_truncada

    return text[:SIMPLE_TEXT_LIMIT].strip(), text[SIMPLE_TEXT_LIMIT : SIMPLE_TEXT_LIMIT + limit].strip()


class SimpleTextArgs(BaseModel):
    """Arguments for simple text component"""

    text: str = Field(..., max_length=8000, description="Message text")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class QuickRepliesArgs(BaseModel):
    """Arguments for quick replies component (2-3 options)"""

    text: str = Field(..., max_length=5000, description="Message text")
    quick_replies: List[str] = Field(
        ..., min_length=2, max_length=3, description="List of 2-3 quick reply options, maximum 20 characters each"
    )
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("quick_replies")
    @classmethod
    def validate_quick_replies(cls, v):
        # Validate size of each option (maximum 20 characters)
        for i, option in enumerate(v):
            if len(option) > 20:
                v[i] = option[:20]
        return v

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class ListItemArgs(BaseModel):
    """Arguments for list item"""

    title: str = Field(..., max_length=24, description="Item title, maximum 24 characters")
    description: str = Field(..., max_length=72, description="Item description, maximum 72 characters")


class ListMessageArgs(BaseModel):
    """Arguments for list component (4-10 options with descriptions)"""

    text: str = Field(..., max_length=5000, description="Message text")
    button_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    list_items: List[ListItemArgs] = Field(
        ..., min_length=2, max_length=10, description="List of 2-10 items with title and description"
    )
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class CtaMessageArgs(BaseModel):
    """Arguments for Call to Action component with URL"""

    text: str = Field(..., max_length=5000, description="Message text")
    url: str = Field(..., description="Valid URL for redirection")
    display_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class ProductArgs(BaseModel):
    """Arguments for catalog product"""

    product: str = Field(..., max_length=72, description="Product category name, maximum 72 characters")
    product_retailer_ids: List[str] = Field(
        ..., min_length=1, description="list of product SKU IDs for this category in format 'sku_id#seller_id'"
    )


class CatalogMessageArgs(BaseModel):
    """Arguments for product catalog component"""

    text: str = Field(..., max_length=5000, description="Message text")
    action_button_text: str = Field(..., max_length=20, description="Action button text, maximum 20 characters")
    products: List[ProductArgs] = Field(..., min_length=1, description="List of products with names and SKU IDs")
    header_text: str = Field(..., max_length=60, description="Header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


async def create_simple_text_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a simple text message without interactive elements.
    Use when: Pure informational responses, open questions, no products/links/explicit options.
    """
    parsed = SimpleTextArgs.model_validate_json(args)

    # FALLBACK: Se texto exceder 4096 chars, divide em múltiplas mensagens
    if len(parsed.text) > 4096:
        messages = []
        remaining_text = parsed.text

        # Divide o texto em chunks de até 4096 chars por frase
        while remaining_text:
            if len(remaining_text) <= 4096:
                # Última parte
                msg = {"text": remaining_text}
                if not messages and parsed.header_text:  # Header só na primeira
                    msg["header"] = {"type": "text", "text": parsed.header_text}
                if parsed.footer:  # Footer só na última
                    msg["footer"] = parsed.footer
                messages.append({"msg": msg})
                break
            else:
                # Divide por frase
                sentences = re.split(r"(?<=[.!?])\s+", remaining_text)
                current_chunk = ""
                i = 0

                while i < len(sentences) and len(current_chunk + sentences[i]) <= 4096:
                    current_chunk += sentences[i] + " "
                    i += 1

                if current_chunk:
                    msg = {"text": current_chunk.strip()}
                    if not messages and parsed.header_text:  # Header só na primeira
                        msg["header"] = {"type": "text", "text": parsed.header_text}
                    messages.append({"msg": msg})
                    remaining_text = " ".join(sentences[i:])
                else:
                    # Fallback: se nenhuma frase coube, corta na força
                    msg = {"text": remaining_text[:4096]}
                    if not messages and parsed.header_text:
                        msg["header"] = {"type": "text", "text": parsed.header_text}
                    messages.append({"msg": msg})
                    remaining_text = remaining_text[4096:]

        return json.dumps(messages, ensure_ascii=False)

    # Caso normal: texto dentro do limite
    msg = {"text": parsed.text}

    if parsed.header_text:
        msg["header"] = {"type": "text", "text": parsed.header_text}

    if parsed.footer:
        msg["footer"] = parsed.footer

    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)


async def create_quick_replies_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a message with 2-3 quick reply buttons.
    Use when: Explicit directive + 2-3 options + no descriptions + all options ≤20 chars.
    """
    parsed = QuickRepliesArgs.model_validate_json(args)

    # FALLBACK: Se texto exceder 1024 chars, divide inteligentemente
    if len(parsed.text) > 1024:
        simple_text_content, component_text = smart_text_split(parsed.text, 1024)

        # Primeira mensagem: simple_text com conteúdo longo (sem header/footer)
        msg1 = {"text": simple_text_content}

        # Segunda mensagem: quick_replies com última(s) frase(s) + header/footer
        msg2 = {"text": component_text, "quick_replies": parsed.quick_replies}
        if parsed.header_text:
            msg2["header"] = {"type": "text", "text": parsed.header_text}
        if parsed.footer:
            msg2["footer"] = parsed.footer

        response = [{"msg": msg1}, {"msg": msg2}]
        return json.dumps(response, ensure_ascii=False)

    # Caso normal: texto dentro do limite
    msg = {"text": parsed.text, "quick_replies": parsed.quick_replies}

    if parsed.header_text:
        msg["header"] = {"type": "text", "text": parsed.header_text}

    if parsed.footer:
        msg["footer"] = parsed.footer

    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)


async def create_list_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a message with 2-10 list items with titles and descriptions.
    Use when: 4+ options (MANDATORY) OR 2-3 options with descriptions OR long options >20 chars.
    """
    parsed = ListMessageArgs.model_validate_json(args)

    # FALLBACK: Se texto exceder 1024 chars, divide inteligentemente
    if len(parsed.text) > 1024:
        simple_text_content, component_text = smart_text_split(parsed.text, 1024)

        # Primeira mensagem: simple_text com conteúdo longo (sem header/footer)
        msg1 = {"text": simple_text_content}

        # Segunda mensagem: list com última(s) frase(s) + header/footer
        list_items = []
        for item in parsed.list_items:
            item_uuid = str(uuid.uuid4())
            list_items.append({"title": item.title, "description": item.description, "uuid": item_uuid})

        msg2 = {
            "text": component_text,
            "interaction_type": "list",
            "list_message": {"button_text": parsed.button_text, "list_items": list_items},
        }
        if parsed.header_text:
            msg2["header"] = {"type": "text", "text": parsed.header_text}
        if parsed.footer:
            msg2["footer"] = parsed.footer

        response = [{"msg": msg1}, {"msg": msg2}]
        return json.dumps(response, ensure_ascii=False)

    # Caso normal: texto dentro do limite
    list_items = []

    for item in parsed.list_items:
        item_uuid = str(uuid.uuid4())
        list_items.append({"title": item.title, "description": item.description, "uuid": item_uuid})

    msg = {
        "text": parsed.text,
        "interaction_type": "list",
        "list_message": {"button_text": parsed.button_text, "list_items": list_items},
    }

    if parsed.header_text:
        msg["header"] = {"type": "text", "text": parsed.header_text}

    if parsed.footer:
        msg["footer"] = parsed.footer

    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)


async def create_cta_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a message with Call-to-Action button linking to a URL.
    Use when: Message contains 1 URL that should be clicked. NEVER leave URLs in text field.
    """
    parsed = CtaMessageArgs.model_validate_json(args)

    # FALLBACK: Se texto exceder 1024 chars, divide inteligentemente
    if len(parsed.text) > 1024:
        simple_text_content, component_text = smart_text_split(parsed.text, 1024)

        # Primeira mensagem: simple_text com conteúdo longo (sem header/footer)
        msg1 = {"text": simple_text_content}

        # Segunda mensagem: cta com última(s) frase(s) + header/footer
        msg2 = {
            "text": component_text,
            "interaction_type": "cta_url",
            "cta_message": {"display_text": parsed.display_text, "url": parsed.url},
        }
        if parsed.header_text:
            msg2["header"] = {"type": "text", "text": parsed.header_text}
        if parsed.footer:
            msg2["footer"] = parsed.footer

        response = [{"msg": msg1}, {"msg": msg2}]
        return json.dumps(response, ensure_ascii=False)

    # Caso normal: texto dentro do limite
    msg = {
        "text": parsed.text,
        "interaction_type": "cta_url",
        "cta_message": {"display_text": parsed.display_text, "url": parsed.url},
    }

    if parsed.header_text:
        msg["header"] = {"type": "text", "text": parsed.header_text}

    if parsed.footer:
        msg["footer"] = parsed.footer

    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)


async def create_catalog_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a message with product catalog (HIGHEST PRIORITY component).
    Use when: Products with SKUs present. Text = brief intro, catalog = auto-displays products.
    """
    parsed = CatalogMessageArgs.model_validate_json(args)
    # Tratamento para catalog_text (não pode ter \n). Se houver, move para simple_text.
    parsed.text = parsed.text.strip()
    has_newline = "\n" in parsed.text
    component_text = None

    if len(parsed.text) > 1024 or has_newline:
        simple_text_content = ""
        component_text = parsed.text

        if has_newline and len(parsed.text) <= 1024:
            sentences = re.split(r"(?<=[.!?])\s+", parsed.text)
            if len(sentences) > 1 and "\n" not in sentences[-1]:
                component_text = sentences[-1]
                simple_text_content = " ".join(sentences[:-1])
            elif "\n" in parsed.text:
                parts = parsed.text.rsplit("\n", 1)
                simple_text_content = parts[0]
                component_text = parts[1]
        else:
            simple_text_content, component_text = smart_text_split(parsed.text, 1024)

        component_text = component_text.replace("\n", " ").strip()

        if simple_text_content:
            msg1 = {"text": simple_text_content}

            products = []
            for product in parsed.products:
                products.append({"product": product.product, "product_retailer_ids": product.product_retailer_ids})
                if len(products) >= 10:
                    break

            header = {"type": "text", "text": parsed.header_text if parsed.header_text else "Saiba mais"}

            msg2 = {
                "text": component_text,
                "catalog_message": {
                    "send_catalog": False,
                    "action_button_text": parsed.action_button_text,
                    "products": products,
                },
                "header": header,
            }

            if parsed.footer:
                msg2["footer"] = parsed.footer

            response = [{"msg": msg1}, {"msg": msg2}]
            return json.dumps(response, ensure_ascii=False)

    final_text = parsed.text
    if component_text is not None:
        final_text = component_text
    else:
        final_text = parsed.text.replace("\n", " ").strip()

    products = []
    for product in parsed.products:
        products.append({"product": product.product, "product_retailer_ids": product.product_retailer_ids})
        if len(products) >= 10:
            break

    if parsed.header_text:
        header = {"type": "text", "text": parsed.header_text}
    else:
        header = {"type": "text", "text": "Saiba mais"}

    msg = {
        "text": final_text,
        "catalog_message": {
            "send_catalog": False,
            "action_button_text": parsed.action_button_text,
            "products": products,
        },
        "header": header,
    }

    if parsed.footer:
        msg["footer"] = parsed.footer

    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)


simple_text_tool = FunctionTool(
    name="create_simple_text_message",
    description="Pure informational text without interactive elements.\n\nUSE WHEN: No products with SKUs, no single URL, no imperative directive with options, or 2+ URLs present.\n\nLIMITS: text <=4096 chars",
    params_json_schema=SimpleTextArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_message,
)

quick_replies_tool = FunctionTool(
    name="create_quick_replies_message",
    description="Message with 2-3 simple quick reply buttons.\n\nUSE WHEN: Imperative directive + exactly 2-3 simple options (<=20 chars each) + NO descriptions.\n\nDO NOT USE: If ANY option has description -> use list_message. If 4+ options -> use list_message. If products with SKUs -> use catalog.\n\nLIMITS: text <=1024 chars, 2-3 buttons <=20 chars each",
    params_json_schema=QuickRepliesArgs.model_json_schema(),
    on_invoke_tool=create_quick_replies_message,
)

list_message_tool = FunctionTool(
    name="create_list_message",
    description="Message with 2-10 detailed list items (title + description).\n\nUSE WHEN: 4+ options (mandatory), OR 2-3 options with descriptions, OR options >20 chars.\n\nDO NOT USE: If products with SKUs -> use catalog. If 2-3 simple options without descriptions -> use quick_replies.\n\nLIMITS: text <=1024 chars, title <=24 chars, description <=72 chars, button_text <=20 chars",
    params_json_schema=ListMessageArgs.model_json_schema(),
    on_invoke_tool=create_list_message,
)

cta_message_tool = FunctionTool(
    name="create_cta_message",
    description="Message with single Call-to-Action URL button.\n\nUSE WHEN: Exactly 1 URL present + NO products with SKUs.\n\nDO NOT USE: If 2+ URLs -> use simple_text. If products with SKUs -> use catalog.\n\nLIMITS: text <=1024 chars, display_text <=20 chars",
    params_json_schema=CtaMessageArgs.model_json_schema(),
    on_invoke_tool=create_cta_message,
)

catalog_message_tool = FunctionTool(
    name="create_catalog_message",
    description="Product catalog with SKUs (HIGHEST PRIORITY when products present).\n\nUSE WHEN: Products with SKU codes (containing '#') found in history or message.\n\nPRIORITY: Always use catalog over other components when products with SKUs exist.\n\nTEXT OPTIMIZATION: Brief conversational intro only (catalog displays full product data).\n\nLIMITS: text <=1024 chars (single-line, no \\n), max 10 categories, header REQUIRED <=60 chars",
    params_json_schema=CatalogMessageArgs.model_json_schema(),
    on_invoke_tool=create_catalog_message,
)


# Classes for combined components (simple_text + another component)
class SimpleTextWithQuickRepliesArgs(BaseModel):
    """Arguments for component that combines simple text + quick replies"""

    # simple_text fields
    text: str = Field(..., max_length=4096, description="Initial message text, maximum 4096 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    # quick_replies fields
    quick_replies_text: str = Field(
        ..., max_length=1024, description="Second message text with options, maximum 1024 characters"
    )
    quick_replies: List[str] = Field(
        ..., min_length=2, max_length=3, description="List of 2-3 quick reply options, maximum 20 characters each"
    )
    quick_replies_header_text: Optional[str] = Field(
        None, max_length=60, description="Optional header text for quick replies, maximum 60 characters"
    )
    quick_replies_footer: Optional[str] = Field(
        None, max_length=60, description="Optional footer for quick replies, maximum 60 characters"
    )

    @field_validator("quick_replies")
    @classmethod
    def validate_quick_replies(cls, v):
        # Validate size of each option (maximum 20 characters)
        for i, option in enumerate(v):
            if len(option) > 20:
                v[i] = option[:20]
        return v

    @field_validator("header_text", "quick_replies_header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer", "quick_replies_footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class SimpleTextWithListArgs(BaseModel):
    """Arguments for component that combines simple text + list"""

    # simple_text fields
    text: str = Field(..., max_length=4096, description="Initial message text, maximum 4096 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    # list_message fields
    list_text: str = Field(..., max_length=4096, description="Second message text with list, maximum 4096 characters")
    button_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    list_items: List[ListItemArgs] = Field(
        ..., min_length=2, max_length=10, description="List of 2-10 items with title, description and uuid"
    )
    list_header_text: Optional[str] = Field(
        None, max_length=60, description="Optional header text for list, maximum 60 characters"
    )
    list_footer: Optional[str] = Field(
        None, max_length=60, description="Optional footer for list, maximum 60 characters"
    )

    @field_validator("header_text", "list_header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer", "list_footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class SimpleTextWithCtaArgs(BaseModel):
    """Arguments for component that combines simple text + CTA"""

    # simple_text fields
    text: str = Field(
        ..., max_length=4096, description="Initial message text with supervisor message, maximum 4096 characters"
    )
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    # cta_message fields
    cta_text: str = Field(
        ...,
        max_length=1024,
        description="Second message text with CTA with supervisor message, maximum 1024 characters",
    )
    url: str = Field(..., description="Valid URL for redirection")
    display_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    cta_header_text: Optional[str] = Field(
        None, max_length=60, description="Optional header text for CTA, maximum 60 characters"
    )
    cta_footer: Optional[str] = Field(None, max_length=60, description="Optional footer for CTA, maximum 60 characters")

    @field_validator("header_text", "cta_header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer", "cta_footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class SimpleTextWithCatalogArgs(BaseModel):
    """Arguments for component that combines simple text + catalog"""

    # simple_text fields
    text: str = Field(..., max_length=4096, description="Initial message text, maximum 4096 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    # catalog_message fields
    catalog_text: str = Field(
        ..., max_length=1024, description="Second message text with catalog, maximum 1024 characters"
    )
    catalog_header_text: str = Field(..., max_length=60, description="Catalog header text, maximum 60 characters")
    action_button_text: str = Field(..., max_length=20, description="Action button text, maximum 20 characters")
    products: List[ProductArgs] = Field(..., min_length=1, description="List of products with names and SKU IDs")
    catalog_footer: Optional[str] = Field(
        None, max_length=60, description="Optional footer for catalog, maximum 60 characters"
    )

    @field_validator("header_text", "catalog_header_text")
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator("footer", "catalog_footer")
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


# Functions for combined components
async def create_simple_text_with_quick_replies(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates TWO messages: simple text + quick replies.
    Use when: Text exceeds 1024 chars AND all quick_replies conditions apply.
    """
    parsed = SimpleTextWithQuickRepliesArgs.model_validate_json(args)

    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    msg2 = {"text": parsed.quick_replies_text, "quick_replies": parsed.quick_replies}
    if parsed.quick_replies_header_text:
        msg2["header"] = {"type": "text", "text": parsed.quick_replies_header_text}
    if parsed.quick_replies_footer:
        msg2["footer"] = parsed.quick_replies_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


async def create_simple_text_with_list(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates TWO messages: simple text + list.
    Use when: Text exceeds 4096 chars AND list conditions apply (4+ options OR descriptions).
    """
    parsed = SimpleTextWithListArgs.model_validate_json(args)

    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    list_items = []
    for item in parsed.list_items:
        item_uuid = str(uuid.uuid4())
        list_items.append({"title": item.title, "description": item.description, "uuid": item_uuid})

    msg2 = {
        "text": parsed.list_text,
        "interaction_type": "list",
        "list_message": {"button_text": parsed.button_text, "list_items": list_items},
    }
    if parsed.list_header_text:
        msg2["header"] = {"type": "text", "text": parsed.list_header_text}
    if parsed.list_footer:
        msg2["footer"] = parsed.list_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


async def create_simple_text_with_cta(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates TWO messages: simple text + CTA.
    Use when: Text exceeds 1024 chars AND URL/link is present.
    """
    parsed = SimpleTextWithCtaArgs.model_validate_json(args)

    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    msg2 = {
        "text": parsed.cta_text,
        "interaction_type": "cta_url",
        "cta_message": {"display_text": parsed.display_text, "url": parsed.url},
    }
    if parsed.cta_header_text:
        msg2["header"] = {"type": "text", "text": parsed.cta_header_text}
    if parsed.cta_footer:
        msg2["footer"] = parsed.cta_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


async def create_simple_text_with_catalog(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates TWO messages: simple text + catalog.
    Use when: Text exceeds 1024 chars AND products with SKUs are present.
    """
    parsed = SimpleTextWithCatalogArgs.model_validate_json(args)

    # Tratamento para catalog_text (não pode ter \n). Se houver, move para simple_text.
    parsed.catalog_text = parsed.catalog_text.strip()

    catalog_text_final = parsed.catalog_text
    extra_simple_text = ""
    has_newline = "\n" in parsed.catalog_text

    if len(parsed.catalog_text) > 1024 or has_newline:
        if has_newline and len(parsed.catalog_text) <= 1024:
            sentences = re.split(r"(?<=[.!?])\s+", parsed.catalog_text)

            if len(sentences) > 1 and "\n" not in sentences[-1]:
                catalog_text_final = sentences[-1]
                extra_simple_text = " ".join(sentences[:-1])
            elif "\n" in parsed.catalog_text:
                parts = parsed.catalog_text.rsplit("\n", 1)
                extra_simple_text = parts[0]
                catalog_text_final = parts[1]
        else:
            extra_simple_text, catalog_text_final = smart_text_split(parsed.catalog_text, 1024)

        catalog_text_final = catalog_text_final.replace("\n", " ").strip()
    else:
        catalog_text_final = parsed.catalog_text.replace("\n", " ").strip()

    full_text = parsed.text
    if extra_simple_text:
        full_text = f"{parsed.text}\n{extra_simple_text}".strip()

    msg1 = {"text": full_text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    products = []
    for product in parsed.products:
        products.append({"product": product.product, "product_retailer_ids": product.product_retailer_ids})
        if len(products) >= 10:
            break

    if parsed.catalog_header_text:
        header = {"type": "text", "text": parsed.catalog_header_text}
    else:
        header = {"type": "text", "text": "Saiba mais"}

    msg2 = {
        "text": catalog_text_final,
        "header": header,
        "catalog_message": {
            "send_catalog": False,
            "action_button_text": parsed.action_button_text,
            "products": products,
        },
    }
    if parsed.catalog_footer:
        msg2["footer"] = parsed.catalog_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


# Tools for combined components
simple_text_with_quick_replies_tool = FunctionTool(
    name="create_simple_text_with_quick_replies",
    description="TWO messages: simple text + quick replies.\n\nUSE WHEN: Text >1024 chars AND quick_replies conditions apply.\n\nMANDATORY: Must use when text exceeds 1024 chars (cannot use single quick_replies).\n\nLIMITS: text <=4096 chars, quick_replies_text <=1024 chars",
    params_json_schema=SimpleTextWithQuickRepliesArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_quick_replies,
)

simple_text_with_list_tool = FunctionTool(
    name="create_simple_text_with_list",
    description="TWO messages: simple text + list.\n\nUSE WHEN: Text >1024 chars AND list conditions apply.\n\nMANDATORY: Must use when text exceeds 1024 chars (cannot use single list_message).\n\nLIMITS: text <=4096 chars, list_text <=1024 chars",
    params_json_schema=SimpleTextWithListArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_list,
)

simple_text_with_cta_tool = FunctionTool(
    name="create_simple_text_with_cta",
    description="TWO messages: simple text + CTA button.\n\nUSE WHEN: Text >1024 chars AND exactly 1 URL present.\n\nMANDATORY: Must use when text exceeds 1024 chars (cannot use single cta_message).\n\nLIMITS: text <=4096 chars, cta_text <=1024 chars",
    params_json_schema=SimpleTextWithCtaArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_cta,
)

simple_text_with_catalog_tool = FunctionTool(
    name="create_simple_text_with_catalog",
    description="TWO messages: simple text + product catalog.\n\nUSE WHEN: \n1. Text > 1024 chars AND products with SKUs present.\n2. OR: When there is IMPORTANT context/advice/questions before or after the product list that must be preserved.\n\nMANDATORY: Use this whenever the supervisor provides advice, \"combo\" recommendations, or closing questions along with the products. The single 'create_catalog_message' cannot hold this rich context.\n\nLIMITS: text <=4096 chars (for the rich context), catalog_text <=1024 chars (brief intro only)",
    params_json_schema=SimpleTextWithCatalogArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_catalog,
)


COMPONENT_TOOLS = [
    simple_text_tool,
    quick_replies_tool,
    list_message_tool,
    cta_message_tool,
    catalog_message_tool,
    # Combined components
    simple_text_with_quick_replies_tool,
    simple_text_with_list_tool,
    simple_text_with_cta_tool,
    simple_text_with_catalog_tool,
]
