import re
import uuid
import json

from typing import Optional, List, Any
from agents import RunContextWrapper, FunctionTool
from pydantic import BaseModel, Field, field_validator


class SimpleTextArgs(BaseModel):
    """Arguments for simple text component"""
    text: str = Field(..., max_length=4096, description="Message text, maximum 4096 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator('header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class QuickRepliesArgs(BaseModel):
    """Arguments for quick replies component (2-3 options)"""
    text: str = Field(..., max_length=1024, description="Message text, maximum 1024 characters")
    quick_replies: List[str] = Field(..., min_length=2, max_length=3, description="List of 2-3 quick reply options, maximum 20 characters each")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator('quick_replies')
    @classmethod
    def validate_quick_replies(cls, v):
        # Validate size of each option (maximum 20 characters)
        for i, option in enumerate(v):
            if len(option) > 20:
                v[i] = option[:20]
        return v

    @field_validator('header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
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
    text: str = Field(..., max_length=4096, description="Message text, maximum 4096 characters")
    button_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    list_items: List[ListItemArgs] = Field(..., min_length=2, max_length=10, description="List of 2-10 items with title and description")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator('header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class CtaMessageArgs(BaseModel):
    """Arguments for Call to Action component with URL"""
    text: str = Field(..., max_length=1024, description="Message text, maximum 1024 characters")
    url: str = Field(..., description="Valid URL for redirection")
    display_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator('header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class ProductArgs(BaseModel):
    """Arguments for catalog product"""
    product: str = Field(..., max_length=72, description="Product category name, maximum 72 characters")
    product_retailer_ids: List[str] = Field(..., min_length=1, description="list of product SKU IDs for this category in format 'sku_id#seller_id'")


class CatalogMessageArgs(BaseModel):
    """Arguments for product catalog component"""
    text: str = Field(..., max_length=1024, description="Message text, maximum 1024 characters")
    action_button_text: str = Field(..., max_length=20, description="Action button text, maximum 20 characters")
    products: List[ProductArgs] = Field(..., min_length=1, description="List of products with names and SKU IDs")
    header_text: str = Field(..., max_length=60, description="Header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator('header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


async def create_simple_text_message(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a simple text message.
    Use when: direct informative response, without special interactions.
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
    Creates a message with quick reply options (2-3 options).
    Use when: user needs to choose between 2-3 simple options.
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
    Creates a message with list of options (4-10 options with descriptions).
    Use when: user needs to choose between multiple options that need description.
    """
    parsed = ListMessageArgs.model_validate_json(args)

    list_items = []

    for item in parsed.list_items:
        item_uuid = str(uuid.uuid4())
        list_items.append({
            "title": item.title,
            "description": item.description,
            "uuid": item_uuid
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
    Creates a message with Call to Action (CTA) button with URL.
    Use when: user needs to access an external link or specific page.
    """
    parsed = CtaMessageArgs.model_validate_json(args)

    msg = {
        "text": parsed.text,
        "interaction_type": "cta_url",
        "cta_message": {
            "display_text": parsed.display_text,
            "url": parsed.url
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
    Creates a message with product catalog.
    Use when: products were found and should be displayed to the user.
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
            "send_catalog": False,  # Always False according to rules
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
    description="Creates a simple text message. Use for direct informative responses without special interactions.",
    params_json_schema=SimpleTextArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_message,
)

quick_replies_tool = FunctionTool(
    name="create_quick_replies_message", 
    description="Creates a message with 2-3 quick reply options. Use when the user needs to choose between simple options.",
    params_json_schema=QuickRepliesArgs.model_json_schema(),
    on_invoke_tool=create_quick_replies_message,
)

list_message_tool = FunctionTool(
    name="create_list_message",
    description="Creates a message with list of 4-10 options with descriptions. Use when there are multiple options that need explanation.",
    params_json_schema=ListMessageArgs.model_json_schema(),
    on_invoke_tool=create_list_message,
)

cta_message_tool = FunctionTool(
    name="create_cta_message",
    description="Creates a message with Call to Action (CTA) button with URL. Use when the user needs to access an external link.",
    params_json_schema=CtaMessageArgs.model_json_schema(),
    on_invoke_tool=create_cta_message,
)

catalog_message_tool = FunctionTool(
    name="create_catalog_message",
    description="Creates a message with product catalog. Use when products were found and should be displayed.",
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
    quick_replies_text: str = Field(..., max_length=1024, description="Second message text with options, maximum 1024 characters")
    quick_replies: List[str] = Field(..., min_length=2, max_length=3, description="List of 2-3 quick reply options, maximum 20 characters each")
    quick_replies_header_text: Optional[str] = Field(None, max_length=60, description="Optional header text for quick replies, maximum 60 characters")
    quick_replies_footer: Optional[str] = Field(None, max_length=60, description="Optional footer for quick replies, maximum 60 characters")

    @field_validator('quick_replies')
    @classmethod
    def validate_quick_replies(cls, v):
        # Validate size of each option (maximum 20 characters)
        for i, option in enumerate(v):
            if len(option) > 20:
                v[i] = option[:20]
        return v

    @field_validator('header_text', 'quick_replies_header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer', 'quick_replies_footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
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
    list_items: List[ListItemArgs] = Field(..., min_length=2, max_length=10, description="List of 2-10 items with title, description and uuid")
    list_header_text: Optional[str] = Field(None, max_length=60, description="Optional header text for list, maximum 60 characters")
    list_footer: Optional[str] = Field(None, max_length=60, description="Optional footer for list, maximum 60 characters")

    @field_validator('header_text', 'list_header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer', 'list_footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


class SimpleTextWithCtaArgs(BaseModel):
    """Arguments for component that combines simple text + CTA"""
    # simple_text fields
    text: str = Field(..., max_length=4096, description="Initial message text with supervisor message, maximum 4096 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    # cta_message fields
    cta_text: str = Field(..., max_length=1024, description="Second message text with CTA with supervisor message, maximum 1024 characters")
    url: str = Field(..., description="Valid URL for redirection")
    display_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    cta_header_text: Optional[str] = Field(None, max_length=60, description="Optional header text for CTA, maximum 60 characters")
    cta_footer: Optional[str] = Field(None, max_length=60, description="Optional footer for CTA, maximum 60 characters")

    @field_validator('header_text', 'cta_header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer', 'cta_footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
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
    catalog_text: str = Field(..., max_length=1024, description="Second message text with catalog, maximum 1024 characters")
    catalog_header_text: str = Field(..., max_length=60, description="Catalog header text, maximum 60 characters")
    action_button_text: str = Field(..., max_length=20, description="Action button text, maximum 20 characters")
    products: List[ProductArgs] = Field(..., min_length=1, description="List of products with names and SKU IDs")
    catalog_footer: Optional[str] = Field(None, max_length=60, description="Optional footer for catalog, maximum 60 characters")

    @field_validator('header_text', 'catalog_header_text')
    @classmethod
    def clean_header(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v

    @field_validator('footer', 'catalog_footer')
    @classmethod
    def clean_footer(cls, v):
        if v is None:
            return v
        # Remove caracteres de controle (incluindo \u000e, \x0e, etc)
        v = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', v)
        v = v.strip()
        # Se ficou vazio após a limpeza, retorna None
        if not v:
            return None
        return v


# Functions for combined components
async def create_simple_text_with_quick_replies(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a simple text message followed by a message with quick replies.
    Use when: need to give initial information and then offer choice options.
    """
    parsed = SimpleTextWithQuickRepliesArgs.model_validate_json(args)

    # First message (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    # Second message (quick_replies)
    msg2 = {
        "text": parsed.quick_replies_text,
        "quick_replies": parsed.quick_replies
    }
    if parsed.quick_replies_header_text:
        msg2["header"] = {"type": "text", "text": parsed.quick_replies_header_text}
    if parsed.quick_replies_footer:
        msg2["footer"] = parsed.quick_replies_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


async def create_simple_text_with_list(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a simple text message followed by a message with list.
    Use when: need to give initial information and then show detailed options.
    """
    parsed = SimpleTextWithListArgs.model_validate_json(args)

    # First message (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    # Second message (list_message)
    list_items = []
    for item in parsed.list_items:
        item_uuid = str(uuid.uuid4())
        list_items.append({
            "title": item.title,
            "description": item.description,
            "uuid": item_uuid
        })

    msg2 = {
        "text": parsed.list_text,
        "interaction_type": "list",
        "list_message": {
            "button_text": parsed.button_text,
            "list_items": list_items
        }
    }
    if parsed.list_header_text:
        msg2["header"] = {"type": "text", "text": parsed.list_header_text}
    if parsed.list_footer:
        msg2["footer"] = parsed.list_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


async def create_simple_text_with_cta(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a simple text message followed by a message with CTA.
    Use when: need to give initial information and then offer a link/action.
    """
    parsed = SimpleTextWithCtaArgs.model_validate_json(args)

    # First message (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    # Second message (cta_message)
    msg2 = {
        "text": parsed.cta_text,
        "interaction_type": "cta_url",
        "cta_message": {
            "display_text": parsed.display_text,
            "url": parsed.url
        }
    }
    if parsed.cta_header_text:
        msg2["header"] = {"type": "text", "text": parsed.cta_header_text}
    if parsed.cta_footer:
        msg2["footer"] = parsed.cta_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


async def create_simple_text_with_catalog(ctx: RunContextWrapper[Any], args: str) -> str:
    """
    Creates a simple text message followed by a message with catalog.
    Use when: need to give initial information and then show products.
    """
    parsed = SimpleTextWithCatalogArgs.model_validate_json(args)

    # First message (simple_text)
    msg1 = {"text": parsed.text}
    if parsed.header_text:
        msg1["header"] = {"type": "text", "text": parsed.header_text}
    if parsed.footer:
        msg1["footer"] = parsed.footer

    # Second message (catalog_message)
    products = []
    for product in parsed.products:
        products.append({
            "product": product.product,
            "product_retailer_ids": product.product_retailer_ids
        })

    msg2 = {
        "text": parsed.catalog_text,
        "header": {
            "type": "text",
            "text": parsed.catalog_header_text
        },
        "catalog_message": {
            "send_catalog": False,
            "action_button_text": parsed.action_button_text,
            "products": products
        }
    }
    if parsed.catalog_footer:
        msg2["footer"] = parsed.catalog_footer

    response = [{"msg": msg1}, {"msg": msg2}]
    return json.dumps(response, ensure_ascii=False)


# Tools for combined components
simple_text_with_quick_replies_tool = FunctionTool(
    name="create_simple_text_with_quick_replies",
    description="Creates a simple text message followed by quick reply options. Use MANDATORILY when the response text is extensive and exceeds the character limit of the pure quick_replies component (which has a limit in the 'text' field). Separates the extensive informative content in the first message and the choice options in the second.",
    params_json_schema=SimpleTextWithQuickRepliesArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_quick_replies,
)

simple_text_with_list_tool = FunctionTool(
    name="create_simple_text_with_list",
    description="Creates a simple text message followed by a list of options. Use MANDATORILY when the response text is extensive and exceeds the character limit of the pure list_message component (which has a limit in the 'text' field). Separates the extensive informative content in the first message and the detailed options in the second.",
    params_json_schema=SimpleTextWithListArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_list,
)

simple_text_with_cta_tool = FunctionTool(
    name="create_simple_text_with_cta",
    description="Creates a simple text message followed by a CTA button. Use MANDATORILY when the response text is extensive and exceeds the character limit of the pure cta_url component (which has a limit in the 'text' field). Separates the extensive informative content in the first message and the action button in the second.",
    params_json_schema=SimpleTextWithCtaArgs.model_json_schema(),
    on_invoke_tool=create_simple_text_with_cta,
)

simple_text_with_catalog_tool = FunctionTool(
    name="create_simple_text_with_catalog",
    description="Creates a simple text message followed by a product catalog. Use MANDATORILY when the response text is extensive and exceeds the character limit of the pure catalog_message component (which has a limit in the 'text' field). Separates the extensive informative content in the first message and the product catalog in the second.",
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
    simple_text_with_catalog_tool
]
