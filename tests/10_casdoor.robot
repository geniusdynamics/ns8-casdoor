*** Settings ***
Library    SSHLibrary
Resource    casdoor.resource

*** Variables ***
# Any resolvable-looking name: the schema demands a dot, nothing resolves it.
${TEST_HOST}    casdoor.ns8-ci.test
${DOMAIN}    casdoorldap.test
${ADMUSER}    ldapadmin
${ADMPASS}    Nethesis,1234
${ORG}    ns8-users
${NEW_PASSWORD}    Robot-Chosen-Admin-Pass-42

*** Test Cases ***
Check if an OpenLDAP user domain can be created
    ${output}  ${rc} =    Execute Command    add-module ghcr.io/nethserver/openldap:latest 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ast.literal_eval($output)    modules=ast
    Set Suite Variable    ${ldap_id}    ${output.module_id}
    ${rc} =    Execute Command    api-cli run module/${ldap_id}/configure-module --data '{"provision": "new-domain", "domain": "${DOMAIN}", "admuser": "${ADMUSER}", "admpass": "${ADMPASS}"}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if casdoor is installed correctly
    ${output}  ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ast.literal_eval($output)    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}

Check if casdoor can be configured
    Run Module Action    ${module_id}    configure-module    {"host":"${TEST_HOST}","http2https":false,"lets_encrypt":false}

Check if casdoor configuration reads back
    ${config} =    Run Module Action    ${module_id}    get-configuration
    Should Be Equal    ${config}[host]    ${TEST_HOST}

Check Casdoor health through Traefik
    Wait Until Keyword Succeeds    2 min    5 sec    Casdoor Health Is OK    ${TEST_HOST}

Check if the module API credentials work on a fresh install
    Wait Until Keyword Succeeds    1 min    5 sec    Configuration Shows Working API Credentials    ${module_id}

Check if the initial admin password is revealed and signs in
    ${secret} =    Run Module Action    ${module_id}    reveal-admin-password
    Should Not Be Empty    ${secret}[password]
    Should Be True    ${secret}[valid]
    Set Suite Variable    ${initial_password}    ${secret}[password]
    ${status} =    Admin Login Status    ${TEST_HOST}    ${initial_password}
    Should Be Equal    ${status}    ok

Check if get-configuration hides the admin password
    ${output} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    Should Not Contain    ${output}    ${initial_password}
    ${config} =    Evaluate    json.loads($output)    modules=json
    Should Be True    ${config}[admin_password_is_initial]
    Should Not Be True    ${config}[admin_password_set]

Check if a domain and organization create the LDAP connector without a token
    Run Module Action    ${module_id}    configure-module    {"host":"${TEST_HOST}","http2https":false,"ldap_domain":"${DOMAIN}","ldap_organization":"${ORG}"}
    ${config} =    Run Module Action    ${module_id}    get-configuration
    Should Be Equal    ${config}[ldap_organization]    ${ORG}
    Should Not Be True    ${config}[api_token_override]
    ${connector} =    Execute Command    runagent -m ${module_id} python3 -c 'import json,os;print(json.load(open(os.environ["AGENT_STATE_DIR"]+"/ldap.json"))["id"])'
    ${output} =    Execute Command
    ...    curl --silent --insecure --resolve ${TEST_HOST}:443:127.0.0.1 --get --data-urlencode 'id=${ORG}/${connector}' --data-urlencode 'username=built-in/admin' --data-urlencode 'password=${initial_password}' https://${TEST_HOST}/api/get-ldap-users
    ${result} =    Evaluate    json.loads($output)    modules=json
    Should Be Equal    ${result}[status]    ok    ${output}
    Should Contain    ${output}    ${ADMUSER}
    ${org} =    Execute Command
    ...    curl --silent --insecure --resolve ${TEST_HOST}:443:127.0.0.1 --get --data-urlencode 'id=admin/${ORG}' --data-urlencode 'username=built-in/admin' --data-urlencode 'password=${initial_password}' https://${TEST_HOST}/api/get-organization
    Should Contain    ${org}    "defaultApplication":"app-${ORG}"

Check if setting your own admin password works
    Run Module Action    ${module_id}    configure-module    {"host":"${TEST_HOST}","http2https":false,"admin_password":"${NEW_PASSWORD}"}
    ${status} =    Admin Login Status    ${TEST_HOST}    ${NEW_PASSWORD}
    Should Be Equal    ${status}    ok
    ${status} =    Admin Login Status    ${TEST_HOST}    ${initial_password}
    Should Not Be Equal    ${status}    ok
    ${config} =    Run Module Action    ${module_id}    get-configuration
    Should Be True    ${config}[admin_password_set]
    ${secret} =    Run Module Action    ${module_id}    reveal-admin-password
    Should Be Equal    ${secret}[password]    ${NEW_PASSWORD}

Check if a short admin password is rejected
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '{"host":"${TEST_HOST}","admin_password":"short"}'
    ...    return_rc=True  return_stdout=False
    Should Not Be Equal As Integers    ${rc}  0

Check if casdoor is removed correctly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
