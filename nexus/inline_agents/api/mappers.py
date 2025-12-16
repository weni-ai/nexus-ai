OFFICIAL_META_MAPPER = {}

MCP_MAPPER = {
    "product_concierge": {
        "VTEX": {
            "name": "Default",
            "description": "Catalog and Search with base price and inventory",
            "config": [
                {
                    "name": "REGIONALIZATION",
                    "label": "Regionalization",
                    "type": "CHECKBOX",
                    "options": [{"name": "Enable", "value": "true"}],
                },
                {
                    "name": "PRICE_SOURCE",
                    "label": "Price Source",
                    "type": "SELECT",
                    "options": [
                        {"name": "BasePrice", "value": "BASE"},
                        {"name": "SalePrice", "value": "SALE"},
                    ],
                },
            ],
        },
        "SYNERISE": {
            "name": "Default",
            "description": "Recommendations powered by Synerise",
            "config": [
                {
                    "name": "RECOMMENDATION_STRATEGY",
                    "label": "Strategy",
                    "type": "SELECT",
                    "options": [
                        {"name": "Bestsellers", "value": "BEST"},
                        {"name": "Personalized", "value": "PERSONALIZED"},
                    ],
                }
            ],
        },
    }
}

CREDENTIALS_MAPPER = {
    "product_concierge": {
        "VTEX": [
            {
                "name": "BASE_URL",
                "label": "VTEX Base URL",
                "placeholder": "https://{account}.vtexcommercestable.com.br",
                "is_confidential": False,
            },
            {
                "name": "COUNTRY_CODE",
                "label": "Country Code",
                "placeholder": "BRA",
                "is_confidential": False,
            },
            {
                "name": "STORE_URL",
                "label": "Store URL",
                "placeholder": "https://example.com",
                "is_confidential": False,
            },
            {
                "name": "UNIQUE_SELLER",
                "label": "Single Seller",
                "placeholder": "False",
                "is_confidential": False,
            },
        ],
        "SYNERISE": [
            {
                "name": "API_KEY",
                "label": "Synerise API Key",
                "placeholder": "sk-...",
                "is_confidential": True,
            },
            {
                "name": "TENANT_ID",
                "label": "Tenant ID",
                "placeholder": "tenant-123",
                "is_confidential": False,
            },
            {
                "name": "ENDPOINT",
                "label": "Endpoint URL",
                "placeholder": "https://api.synerise.com",
                "is_confidential": False,
            },
        ],
    }
}
