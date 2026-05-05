# Enterprise SSO Integration Guide

> Status: 📋 Planned — this document describes the target integration pattern.

## Supported Providers

KnowledgeOps Agent supports enterprise SSO via OpenID Connect (OIDC) and SAML 2.0.

## Configuration

```yaml
app:
  security:
    sso:
      enabled: ${APP_SSO_ENABLED:false}
      provider: ${APP_SSO_PROVIDER:oidc}   # oidc | saml
      # OIDC
      oidc:
        issuer-uri: ${APP_SSO_OIDC_ISSUER:}
        client-id: ${APP_SSO_OIDC_CLIENT_ID:}
        client-secret: ${APP_SSO_OIDC_CLIENT_SECRET:}
      # SAML
      saml:
        metadata-url: ${APP_SSO_SAML_METADATA_URL:}
        entity-id: ${APP_SSO_SAML_ENTITY_ID:}
```

## User Provisioning

When SSO is enabled:
1. User authenticates via corporate IdP
2. OIDC/SAML token maps to KnowledgeOps tenant + role
3. JWT is issued with tenant-scoped claims
4. Existing API-key auth continues to work for service accounts

## Roadmap

- [ ] Implement OIDC Relying Party via `spring-boot-starter-oauth2-client`
- [ ] Map IdP groups to KnowledgeOps RBAC roles
- [ ] Add SAML SP metadata endpoint
- [ ] Document Azure AD and Okta quick-start configs
