# Casdoor as an OIDC provider for NS8 applications

## Manual application configuration

1. Create a Casdoor application in the intended organization. Use a confidential
   client if the consuming application supports one. Register its exact login
   callback URI and any supported logout return URI.
2. Use the issuer or OpenID discovery URL requested by the consuming module.
   For the instance issuer, start with
   `https://<casdoor-host>/.well-known/openid-configuration`. For an organization
   with its own issuer enabled, start with
   `https://<casdoor-host>/orgs/<organization>/.well-known/openid-configuration`.
   Read `issuer` from the actual discovery document and confirm that it matches
   the token's `iss`. Casdoor also exposes application-specific discovery at
   `/.well-known/<application>/openid-configuration` with application details.
3. Enter the client ID and secret in the consumer's manual OIDC settings.
   Start with `openid profile email` and confirm the consumer's claims and
   role requirements with a pilot user. Directory membership and application
   authorization are separate. Map role or group claims explicitly when a
   consumer requires them.

## Native NS8 provider discovery

The NS8 realm-style provider contract publishes an issuer prefix. Consumers
derive an issuer by appending the NS8 domain. Casdoor normally advertises the
instance issuer. It also supports an opt-in organization issuer of the form
`https://<host>/orgs/<organization>`. The organization-issuer path could fit the
existing prefix convention if the organization name exactly matches the NS8
domain and every registered client's tokens use that organization issuer. That
needs end-to-end verification and does not cover instance issuers or
organizations with other names.

This module leaves native provider advertisement disabled. It preserves Casdoor's
issuer and discovery URLs. Automatic consumer registration still needs a tested
NS8 provider contract and implementation for create, update, and revoke,
including exact issuer selection, authorization for the requesting module,
idempotent client ownership, redirect validation, and secret rotation.
Explicit issuer or discovery metadata returned at registration would cover
both Casdoor issuer modes and let existing realm-based providers retain their
behavior. Casdoor's own dynamic client registration endpoint does not by
itself implement the NS8 action and lifecycle contract.

## Keeping this guide current

Notes reviewed against Casdoor `v4.30.0`, NS8 core source
`00d25bc6534e2f2ffbf784de185a33cc7b804b25`, and the NS8 IdP reference
`428668941469be93fc200c508718171f3c9cdd04`. These are source references.
Track contract changes and interoperability findings in the
[NS8 provider discovery discussion](https://community.nethserver.org/t/ns8-idp-via-authentik-and-zitadel-identified-blockers-for-the-ns8-sso-provider-and-suggested-improvements/29433/3).
