from typing import List


class Components:
    SIMPLE_TEXT = """
    {
    "msg": {
        "text": "Hi! How can I help you today?" #(MAXIMUM 4096 CHARACTERS)

    }
    }
    """

    QUICK_REPLIES = """
    {
    "msg": {
        "text": "How would you like to receive your order?",  #(MAXIMUM 1024 CHARACTERS)
        "quick_replies": [
        "Delivery",         #(MAXIMUM 15 CHARACTERS)
        "Store pickup"      #(MAXIMUM 15 CHARACTERS)
        ]                     #(MAXIMUM 3 ITEMS)
    }
    }
    """

    LIST_MESSAGE = """
    {
    "msg": {
        "text": "Choose a category:",  #(MAXIMUM 4096 CHARACTERS)
        "interaction_type": "list",
        "list_message": {
        "button_text": "View categories",  #(MAXIMUM 15 CHARACTERS)
        "list_items": [
            {
            "title": "Smartphones",                     #(MAXIMUM 15 CHARACTERS)
            "description": "iPhone, Samsung and more",  #(MAXIMUM 60 CHARACTERS)
            "uuid": "1"
            },
            {
            "title": "Notebooks",				#(MAXIMUM 15 CHARACTERS)
            "description": "Dell, Lenovo, Acer",		#(MAXIMUM 60 CHARACTERS)
            "uuid": "2"
            }
        ]  #(MAXIMUM 10 ITEMS)
        }
    }
    }
    """

    CTA_URL = """
    {
    "msg": {
        "text": "Click the button below to access more information!",  #(MAXIMUM 1024 CHARACTERS)
        "interaction_type": "cta_url",
        "cta_url": {
        "url": "https://example.com",
        "display_text": "Access now"  #(MAXIMUM 15 CHARACTERS)
        }
    }
    }
    """

    CATALOG = """
    {
    "msg": {
        "text": "Confira nossos produtos disponíveis para entrega no seu CEP:", #(MAXIMUM 1024 CHARACTERS)
        "header": {
        "text": "Produtos disponíveis",  #(MAXIMUM 60 CHARACTERS)
        "type": "text"
        },
        "footer": "Entrega disponível para seu CEP",  #(MAXIMUM 60 CHARACTERS)
        "catalog_message": {
        "send_catalog": false,
        "action_button_text": "Ver detalhes",  #(MAXIMUM 15 CHARACTERS)
        "products": [  	#CATEGORYS
            {
            "product": "Tipo de produto A",
            "product_retailer_ids": [
                "produto_id_A1#loja_id",
                "produto_id_A2#loja_id",
                "produto_id_A3#loja_id"
            ]
            },
            {
            "product": "Tipo de produto B",
            "product_retailer_ids": [
                "produto_id_B1#loja_id",
                "produto_id_B2#loja_id",
                "produto_id_B3#loja_id"
            ]
            },
            {
            "product": "Tipo de produto C",
            "product_retailer_ids": [
                "produto_id_C1#loja_id",
                "produto_id_C2#loja_id",
                "produto_id_C3#loja_id"
            ]
            },
            {
            "product": "Tipo de produto D",
            "product_retailer_ids": [
                "produto_id_D1#loja_id",
                "produto_id_D2#loja_id",
                "produto_id_D3#loja_id"
            ]
            }
        ]
        }
    }
    }
    """

    def get_all_formats(self) -> List[str]:
        return [self.SIMPLE_TEXT, self.QUICK_REPLIES, self.LIST_MESSAGE, self.CTA_URL, self.CATALOG]

    def get_all_formats_string(self) -> str:
        return "\n".join(self.get_all_formats())


INSTRUCTIONS_SIMPLE_TEXT = []

INSTRUCTIONS_QUICK_REPLIES = [
    "ALWAYS send the following sentence at the end of your response: USE THE '<components>QUICK_REPLIES</components>'",
    "Use this component when you want to offer up to 3 quick reply options to the user.",
    "Each quick reply option must have a maximum of 15 characters.",
    "The main message must be a maximum of 1024 characters.",
]

INSTRUCTIONS_CATALOG = [
    "SEMPRE envie a seguinte frase ao final da sua resposta: '<components>CATALOG</components>'",
    (
        "NUNCA oculte ou omita QUALQUER informação do produto, especialmente: ProductID, SellerID, "
        "Especificações completas, Descrições completas, Valores, Códigos de barras, Dimensões e "
        "Qualquer outra informação disponível."
    ),
    "NUNCA crie um sellerId, SEMPRE chame o action group responsável por buscar o sellerId.",
    "Destaque informações importantes como ProductID e SellerID.",
    "Sempre apresente todas as informações de forma organizada e clara.",
]

INSTRUCTIONS_LIST_MESSAGE = [
    "SEMPRE envie a seguinte frase ao final da sua resposta: '<components>LIST_MESSAGE</components>'",
    (
        "SEMPRE estruture sua resposta como um lista de mensagens, com título(MAXIMUM 20 CHARACTERS), "
        "descrição(MAXIMUM 60 CHARACTERS), link e uuid(ordem de exibição)(MAXIMUM 10 ITEMS). "
        "Fique atento aos limites de caracteres para cada campo, não exceda os limites."
    ),
]

INSTRUCTIONS_CTA_URL = [
    "SEMPRE envie a seguinte frase ao final da sua resposta: USE THE '<components>CTA_URL</components>'",
    "SEMPRE que identificar ou receber links importantes, envie-os de forma clara e direta",
    "Ao compartilhar links, apresente-os de maneira estruturada e legível para o usuário",
]

INSTRUCTIONS = {
    "simple_text": INSTRUCTIONS_SIMPLE_TEXT,
    "quick_replies": INSTRUCTIONS_QUICK_REPLIES,
    "list_message": INSTRUCTIONS_LIST_MESSAGE,
    "catalog": INSTRUCTIONS_CATALOG,
    "cta_url": INSTRUCTIONS_CTA_URL,
}
