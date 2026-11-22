# Casdoor for NethServer 8

Casdoor provides application identity management and single sign-on. This module
runs Casdoor 4.30.0 and PostgreSQL 17 in a rootless Podman pod behind NS8 Traefik.
It requires NS8 core 3.20.1 or later.

## Install and configure

For testing, install an available module image by tag.

```sh
add-module ghcr.io/geniusdynamics/casdoor:<tag> 1
```

Point a fully qualified hostname at the NS8 node, enter it in the module
settings, and configure an HTTPS certificate before using the Casdoor console.
To retrieve the generated first-start password for `built-in/admin`, run the
following on the node hosting the instance. Substitute the actual module ID.

```sh
runagent -m casdoor1 casdoor-initial-password
```

Change that password after the first sign-in. The command displays the original
bootstrap password. Subsequent password changes take place in Casdoor.

- [Configure OpenLDAP or Samba AD directory login](docs/ns8-directory-login.md)
- [Configure manual OIDC and track NS8 provider discovery](docs/ns8-sso.md)

## Backup and restore

NS8 backs up the PostgreSQL database as a logical dump, the database credential
file, and the identity of the managed LDAP connector. After moving or restoring
an instance, configure the directory API credential again and save the NS8
settings to reconcile the connector with the destination node's LDAP proxy.
Keep an independent local administrator available for this operation.
