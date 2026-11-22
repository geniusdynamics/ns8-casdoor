*** Settings ***
Library    SSHLibrary

*** Variables ***
# Any resolvable-looking name: the schema demands a dot, nothing resolves it.
${TEST_HOST}    casdoor.ns8-ci.test

*** Test Cases ***
Check if casdoor is installed correctly
    ${output}  ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ast.literal_eval($output)    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}

Check if casdoor can be configured
    ${rc} =    Execute Command
    ...    api-cli run module/${module_id}/configure-module --data '{"host":"${TEST_HOST}","http2https":false,"lets_encrypt":false}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if casdoor configuration reads back
    ${output}  ${rc} =    Execute Command    api-cli run module/${module_id}/get-configuration --data '{}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    ${config} =    Evaluate    json.loads($output)    modules=json
    Should Be Equal    ${config}[host]    ${TEST_HOST}

Check Casdoor health through Traefik
    Should Not Be Empty    ${module_id}
    Wait Until Keyword Succeeds    2 min    5 sec    Casdoor Health Is OK

Check if casdoor is removed correctly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0


*** Keywords ***
Casdoor Health Is OK
    ${output}  ${rc} =    Execute Command
    ...    curl --silent --show-error --fail --insecure --resolve ${TEST_HOST}:443:127.0.0.1 https://${TEST_HOST}/api/health
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    ${health} =    Evaluate    json.loads($output)    modules=json
    Should Be Equal    ${health}[status]    ok
