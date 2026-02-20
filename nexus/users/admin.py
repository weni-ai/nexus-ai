import secrets

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html

from .models import User, UserApiToken


class UserApiTokenInline(admin.TabularInline):
    model = UserApiToken
    extra = 0
    readonly_fields = ("token_hash", "salt", "token_prefix", "created_at", "last_used_at")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ("email", "is_active", "is_superuser", "is_staff")
    list_filter = ("is_superuser", "is_active", "groups")
    search_fields = ("email",)
    inlines = [UserApiTokenInline]
    actions = ["generate_global_token"]

    def generate_global_token(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one user to generate a token for.",
                level=messages.WARNING,
            )
            return

        user = queryset.first()
        name = f"Global Token - {user.email} - {timezone.now().strftime('%Y-%m-%d %H:%M')}"

        existing_token = UserApiToken.objects.filter(user=user, name=name).first()
        if existing_token:
            existing_token.enabled = False
            # Rename to avoid unique constraint collision
            suffix = f"_disabled_{secrets.token_hex(4)}"
            max_len = 255 - len(suffix)
            existing_token.name = existing_token.name[:max_len] + suffix
            existing_token.save()

            self.message_user(
                request,
                f"Previous token '{name}' has been disabled.",
                level=messages.INFO,
            )

        token, salt, token_hash, token_prefix = UserApiToken.generate_token_pair()

        UserApiToken.objects.create(
            user=user,
            name=name,
            token_hash=token_hash,
            salt=salt,
            token_prefix=token_prefix,
            scope="global",
        )

        self.message_user(
            request,
            format_html(
                "Token generated successfully for {}. <br/>"
                "<strong>Token:</strong> {} <br/>"
                "Please copy it now. It will not be shown again.",
                user.email,
                token,
            ),
            level=messages.SUCCESS,
        )

    generate_global_token.short_description = "Generate Global Token"


@admin.register(UserApiToken)
class UserApiTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "created_at", "last_used_at", "enabled")
    search_fields = ("user__email", "name")
    readonly_fields = ("token_hash", "salt", "token_prefix", "created_at", "last_used_at")
