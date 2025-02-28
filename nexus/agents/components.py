# Simple text message
SIMPLE_TEXT = '<exemplo>{"msg":{"text":"Hi! How can I help you today?"}}</exemplo>'

# Attachments
ATTACHMENT = '<exemplo>{"msg": {"attachments": ["image:https://example.com/product-photo.jpg"]}}</exemplo>'
TEXT_WITH_ATTACHMENT = '<exemplo>{"msg": {"text": "Here is the catalog you requested:", "attachments": ["pdf:https://example.com/catalog.pdf"]}}</exemplo>'

# Quick replies
QUICK_REPLIES = '<exemplo>{"msg": {"text": "How would you like to receive your order?", "quick_replies": ["Delivery", "Store pickup"]}}</exemplo>'

# List Message
LIST_MESSAGE = '<exemplo>{"msg": {"text": "Choose a category:","interaction_type": "list","list_message": { "button_text": "View categories", "list_items": [{"title": "Smartphones", "description": "iPhone, Samsung and more", "uuid": "cat_001"}, {"title": "Notebooks", "description": "Dell, Lenovo, Acer", "uuid": "cat_002"}]}}}</exemplo>'

# CTA Message (Call to Action)
CTA_MESSAGE = '<exemplo>{"msg": {"text": "Visit our online store!", "interaction_type": "cta_url", "cta_url": {"url": "https://mystore.com", "display_text": "See offers 🏷️"}}}</exemplo>'

# Catalog examples
CATALOG = '<exemplo>{"msg": {"text":"Check out our premium cookware line:", "header": {"text":"🏆 Premium Line","type":"text"}, "footer":"Free shipping nationwide", "catalog_message": {"send_catalog": false, "action_button_name":"flow", "products": [{"product":"Stainless Steel Cookware Set", "product_retailer_ids":["PAN789#a"]}, {"product":"Ceramic Cookware Set", "product_retailer_ids":["PAN101#a"]}], "action_button_text":"Learn more"}}}</exemplo>'

def get_all_formats():
    return (SIMPLE_TEXT + " " + 
            ATTACHMENT + " " + 
            TEXT_WITH_ATTACHMENT + " " + 
            QUICK_REPLIES + " " + 
            LIST_MESSAGE + " " + 
            CTA_MESSAGE + " " + 
            CATALOG)
