# weni-django-keycloak-admin

Reusable policy layer for Keycloak-protected Django Admin sites. It delegates
the OIDC Authorization Code Flow to `mozilla-django-oidc` and adds:

- dedicated client configuration isolated from API/service OIDC;
- authorization by Keycloak client role;
- secure Admin login and RP-initiated logout;
- synchronization of Django Admin privileges;
- silent authorization revalidation with a maximum five-minute lease;
- Django system checks, structured events, and Prometheus counters.

## Integration

Install the package and add `weni_django_keycloak_admin` to `INSTALLED_APPS`.
Add `AdminAuthorizationRefreshMiddleware` after Django's
`AuthenticationMiddleware`, expose `weni_django_keycloak_admin.urls`, and use
`AdminOIDCBackend` (or a service subclass) as the human authentication backend.
Do not keep Django's `ModelBackend` enabled.

Configure `KEYCLOAK_ADMIN_OIDC` with `ISSUER`, OIDC endpoints, `CLIENT_ID`,
`CLIENT_SECRET`, and `AUTHORIZED_ROLE`. The Keycloak client must use
Authorization Code Flow with PKCE and map its client role into
`resource_access.<client-id>.roles` in the ID token.

The package expects exact callback and post-logout URIs. Production endpoints
must use HTTPS. Tokens and full claims must never be logged.

## Compatibility and releases

The supported matrix is Python 3.10–3.13, Django 4.2–5.x,
`mozilla-django-oidc` 4.x–5.x, and supported Keycloak releases implementing
standard OIDC discovery/endpoints. CI should test the lower and upper bounds
before publishing.

Releases use semantic versioning. Changes to settings, backend behavior,
session keys, URL names, or authorization decisions are public contract
changes. Upstream OIDC upgrades require the token, callback, logout, and
revocation contract suite to pass before release.
