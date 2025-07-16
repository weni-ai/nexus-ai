import jwt

from datetime import datetime, timedelta

from django.conf import settings

class JWTUsecase:

    def generate_jwt_token(self, project_uuid: str):
        payload = {
            "project_uuid": project_uuid,
            "exp": datetime.now(datetime.timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(datetime.timezone.utc)
        }
        token = jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm="RS256"
        )
        return token