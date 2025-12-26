# Generated manually

from django.db import migrations


def migrate_credentials_to_config_options(apps, schema_editor):
    """
    Migrate TRADE_POLICY and UNIQUE_SELLER from MCPCredentialTemplate to MCPConfigOption.
    Also set default values for REGIONALIZATION, SALE_PRICE, TRADE_POLICY, and UNIQUE_SELLER.
    """
    MCP = apps.get_model("inline_agents", "MCP")
    MCPCredentialTemplate = apps.get_model("inline_agents", "MCPCredentialTemplate")
    MCPConfigOption = apps.get_model("inline_agents", "MCPConfigOption")

    # Find all credential templates that need to be migrated
    trade_policy_creds = MCPCredentialTemplate.objects.filter(name="TRADE_POLICY")
    unique_seller_creds = MCPCredentialTemplate.objects.filter(name="UNIQUE_SELLER")

    # Migrate TRADE_POLICY credentials to config options
    for cred in trade_policy_creds:
        mcp = cred.mcp
        # Check if config option already exists
        config_option, created = MCPConfigOption.objects.get_or_create(
            mcp=mcp,
            name="TRADE_POLICY",
            defaults={
                "label": cred.label or "Trade Policy",
                "type": "NUMBER",
                "default_value": 1,
                "order": cred.order,
                "is_required": False,
            },
        )
        # Update if it already existed
        if not created:
            config_option.label = cred.label or "Trade Policy"
            config_option.type = "NUMBER"
            config_option.default_value = 1
            config_option.order = cred.order
            config_option.save()

        # Delete the credential template
        cred.delete()

    # Migrate UNIQUE_SELLER credentials to config options
    for cred in unique_seller_creds:
        mcp = cred.mcp
        # Check if config option already exists
        config_option, created = MCPConfigOption.objects.get_or_create(
            mcp=mcp,
            name="UNIQUE_SELLER",
            defaults={
                "label": cred.label or "Unique Seller",
                "type": "SWITCH",
                "default_value": True,
                "order": cred.order,
                "is_required": False,
            },
        )
        # Update if it already existed
        if not created:
            config_option.label = cred.label or "Unique Seller"
            config_option.type = "SWITCH"
            config_option.default_value = True
            config_option.order = cred.order
            config_option.save()

        # Delete the credential template
        cred.delete()

    # Set default values for existing config options
    # REGIONALIZATION: default=True
    regionalization_options = MCPConfigOption.objects.filter(name="REGIONALIZATION")
    for option in regionalization_options:
        if option.default_value is None:
            option.default_value = True
            option.save()

    # SALE_PRICE/PRICE_SOURCE: default="SalePrice"
    # Check for both SALE_PRICE and PRICE_SOURCE (in case it's named differently)
    sale_price_options = MCPConfigOption.objects.filter(name__in=["SALE_PRICE", "PRICE_SOURCE"])
    for option in sale_price_options:
        if option.default_value is None:
            # If it's a SELECT type, look for SalePrice option
            if option.type == "SELECT" and option.options:
                default_value = None
                for opt in option.options:
                    if isinstance(opt, dict):
                        # Look for option with name "SalePrice"
                        if opt.get("name") == "SalePrice":
                            # Use the value from the option (e.g., "SALE") or "SalePrice" as fallback
                            default_value = opt.get("value", "SalePrice")
                            break
                
                if default_value:
                    option.default_value = default_value
                else:
                    # If no SalePrice found, use "SalePrice" as default
                    option.default_value = "SalePrice"
                option.save()
            else:
                # For non-SELECT types, use "SalePrice" as default
                option.default_value = "SalePrice"
                option.save()


def reverse_migration(apps, schema_editor):
    """
    Reverse migration: Convert TRADE_POLICY and UNIQUE_SELLER config options back to credentials.
    Note: This is a best-effort reversal and may not perfectly restore original state.
    """
    MCPCredentialTemplate = apps.get_model("inline_agents", "MCPCredentialTemplate")
    MCPConfigOption = apps.get_model("inline_agents", "MCPConfigOption")

    # Find config options to convert back
    trade_policy_options = MCPConfigOption.objects.filter(name="TRADE_POLICY")
    unique_seller_options = MCPConfigOption.objects.filter(name="UNIQUE_SELLER")

    # Convert TRADE_POLICY back to credential
    for option in trade_policy_options:
        mcp = option.mcp
        MCPCredentialTemplate.objects.get_or_create(
            mcp=mcp,
            name="TRADE_POLICY",
            defaults={
                "label": option.label or "Trade Policy (sc)",
                "placeholder": str(option.default_value) if option.default_value is not None else "1",
                "is_confidential": False,
                "order": option.order,
            },
        )
        option.delete()

    # Convert UNIQUE_SELLER back to credential
    for option in unique_seller_options:
        mcp = option.mcp
        MCPCredentialTemplate.objects.get_or_create(
            mcp=mcp,
            name="UNIQUE_SELLER",
            defaults={
                "label": option.label or "Single Seller",
                "placeholder": str(option.default_value) if option.default_value is not None else "False",
                "is_confidential": False,
                "order": option.order,
            },
        )
        option.delete()

    # Remove default values (set to None)
    MCPConfigOption.objects.filter(name="REGIONALIZATION").update(default_value=None)
    MCPConfigOption.objects.filter(name__in=["SALE_PRICE", "PRICE_SOURCE"]).update(default_value=None)


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0023_add_switch_radio_and_default_value_to_mcpconfigoption"),
    ]

    operations = [
        migrations.RunPython(migrate_credentials_to_config_options, reverse_migration),
    ]

