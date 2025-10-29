# ruff: noqa: E501 - Very long embedded prompt strings
SIMPLE_TEXT = '<exemplo>{"msg":{"text":"Hi! How can I help you today?" (MAXIMUM 4096 CHARACTERS)}}</exemplo>'

# Quick replies
QUICK_REPLIES = '<exemplo>{"msg": {"text": "How would you like to receive your order?"(MAXIMUM 1024 CHARACTERS), "quick_replies": ["Delivery"(MAXIMUM 15 CHARACTERS), "Store pickup"(MAXIMUM 15 CHARACTERS)](MAXIMUM 3 ITEMS)}}</exemplo>'

# List Message
LIST_MESSAGE = '<exemplo>{"msg": {"text": "Choose a category:"(MAXIMUM 4096 CHARACTERS),"interaction_type": "list","list_message": { "button_text": "View categories"(MAXIMUM 15 CHARACTERS), "list_items": [{"title": "Smartphones"(MAXIMUM 20 CHARACTERS), "description": "iPhone, Samsung and more"(MAXIMUM 72 CHARACTERS), "uuid": "cat_001"}, {"title": "Notebooks"(MAXIMUM 20 CHARACTERS), "description": "Dell, Lenovo, Acer"(MAXIMUM 72 CHARACTERS), "uuid": "cat_002"}](MAXIMUM 10 ITEMS)}}}</exemplo>'

# CTA Message (Call to Action)
CTA_MESSAGE = '<exemplo>{"msg": {"text": "Visit our online store!"(MAXIMUM 1024 CHARACTERS), "interaction_type": "cta_url", "cta_url": {"url": "https://mystore.com", "display_text": "See offers 🏷️"(MAXIMUM 15 CHARACTERS)}}}</exemplo>'

# Catalog examples
CATALOG = '<exemplo>{"msg":{"text":"Confira nossos produtos disponíveis para entrega no seu CEP:"(MAXIMUM 1024 CHARACTERS),"header":{"text":"Produtos disponíveis"(MAXIMUM 60 CHARACTERS),"type":"text"},"footer":"Entrega disponível para seu CEP"(MAXIMUM 60 CHARACTERS),"catalog_message":{"send_catalog":false,"action_button_text":"Ver detalhes"(MAXIMUM 15 CHARACTERS),"products"(CATEGORYS):[{"product":"Tipo de produto A","product_retailer_ids":["produto_id_A1#loja_id","produto_id_A2#loja_id","produto_id_A3#loja_id"]},{"product":"Tipo de produto B","product_retailer_ids":["produto_id_B1#loja_id","produto_id_B2#loja_id","produto_id_B3#loja_id"]},{"product":"Tipo de produto C","product_retailer_ids":["produto_id_C1#loja_id","produto_id_C2#loja_id","produto_id_C3#loja_id"]},{"product":"Tipo de produto D","product_retailer_ids":["produto_id_D1#loja_id","produto_id_D2#loja_id","produto_id_D3#loja_id"]}]}}}</exemplo>'


def get_all_formats():
    return f"{LIST_MESSAGE} {QUICK_REPLIES} {SIMPLE_TEXT} {CTA_MESSAGE} {CATALOG}"


def get_all_formats_list():
    return [LIST_MESSAGE, QUICK_REPLIES, SIMPLE_TEXT, CTA_MESSAGE, CATALOG]
