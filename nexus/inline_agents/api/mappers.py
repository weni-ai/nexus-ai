OFFICIAL_META_MAPPER = {}

MCP_MAPPER = {
    "product_concierge": {
        "VTEX": [
            {
                "name": "Default",
                "description": "Catalog/Search + Base price + Inventory",
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
            {
                "name": "Trade Policy",
                "description": "Support for multiple B2B commercial policies",
                "config": [],
            },
            {
                "name": "Marketplace",
                "description": "Seller consultation and bidding rules",
                "config": [],
            },
        ],
        "SYNERISE": [
            {
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
        ],
    }
}

CREDENTIALS_MAPPER = {
    "product_concierge": {
        "VTEX": {
            "Default": [
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
            "Trade Policy": [
                {
                    "name": "BASE_URL",
                    "label": "VTEX Base URL",
                    "placeholder": "https://your-store.myvtex.com",
                    "is_confidential": False,
                },
                {
                    "name": "COUNTRY_CODE",
                    "label": "Country",
                    "placeholder": "ARG",
                    "is_confidential": False,
                },
                {
                    "name": "STORE_URL",
                    "label": "Store Domain URL",
                    "placeholder": "https://www.your-store.com",
                    "is_confidential": False,
                },
                {
                    "name": "TRADE_POLICY",
                    "label": "Trade Policy (sc)",
                    "placeholder": "1",
                    "is_confidential": False,
                },
                {
                    "name": "UNIQUE_SELLER",
                    "label": "Single Seller",
                    "placeholder": "False",
                    "is_confidential": False,
                },
            ],
            "Marketplace": [
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
        },
        "SYNERISE": {
            "Default": [
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
        },
    }
}
