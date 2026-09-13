import { api } from '../shared/api/axios'

const BASE = '/cmd'

export const stepApi = {
  runLocalCommand: ({ chain_name, callback_display_id, command }) =>
    api.post(`${BASE}/run-command`, {
      chain_name,
      callback_display_id,
      command,
    }),

  runAgentCommand: ({ chain_name, callback_display_id, command_params, tool }) =>
    api.post(`${BASE}/run-agent-command`, {
      chain_name,
      callback_display_id,
      command_params: command_params ?? '',
      // TODO: fix the workaround in proc.py -> process_approved_cmd -> tool_name like local_impacket-wmiexec
      tool: tool ?? 'shell',
    }),
}
