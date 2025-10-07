from typing import Any, Union, Literal
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from agents import RunContextWrapper, FunctionTool
import json


class SimpleTextArgs(BaseModel):
    """Argumentos para componente de texto simples"""
    text: str = Field(..., max_length=4096, description="Texto da mensagem, máximo 4096 caracteres")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")

class QuickRepliesArgs(BaseModel):
    """Argumentos para componente de respostas rápidas (2-3 opções)"""
    text: str = Field(..., max_length=1024, description="Texto da mensagem, máximo 1024 caracteres")
    quick_replies: List[str] = Field(..., min_length=2, max_length=3, description="Lista de 2-3 opções de resposta rápida, máximo 15 caracteres cada")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")
    
    @field_validator('quick_replies')
    @classmethod
    def validate_quick_replies(cls, v):
        # Validar tamanho de cada opção (máximo 15 caracteres)
        for i, option in enumerate(v):
            if len(option) > 15:
                v[i] = option[:12] + "..."
        return v

class ListItemArgs(BaseModel):
    """Argumentos para item de lista"""
    title: str = Field(..., max_length=15, description="Título do item, máximo 15 caracteres")
    description: str = Field(..., max_length=60, description="Descrição do item, máximo 60 caracteres")
    uuid: str = Field(..., description="Identificador único do item")

class ListMessageArgs(BaseModel):
    """Argumentos para componente de lista (4-10 opções com descrições)"""
    text: str = Field(..., max_length=4096, description="Texto da mensagem, máximo 4096 caracteres")
    button_text: str = Field(..., max_length=15, description="Texto do botão, máximo 15 caracteres")
    list_items: List[ListItemArgs] = Field(..., min_length=2, max_length=10, description="Lista de 2-10 itens com título, descrição e uuid")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")

class CtaMessageArgs(BaseModel):
    """Argumentos para componente de Call to Action com URL"""
    text: str = Field(..., max_length=1024, description="Texto da mensagem, máximo 1024 caracteres")
    url: str = Field(..., description="URL válida para redirecionamento")
    display_text: str = Field(..., max_length=15, description="Texto do botão, máximo 15 caracteres")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")

class ProductArgs(BaseModel):
    """Argumentos para produto no catálogo"""
    product: str = Field(..., description="Nome da categoria de produtos")
    product_retailer_ids: List[str] = Field(..., min_length=1, description="lista de SKUs IDs dos produtos dessa categoria no formato 'sku_id#seller_id'")

class CatalogMessageArgs(BaseModel):
    """Argumentos para componente de catálogo de produtos"""
    text: str = Field(..., max_length=1024, description="Texto da mensagem, máximo 1024 caracteres")
    action_button_text: str = Field(..., max_length=15, description="Texto do botão de ação, máximo 15 caracteres")
    products: List[ProductArgs] = Field(..., min_length=1, description="Lista de produtos com nomes e SKUs IDs")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")



async def create_simple_text_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem de texto simples.
    Use quando: resposta informativa direta, sem interações especiais.
    """
    parsed = SimpleTextArgs.model_validate_json(args)
    
    msg = {
        "text": parsed.text
    }

    if parsed.header_text:
        msg["header"] = {
            "type": "text",
            "text": parsed.header_text
        }

    if parsed.footer:
        msg["footer"] = parsed.footer
    
    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)

async def create_quick_replies_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem com opções de resposta rápida (2-3 opções).
    Use quando: usuário precisa escolher entre 2-3 opções simples.
    """
    parsed = QuickRepliesArgs.model_validate_json(args)
    
    msg = {
        "text": parsed.text,
        "quick_replies": parsed.quick_replies
    }

    if parsed.header_text:
        msg["header"] = {
            "type": "text",
            "text": parsed.header_text
        }
    
    if parsed.footer:
        msg["footer"] = parsed.footer
    
    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)

async def create_list_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem com lista de opções (4-10 opções com descrições).
    Use quando: usuário precisa escolher entre múltiplas opções que precisam de descrição.
    """
    parsed = ListMessageArgs.model_validate_json(args)
    
    list_items = []
    for item in parsed.list_items:
        list_items.append({
            "title": item.title,
            "description": item.description,
            "uuid": item.uuid
        })
    
    msg = {
        "text": parsed.text,
        "interaction_type": "list",
        "list_message": {
            "button_text": parsed.button_text,
            "list_items": list_items
        }
    }
    
    if parsed.header_text:
        msg["header"] = {
            "type": "text",
            "text": parsed.header_text
        }
    
    if parsed.footer:
        msg["footer"] = parsed.footer

    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)

async def create_cta_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem com botão de Call to Action (CTA) com URL.
    Use quando: usuário precisa acessar um link externo ou página específica.
    """
    parsed = CtaMessageArgs.model_validate_json(args)
    
    msg = {
        "text": parsed.text,
        "interaction_type": "cta_url",
        "cta_url": {
            "url": parsed.url,
            "display_text": parsed.display_text
        }
    }

    if parsed.header_text:
        msg["header"] = {
            "type": "text",
            "text": parsed.header_text
        }
    
    if parsed.footer:
        msg["footer"] = parsed.footer
    
    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)

async def create_catalog_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem com catálogo de produtos.
    Use quando: produtos foram encontrados e devem ser exibidos ao usuário.
    """
    parsed = CatalogMessageArgs.model_validate_json(args)
    
    products = []
    for product in parsed.products:
        products.append({
            "product": product.product,
            "product_retailer_ids": product.product_retailer_ids
        })
    
    msg = {
        "text": parsed.text,
        "catalog_message": {
            "send_catalog": False,  # Sempre False conforme regras
            "action_button_text": parsed.action_button_text,
            "products": products
        }
    }
    
    if parsed.header_text:
        msg["header"] = {
            "type": "text",
            "text": parsed.header_text
        }
    
    if parsed.footer:
        msg["footer"] = parsed.footer
    
    response = [{"msg": msg}]
    return json.dumps(response, ensure_ascii=False)


simple_text_tool = FunctionTool(
    name="create_simple_text_message",
    description="Cria uma mensagem de texto simples. Use para respostas informativas diretas sem interações especiais.",
    params_json_schema=SimpleTextArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_message,
)

quick_replies_tool = FunctionTool(
    name="create_quick_replies_message", 
    description="Cria uma mensagem com 2-3 opções de resposta rápida. Use quando o usuário precisa escolher entre opções simples.",
    params_json_schema=QuickRepliesArgs.model_json_schema(),
    on_invoke_tool=create_quick_replies_message,
)

list_message_tool = FunctionTool(
    name="create_list_message",
    description="Cria uma mensagem com lista de 4-10 opções com descrições. Use quando há múltiplas opções que precisam de explicação.",
    params_json_schema=ListMessageArgs.model_json_schema(),
    on_invoke_tool=create_list_message,
)

cta_message_tool = FunctionTool(
    name="create_cta_message",
    description="Cria uma mensagem com botão de Call to Action (CTA) com URL. Use quando o usuário precisa acessar um link externo.",
    params_json_schema=CtaMessageArgs.model_json_schema(),
    on_invoke_tool=create_cta_message,
)

catalog_message_tool = FunctionTool(
    name="create_catalog_message",
    description="Cria uma mensagem com catálogo de produtos. Use quando produtos foram encontrados e devem ser exibidos.",
    params_json_schema=CatalogMessageArgs.model_json_schema(),
    on_invoke_tool=create_catalog_message,
)


# Classes para componentes combinados (simple_text + outro componente)
class SimpleTextWithQuickRepliesArgs(BaseModel):
    """Argumentos para componente que combina texto simples + respostas rápidas"""
    # Campos do simple_text
    text: str = Field(..., max_length=4096, description="Texto da mensagem inicial, máximo 4096 caracteres")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")
    
    # Campos do quick_replies
    quick_replies_text: str = Field(..., max_length=1024, description="Texto da segunda mensagem com opções, máximo 1024 caracteres")
    quick_replies: List[str] = Field(..., min_length=2, max_length=3, description="Lista de 2-3 opções de resposta rápida, máximo 15 caracteres cada")
    
    @field_validator('quick_replies')
    @classmethod
    def validate_quick_replies(cls, v):
        # Validar tamanho de cada opção (máximo 15 caracteres)
        for i, option in enumerate(v):
            if len(option) > 15:
                v[i] = option[:12] + "..."
        return v

class SimpleTextWithListArgs(BaseModel):
    """Argumentos para componente que combina texto simples + lista"""
    # Campos do simple_text
    text: str = Field(..., max_length=4096, description="Texto da mensagem inicial, máximo 4096 caracteres")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")
    
    # Campos do list_message
    list_text: str = Field(..., max_length=4096, description="Texto da segunda mensagem com lista, máximo 4096 caracteres")
    button_text: str = Field(..., max_length=15, description="Texto do botão, máximo 15 caracteres")
    list_items: List[ListItemArgs] = Field(..., min_length=2, max_length=10, description="Lista de 2-10 itens com título, descrição e uuid")

class SimpleTextWithCtaArgs(BaseModel):
    """Argumentos para componente que combina texto simples + CTA"""
    # Campos do simple_text
    text: str = Field(..., max_length=4096, description="Texto da mensagem inicial com a mensagem do supervisor, máximo 4096 caracteres")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")
    
    # Campos do cta_message
    cta_text: str = Field(..., max_length=1024, description="Texto da segunda mensagem com CTA com a mensagem do supervisor, máximo 1024 caracteres")
    url: str = Field(..., description="URL válida para redirecionamento")
    display_text: str = Field(..., max_length=15, description="Texto do botão, máximo 15 caracteres")

class SimpleTextWithCatalogArgs(BaseModel):
    """Argumentos para componente que combina texto simples + catálogo"""
    # Campos do simple_text
    text: str = Field(..., max_length=4096, description="Texto da mensagem inicial, máximo 4096 caracteres")
    header_text: Optional[str] = Field(None, max_length=60, description="Texto do cabeçalho opcional, máximo 60 caracteres")
    footer: Optional[str] = Field(None, max_length=60, description="Rodapé opcional, máximo 60 caracteres")
    
    # Campos do catalog_message
    catalog_text: str = Field(..., max_length=1024, description="Texto da segunda mensagem com catálogo, máximo 1024 caracteres")
    action_button_text: str = Field(..., max_length=15, description="Texto do botão de ação, máximo 15 caracteres")
    products: List[ProductArgs] = Field(..., min_length=1, description="Lista de produtos com nomes e SKUs IDs")


# Funções para componentes combinados
async def create_simple_text_with_quick_replies(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem de texto simples seguida de uma mensagem com respostas rápidas.
    Use quando: precisa dar uma informação inicial e depois oferecer opções de escolha.
    """
    parsed = SimpleTextWithQuickRepliesArgs.model_validate_json(args)
    
    # Primeira mensagem (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer
    
    # Segunda mensagem (quick_replies)
    msg2 = {
        "text": parsed.quick_replies_text,
        "quick_replies": parsed.quick_replies
    }
    
    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)

async def create_simple_text_with_list(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem de texto simples seguida de uma mensagem com lista.
    Use quando: precisa dar uma informação inicial e depois mostrar opções detalhadas.
    """
    parsed = SimpleTextWithListArgs.model_validate_json(args)
    
    # Primeira mensagem (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer
    
    # Segunda mensagem (list_message)
    list_items = []
    for item in parsed.list_items:
        list_items.append({
            "title": item.title,
            "description": item.description,
            "uuid": item.uuid
        })
    
    msg2 = {
        "text": parsed.list_text,
        "interaction_type": "list",
        "list_message": {
            "button_text": parsed.button_text,
            "list_items": list_items
        }
    }
    
    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)

async def create_simple_text_with_cta(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem de texto simples seguida de uma mensagem com CTA.
    Use quando: precisa dar uma informação inicial e depois oferecer um link/ação.
    """
    parsed = SimpleTextWithCtaArgs.model_validate_json(args)
    
    # Primeira mensagem (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer
    
    # Segunda mensagem (cta_message)
    msg2 = {
        "text": parsed.cta_text,
        "interaction_type": "cta_url",
        "cta_url": {
            "url": parsed.url,
            "display_text": parsed.display_text
        }
    }
    
    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)

async def create_simple_text_with_catalog(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Cria uma mensagem de texto simples seguida de uma mensagem com catálogo.
    Use quando: precisa dar uma informação inicial e depois mostrar produtos.
    """
    parsed = SimpleTextWithCatalogArgs.model_validate_json(args)
    
    # Primeira mensagem (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer
    
    # Segunda mensagem (catalog_message)
    products = []
    for product in parsed.products:
        products.append({
            "product": product.product,
            "product_retailer_ids": product.product_retailer_ids
        })
    
    msg2 = {
        "text": parsed.catalog_text,
        "catalog_message": {
            "send_catalog": False,
            "action_button_text": parsed.action_button_text,
            "products": products
        }
    }
    
    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


# Ferramentas para componentes combinados
simple_text_with_quick_replies_tool = FunctionTool(
    name="create_simple_text_with_quick_replies",
    description="Cria uma mensagem de texto simples seguida de opções de resposta rápida. Use quando precisa informar algo e depois oferecer escolhas.",
    params_json_schema=SimpleTextWithQuickRepliesArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_quick_replies,
)

simple_text_with_list_tool = FunctionTool(
    name="create_simple_text_with_list",
    description="Cria uma mensagem de texto simples seguida de uma lista de opções. Use quando precisa informar algo e depois mostrar opções detalhadas.",
    params_json_schema=SimpleTextWithListArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_list,
)

simple_text_with_cta_tool = FunctionTool(
    name="create_simple_text_with_cta",
    description="Cria uma mensagem de texto simples seguida de um botão CTA. Use quando precisa informar algo e depois oferecer um link/ação.",
    params_json_schema=SimpleTextWithCtaArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_cta,
)

simple_text_with_catalog_tool = FunctionTool(
    name="create_simple_text_with_catalog",
    description="Cria uma mensagem de texto simples seguida de um catálogo de produtos. Use quando precisa informar algo e depois mostrar produtos.",
    params_json_schema=SimpleTextWithCatalogArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_catalog,
)


COMPONENT_TOOLS = [
    simple_text_tool,
    quick_replies_tool,
    list_message_tool,
    cta_message_tool,
    catalog_message_tool,
    # Componentes combinados
    simple_text_with_quick_replies_tool,
    simple_text_with_list_tool,
    simple_text_with_cta_tool,
    simple_text_with_catalog_tool
]
