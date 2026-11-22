"""Manage the Casdoor LDAP connector owned by this NS8 instance."""
import fcntl
import json
import os
import tempfile
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


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def write(path, value):
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


def api(host, action, *, query=None, body=None):
    auth = read(TOKEN)
    if auth.get("host") != host or not auth.get("token"):
        raise RuntimeError("Set a Casdoor API token for this hostname with casdoor-directory-token.")
    request = Request(f"https://{host}/api/{action}" + ("?" + urlencode(query) if query else ""),
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={"Authorization": "Bearer " + auth["token"],
                               "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        raise RuntimeError(f"Casdoor {action} failed. Check HTTPS and the API token.") from None
    if result.get("status") != "ok":
        raise RuntimeError(f"Casdoor rejected {action}. Check the organization and API permissions.")
    return result.get("data")


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
