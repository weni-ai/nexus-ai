SIMPLE_TEXT = '<exemplo>{"msg":{"text":"Hi! How can I help you today?" (MAXIMUM 4096 CHARACTERS)}}</exemplo>'

# Quick replies
QUICK_REPLIES = '<exemplo>{"msg": {"text": "How would you like to receive your order?"(MAXIMUM 1024 CHARACTERS), "quick_replies": ["Delivery"(MAXIMUM 20 CHARACTERS), "Store pickup"(MAXIMUM 20 CHARACTERS)](MAXIMUM 3 ITEMS)}}</exemplo>'

# List Message
LIST_MESSAGE = '<exemplo>{"msg": {"text": "Choose a category:"(MAXIMUM 4096 CHARACTERS),"interaction_type": "list","list_message": { "button_text": "View categories"(MAXIMUM 20 CHARACTERS), "list_items": [{"title": "Smartphones"(MAXIMUM 24 CHARACTERS), "description": "iPhone, Samsung and more"(MAXIMUM 72 CHARACTERS), "uuid": "cat_001"}, {"title": "Notebooks"(MAXIMUM 24 CHARACTERS), "description": "Dell, Lenovo, Acer"(MAXIMUM 72 CHARACTERS), "uuid": "cat_002"}](MAXIMUM 10 ITEMS)}}}</exemplo>'

# CTA Message (Call to Action)
CTA_MESSAGE = '<exemplo>{"msg": {"text": "Visit our online store!"(MAXIMUM 1024 CHARACTERS), "interaction_type": "cta_url", "cta_url": {"url": "https://mystore.com", "display_text": "See offers 🏷️"(MAXIMUM 20 CHARACTERS)}}}</exemplo>'

# Catalog examples
CATALOG = '<exemplo>{"msg": {"text":"Check out our premium cookware line:"(MAXIMUM 1024 CHARACTERS), "header": {"text":"🏆 Premium Line"(MAXIMUM 60 CHARACTERS),"type":"text"}, "footer":"Free shipping nationwide"(MAXIMUM 60 CHARACTERS), "catalog_message": {"send_catalog": false, "action_button_name":"flow", "products": [{"product":"Stainless Steel Cookware Set", "product_retailer_ids":["PAN789#a"]}, {"product":"Ceramic Cookware Set", "product_retailer_ids":["PAN101#a"]}], "action_button_text":"Learn more"}}}</exemplo>'

def get_all_formats():
    return (LIST_MESSAGE+ " " + 
            QUICK_REPLIES + " " + 
            SIMPLE_TEXT + " " + 
            CTA_MESSAGE + " " + 
            CATALOG)
