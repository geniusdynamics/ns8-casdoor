# NS8 directory login in Casdoor

## Connect a directory

1. Configure Casdoor in NS8 and verify HTTPS and local `built-in/admin` login.
   Back up existing Casdoor data before connecting a directory.
2. Create a dedicated organization in Casdoor for the selected NS8 user
   domain. Use its internal name from the organization editor. Create a
   Casdoor application in that organization and enable the applicable sign-in
   options in Casdoor before testing its login page.
3. Obtain a Casdoor OAuth access token for an administrator authorized to read,
   add, update, and delete LDAP configurations in that organization. Use the
   authorization-code flow with an application you control and its registered
   redirect URI. Use the access token returned by the OAuth token endpoint.
   Enter it at the hidden prompt on the NS8 node hosting Casdoor.

   ```sh
   runagent -m casdoor1 casdoor-directory-token
   ```

   The token is tied to the configured hostname and stored locally with mode
   0600. Renew it before expiry to let NS8 refresh the connector after
   directory changes. To clear the credential, submit an empty value.
4. In the NS8 module settings, choose one OpenLDAP or Samba AD user domain, enter
   the dedicated Casdoor organization name, and save. NS8 binds the module to
   the domain and configures the organization connector against the node's LDAP
   proxy. LDAP traffic between the rootless pod and the loopback proxy stays on
   the node. Upstream LDAP transport is configured by NS8.
5. Check the connector in Casdoor. Use its LDAP user preview and sync a pilot
   user. Test that user's sign-in on the organization's application, then test
   the independent local administrator again. Repeat the pilot verification
   when changing the domain or upgrading the integration.

## Existing organizations and account lifecycle

Casdoor's LDAP workflow imports user records through LDAP sync and checks their
passwords against the directory on sign-in. The module leaves automatic sync,
group import, and LDAP password resets disabled. Use the Casdoor console to
review and import accounts. A successful import alone does not prove sign-in.

Keep each managed directory in a dedicated organization. Casdoor checks an
organization's LDAP connectors during authentication, so mixing directories in
one organization can create account overlap. Leave existing manually managed
organizations, connectors, application assignments, and user links in place
while you verify a pilot application.

To disconnect, clear the user domain in NS8 with a valid API token configured.
NS8 removes its own connector and proxy binding. Casdoor retains imported user
records and application assignments. Users relying on that connector lose
directory authentication. To reconnect, choose the domain again and verify the
affected users' sign-in with a pilot.

After restoring on a different node, re-enter an API token and save the settings
to refresh the LDAP proxy endpoint and credentials. If the directory is down,
use your independent local administrator.
