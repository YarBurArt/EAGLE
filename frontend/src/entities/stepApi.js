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

  runBash: ({ chain_name, command, timeout }) =>
    // direct bash on host
    api.post(`${BASE}/run-bash`, { chain_name, command, timeout }),

  runAgentCommand: ({ chain_name, callback_display_id, command_params, tool, is_analyze_llm }) =>
    api.post(`${BASE}/run-agent-command`, {
      chain_name,
      callback_display_id,
      command_params: command_params ?? '',
      // TODO: fix the workaround in proc.py -> process_approved_cmd -> tool_name like local_impacket-wmiexec
      tool: tool ?? 'shell',
      is_analyze_llm,
    }),

  getStep: (stepId) => api.get(`${BASE}/step/${stepId}`).then((res) => res.data),

  analyzeStep: (stepId) => api.post(`${BASE}/step/${stepId}/analyze`).then((res) => res.data),

  // live ndjson events of step & tasks, cookies ride along
  streamStepEvents: (stepId, onEvent, signal) =>
    fetch(`${BASE}/step/${stepId}/events`, {
      signal,
    }).then(async (resp) => {
      if (!resp.ok || !resp.body) throw new Error(`step events status ${resp.status}`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()
        lines.forEach((line) => {
          if (!line.trim()) return
          try {
            onEvent(JSON.parse(line))
          } catch {
            // partial or broken row, skip it
          }
        })
      }
      if (buf.trim()) {
        try {
          onEvent(JSON.parse(buf))
        } catch {
          // leftover without newline
        }
      }
      return resp
    }),

  deleteStep: (stepId) => api.delete(`${BASE}/step/${stepId}`).then((res) => res.data),

  updateStep: (stepId, patch) => api.patch(`${BASE}/step/${stepId}`, patch).then((res) => res.data),
}
