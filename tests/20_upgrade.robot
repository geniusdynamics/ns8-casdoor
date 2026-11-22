*** Settings ***
Library    SSHLibrary
Resource    casdoor.resource

*** Variables ***
${RELEASE_IMAGE}    ghcr.io/geniusdynamics/casdoor:1.0.0
${UPGRADE_HOST}    casdoor-upgrade.ns8-ci.test

*** Test Cases ***
Check if the 1.0.0 release installs
    ${output}  ${rc} =    Execute Command    add-module ${RELEASE_IMAGE} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ast.literal_eval($output)    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}
    Run Module Action    ${module_id}    configure-module    {"host":"${UPGRADE_HOST}","http2https":false,"lets_encrypt":false}
    Wait Until Keyword Succeeds    2 min    5 sec    Casdoor Health Is OK    ${UPGRADE_HOST}

Check if the module upgrades from 1.0.0
    ${out}  ${rc} =    Execute Command    api-cli run update-module --data '{"module_url":"${IMAGE_URL}","instances":["${module_id}"],"force":true}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0    ${out}
    Wait Until Keyword Succeeds    2 min    5 sec    Casdoor Health Is OK    ${UPGRADE_HOST}

Check if the upgraded module provisioned its API credentials
    Wait Until Keyword Succeeds    1 min    5 sec    Configuration Shows Working API Credentials    ${module_id}
    ${secret} =    Run Module Action    ${module_id}    reveal-admin-password
    Should Be True    ${secret}[valid]
    ${status} =    Admin Login Status    ${UPGRADE_HOST}    ${secret}[password]
    Should Be Equal    ${status}    ok

Check if the upgraded module is removed
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
