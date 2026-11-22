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

### Administrator credentials

The administrator is `admin` in the `built-in` organization. The Settings page
offers **Copy initial password**: it runs the admin-only `reveal-admin-password`
action and copies the password to the clipboard without showing it. Readers
cannot run this action. NS8 keeps task output in Redis for a few hours, where
cluster administrators can read it; the same applies to a password typed in the
**Admin password** field.

The module checks the stored password against the bcrypt hash in the database
(with PostgreSQL pgcrypto, so no sign-in attempt is made). If someone changed the
password in Casdoor, the page says so; type a new password of at least 12
characters in **Admin password** to take control again. From a shell:

```sh
runagent -m casdoor1 casdoor-initial-password
```

### Automatic setup

At create time the module generates the client ID and secret of a private
application, `ns8-module`, in the `built-in` organization (stored in the 0600
file `state/machine.json`). Casdoor loads it at every start through
`initDataFile` with `initDataNewOnly=true`, so it is only added when missing and
existing objects are never changed; this also provisions modules upgraded from
1.0.0. The module calls the Casdoor API on `127.0.0.1` with HTTP Basic client
credentials. Casdoor 4.30 gives an application credential administrator rights
over its own organization only, and global rights for the built-in organization,
which creating organizations requires: keep this application private and do not
delete it.

Choose an NS8 user domain and type an organization name in Settings: the module
creates the organization, its `app-<organization>` login application and the LDAP
connector. A token pasted with `runagent -m casdoor1 casdoor-directory-token`
still overrides the module credentials.

- [Configure OpenLDAP or Samba AD directory login](docs/ns8-directory-login.md)
- [Configure manual OIDC and track NS8 provider discovery](docs/ns8-sso.md)

## Backup and restore

NS8 backs up the PostgreSQL database as a logical dump, the database credential
file, and the identity of the managed LDAP connector. The module API credentials are part of the backup.
After moving or restoring an instance, save the NS8 settings to reconcile the
connector with the destination node's LDAP proxy.
Keep an independent local administrator available for this operation.
