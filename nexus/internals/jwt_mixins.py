from nexus.authentication.authentication import JWTAuthentication

class JWTProjectMixin:
    authentication_classes = [JWTAuthentication]
    permission_classes = ([])


    @property
    def get_project_uuid(self):
        return self.request.project_uuid

    @property
    def get_jwt_payload(self):
        return self.request.jwt_payload