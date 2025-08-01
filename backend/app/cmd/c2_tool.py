# from app.core.config import get_settings
from mythic import mythic

import os
from dotenv import load_dotenv


mythic_instance = None
load_dotenv()


async def init_mythic():
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


def check_status(callback_display_id: int):
    pass


async def get_payload_ids(callback_display_id):
    payload_a = await mythic.get_all_payloads(mythic=mythic_instance)
    payload = payload_a[0]  # temp
    return (payload.get('filemetum', {}).get('id'),
            payload.get('filemetum', {}).get('agent_file_id'))


async def execute_local_command(cmd, callback_display_id: int, timeout=500):
    global mythic_instance
    if mythic_instance is None:
        mythic_instance = await init_mythic()

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

    return str(output), mythic_t_id, mythic_p_id, mythic_p_uuid
