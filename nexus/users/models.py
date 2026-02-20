import hashlib
import hmac
import secrets
from typing import Optional

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def _create_user(self, email: str, password: Optional[str] = None, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: Optional[str] = None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: Optional[str] = None, **extra_fields):
        raise NotImplementedError("No superuser allowed")


class User(AbstractBaseUser, PermissionsMixin):
    USERNAME_FIELD = "email"

    email = models.EmailField("email", unique=True)
    language = models.CharField(
        max_length=64,
        choices=settings.LANGUAGES,
        default=settings.DEFAULT_LANGUAGE,
    )
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    @property
    def is_staff(self):
        return self.is_superuser


class UserApiToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=255)
    token_hash = models.CharField(max_length=128)
    token_prefix = models.CharField(max_length=32, db_index=True, null=True, blank=True)
    salt = models.CharField(max_length=64)
    scope = models.CharField(max_length=64, default="global")
    enabled = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")

    def __str__(self):
        return f"{self.user.email} - {self.name}"

    @staticmethod
    def hash_token(token: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}{token}".encode()).hexdigest()

    def matches(self, token: str) -> bool:
        if not self.enabled:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return hmac.compare_digest(self.token_hash, self.hash_token(token, self.salt))

    @staticmethod
    def generate_token_pair() -> tuple[str, str, str, str]:
        token = secrets.token_urlsafe(48)
        salt = secrets.token_hex(16)
        token_hash = UserApiToken.hash_token(token, salt)
        token_prefix = token[:8]
        return token, salt, token_hash, token_prefix
