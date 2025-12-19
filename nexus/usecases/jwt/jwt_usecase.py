from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings


class JWTUsecase:
    def generate_jwt_token(self, project_uuid: str):
        payload = {
            "project_uuid": project_uuid,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="RS256")
        return token

    def generate_broadcast_jwt_token(self):
        oidc_email = settings.OIDC_RP_EMAIL
        payload = {
            "email": oidc_email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="RS256")
        return token
