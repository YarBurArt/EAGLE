import { api } from '../shared/api/axios'

const BASE = '/cmd'

export const stepApi = {
  runLocalCommand: ({ chain_name, callback_display_id, command, is_analyze_llm }) =>
    api.post(`${BASE}/run-command`, {
      chain_name,
      callback_display_id,
      command,
      is_analyze_llm,
    }),

  runAgentCommand: ({ chain_name, callback_display_id, command_params, tool, is_analyze_llm }) =>
    api.post(`${BASE}/run-agent-command`, {
      chain_name,
      callback_display_id,
      command_params: command_params ?? '',
      // TODO: fix the workaround in proc.py -> process_approved_cmd -> tool_name like local_impacket-wmiexec
      tool: tool ?? 'shell',
      is_analyze_llm,
    }),

  deleteStep: (stepId) => api.delete(`${BASE}/step/${stepId}`).then((res) => res.data),

  updateStep: (stepId, patch) => api.patch(`${BASE}/step/${stepId}`, patch).then((res) => res.data),
}
