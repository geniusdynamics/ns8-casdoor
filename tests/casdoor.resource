*** Settings ***
Library    SSHLibrary

*** Keywords ***
Run Module Action
    [Arguments]    ${module_id}    ${action}    ${data}={}
    ${output}  ${rc} =    Execute Command    api-cli run module/${module_id}/${action} --data '${data}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0    ${action} failed
    ${result} =    Evaluate    json.loads($output) if $output.strip() else {}    modules=json
    RETURN    ${result}

Casdoor Health Is OK
    [Arguments]    ${host}
    ${output}  ${rc} =    Execute Command
    ...    curl --silent --show-error --fail --insecure --resolve ${host}:443:127.0.0.1 https://${host}/api/health
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    ${health} =    Evaluate    json.loads($output)    modules=json
    Should Be Equal    ${health}[status]    ok

Admin Login Status
    [Arguments]    ${host}    ${password}
    ${body} =    Evaluate    json.dumps({"application": "app-built-in", "organization": "built-in", "username": "admin", "password": $password, "type": "login", "autoSignin": False})    modules=json
    ${output} =    Execute Command
    ...    printf '%s' '${body}' | curl --silent --insecure --resolve ${host}:443:127.0.0.1 -H 'Content-Type: application/json' --data-binary @- https://${host}/api/login
    ${result} =    Evaluate    json.loads($output)    modules=json
    RETURN    ${result}[status]

Configuration Shows Working API Credentials
    [Arguments]    ${module_id}
    ${config} =    Run Module Action    ${module_id}    get-configuration
    Should Be True    ${config}[api_credentials_ok]
