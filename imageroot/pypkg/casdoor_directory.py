"""Manage the Casdoor LDAP connector owned by this NS8 instance."""
import base64
import fcntl
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

import agent
from agent.ldapproxy import Ldapproxy

STATE = Path(os.environ["AGENT_STATE_DIR"])
CONFIG = STATE / "ldap.json"
TOKEN = STATE / "directory-token.json"
# Client ID and secret of the module's private Casdoor application (mode 0600).
MACHINE = STATE / "machine.json"
DATABASE_ENV = STATE / "database.env"
ADMIN_STATE = STATE / "admin-password.json"
MACHINE_APP = "ns8-module"


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def write(path, value):
    os.umask(0o077)
    with tempfile.NamedTemporaryFile(mode="w", dir=STATE, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream)
            stream.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def domains():
    proxy = Ldapproxy()
    try:
        names = proxy.get_domains_list()
    except AssertionError:
        # A node without an LDAP proxy can still host Casdoor.
        return []
    return sorted(name for name in names
                  if proxy.domains.get(name, {}).get("schema") in ("ad", "rfc2307"))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def machine_credentials():
    """Return the module's client credentials, generating them on first use."""
    creds = read(MACHINE)
    if not creds.get("client_id") or not creds.get("client_secret"):
        creds = {"client_id": secrets.token_hex(10), "client_secret": secrets.token_hex(20)}
        write(MACHINE, creds)
    return creds


def init_data():
    """Casdoor init data: a private built-in application used only for module API calls.

    Casdoor applies it at every start with initDataNewOnly=true, so it only adds the
    application when it is missing and never touches existing objects.
    """
    creds = machine_credentials()
    return {"applications": [{
        "owner": "admin", "name": MACHINE_APP, "displayName": "NS8 module (do not delete)",
        "organization": "built-in", "cert": "cert-built-in",
        "clientId": creds["client_id"], "clientSecret": creds["client_secret"],
        "grantTypes": ["client_credentials"], "redirectUris": [], "tags": [],
        "enablePassword": False, "enableSignUp": False, "disableSignin": True,
    }]}


def base_url():
    return "http://127.0.0.1:" + os.environ["TCP_PORT"]


def wait_ready(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with build_opener(NoRedirect()).open(base_url() + "/api/health", timeout=5) as response:
                if json.load(response).get("status") == "ok":
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def auth_header(host=None):
    token = read(TOKEN)
    # A pasted administrator token still overrides the machine credentials.
    if token.get("token") and (host is None or token.get("host") in (None, host)):
        return "Bearer " + token["token"]
    creds = read(MACHINE)
    if not creds.get("client_id"):
        raise RuntimeError("The module API credentials are missing. Restart Casdoor or set an API token.")
    raw = (creds["client_id"] + ":" + creds["client_secret"]).encode()
    return "Basic " + base64.b64encode(raw).decode()


def api(host, action, *, query=None, body=None, form=None):
    headers = {"Authorization": auth_header(host), "Accept": "application/json"}
    data = None
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = Request(base_url() + "/api/" + action + ("?" + urlencode(query) if query else ""),
                      data=data, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        raise RuntimeError(f"Casdoor {action} failed. Check that Casdoor is running.") from None
    if result.get("status") != "ok":
        # The message never contains request secrets.
        raise RuntimeError(f"Casdoor rejected {action}: {result.get('msg', '')}")
    return result.get("data")


def machine_ok():
    try:
        api(None, "get-organization", query={"id": "admin/built-in"})
        return True
    except RuntimeError:
        return False


def ensure_organization(organization):
    if api(None, "get-organization", query={"id": "admin/" + organization}):
        return
    app = "app-" + organization
    api(None, "add-organization", body={
        "owner": "admin", "name": organization, "displayName": organization,
        "passwordType": "bcrypt", "defaultApplication": app,
        "websiteUrl": "", "enableSoftDeletion": False, "isProfilePublic": False,
    })
    if not api(None, "get-application", query={"id": "admin/" + app}):
        host = os.environ.get("TRAEFIK_HOST", "")
        api(None, "add-application", body={
            "owner": "admin", "name": app, "displayName": organization,
            "organization": organization, "cert": "cert-built-in",
            "enablePassword": True, "enableSignUp": False,
            "grantTypes": ["authorization_code", "refresh_token"],
            "redirectUris": [f"https://{host}/callback"] if host else [],
            "tags": [], "expireInHours": 168, "refreshExpireInHours": 168,
        })


# --- built-in admin password -------------------------------------------------

def env_value(key):
    if not DATABASE_ENV.exists():
        return ""
    for line in DATABASE_ENV.read_text().splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return ""


def set_env_value(key, value):
    lines = [line for line in DATABASE_ENV.read_text().splitlines() if not line.startswith(key + "=")]
    lines.append(key + "=" + value)
    os.umask(0o077)
    with tempfile.NamedTemporaryFile(mode="w", dir=STATE, delete=False) as stream:
        stream.write("\n".join(lines) + "\n")
        temporary = stream.name
    os.chmod(temporary, 0o600)
    os.replace(temporary, DATABASE_ENV)


def quote(value):
    tag = "$ns8" + secrets.token_hex(8) + "$"
    assert tag not in value
    return tag + value + tag


def psql(database, script):
    """Run SQL through stdin, so values never appear in argv."""
    result = subprocess.run(["podman", "exec", "-i", "postgresql-app", "psql", "-U", "postgres",
                             "-d", database, "-tA", "-q", "-v", "ON_ERROR_STOP=1"],
                            input=script, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError("PostgreSQL query failed")
    return result.stdout.strip()


def admin_hash():
    row = psql("casdoor", "SELECT password_type || '|' || password FROM \"user\" "
                          "WHERE owner = 'built-in' AND name = 'admin';\n")
    kind, _, digest = row.partition("|")
    return kind, digest


def password_matches(password, kind, digest):
    if not password or not digest:
        return False
    if kind == "plain":
        return secrets.compare_digest(password, digest)
    if kind == "bcrypt" and digest.startswith("$2"):
        # pgcrypto checks the hash locally: no sign-in attempt, no lockout counter.
        out = psql("postgres", "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n"
                               f"SELECT crypt({quote(password)}, {quote(digest)}) = {quote(digest)};\n")
        return out.splitlines()[-1] == "t"
    return False


def admin_password_status():
    """Return (stored password still valid, stored password is the generated one)."""
    initial = env_value("CASDOOR_ADMIN_PASSWORD_SOURCE") != "custom"
    try:
        kind, digest = admin_hash()
    except RuntimeError:
        return None, initial
    cache = read(ADMIN_STATE)
    if cache.get("digest") == digest and "valid" in cache:
        return cache["valid"], initial
    valid = password_matches(env_value("CASDOOR_INITIAL_PASSWORD"), kind, digest)
    write(ADMIN_STATE, {"digest": digest, "valid": valid})
    return valid, initial


def set_admin_password(password):
    if len(password) < 12 or " " in password:
        raise RuntimeError("The admin password needs at least 12 characters and no spaces.")
    try:
        api(None, "set-password", form={"userOwner": "built-in", "userName": "admin",
                                        "newPassword": password})
    except RuntimeError:
        # Without API access store the same bcrypt hash Casdoor uses for built-in.
        psql("postgres", "CREATE EXTENSION IF NOT EXISTS pgcrypto;\n")
        digest = psql("postgres", f"SELECT crypt({quote(password)}, gen_salt('bf', 10));\n")
        psql("casdoor", f"UPDATE \"user\" SET password = {quote(digest)}, password_type = 'bcrypt', "
                        "password_salt = '' WHERE owner = 'built-in' AND name = 'admin';\n")
    set_env_value("CASDOOR_INITIAL_PASSWORD", password)
    set_env_value("CASDOOR_ADMIN_PASSWORD_SOURCE", "custom")
    ADMIN_STATE.unlink(missing_ok=True)


def connector(settings):
    proxy = Ldapproxy()
    entry = proxy.get_domain(settings["domain"])
    if not entry or entry.get("schema") not in ("ad", "rfc2307"):
        raise RuntimeError("The selected NS8 directory proxy is unavailable.")
    ad = entry["schema"] == "ad"
    user_filter = ("(&(objectCategory=person)(objectClass=user)(sAMAccountName=*))"
                   if ad else "(objectClass=posixAccount)")
    hidden_filter = proxy.get_ldap_users_search_filter_clause(settings["domain"])
    return {
        "id": settings["id"], "owner": settings["organization"],
        "serverName": "NS8 directory " + settings["id"][:12],
        "host": "10.0.2.2", "port": int(entry["port"]),
        "username": entry["bind_dn"], "password": entry["bind_password"],
        "baseDn": entry["base_dn"], "enableSsl": False,
        "filter": f"(&{user_filter}{hidden_filter})" if hidden_filter else user_filter,
        "filterFields": ["sAMAccountName" if ad else "uid"],
        "autoSync": 0, "enableGroups": False, "enablePasswordReset": False,
    }


def reconcile(host, domain, organization, *, refresh=False):
    with (STATE / "directory.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = read(CONFIG)
        if refresh:
            domain, organization = current.get("domain", ""), current.get("organization", "")
        if domain and (not organization or organization == "built-in"):
            raise RuntimeError("Enter the name of a dedicated Casdoor organization.")
        if current and domain and (domain, organization) != (current["domain"], current["organization"]):
            raise RuntimeError("Disconnect the current directory before selecting a different one.")
        if not domain and not current:
            return
        if not domain:
            key = {"id": current["organization"] + "/" + current["id"]}
            if api(host, "get-ldap", query=key):
                api(host, "delete-ldap", body={"owner": current["organization"], "id": current["id"]})
            agent.bind_user_domains([], check=True)
            CONFIG.unlink()
            return
        if refresh and domain not in domains():
            return
        if domain not in domains():
            raise RuntimeError("Choose an available NS8 OpenLDAP or Samba AD domain.")
        # Persist ownership before the API call so an interrupted request can be retried.
        ensure_organization(organization)
        if not current:
            if api(host, "get-ldaps", query={"owner": organization}):
                raise RuntimeError("Select a Casdoor organization without existing LDAP connectors.")
            current = {"domain": domain, "organization": organization, "id": uuid4().hex}
            write(CONFIG, current)
        agent.bind_user_domains([domain], check=True)
        body = connector(current)
        key = {"id": organization + "/" + current["id"]}
        existing = api(host, "get-ldap", query=key)
        if existing:
            body["createdTime"] = existing.get("createdTime", "")
            body["lastSync"] = existing.get("lastSync", "")
        api(host, "update-ldap" if existing else "add-ldap", body=body)
