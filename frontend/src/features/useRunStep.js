import { useState, useCallback } from 'react'
import { stepApi } from '../entities/stepApi'
import { chainApi } from '../entities/chainApi'
import { STEP_STATUS, STEP_TYPES } from '../entities/types'

const cleanBytesOutput = (output) => {
  // output is raw cuz diffent langs on remote hosts
  if (!output || typeof output !== 'string') return output
  if (output.startsWith('b"') && output.endsWith('"')) {
    return unescapePythonBytes(output.slice(2, -1))
  }
  if (output.startsWith("b'") && output.endsWith("'")) {
    return unescapePythonBytes(output.slice(2, -1))
  }
  return output
}

const unescapePythonBytes = (s) =>
  // clean b'' stings of raw output
  s.replace(/\\(.)/g, (_, char) => {
    switch (char) {
      case 'n':
        return '\n'
      case 't':
        return '\t'
      case 'r':
        return '\r'
      case '\\':
        return '\\'
      default:
        return `\\${char}`
    }
  })

export const useRunStep = () => {
  const [runningIds, setRunningIds] = useState(new Set())

  const run = useCallback(async (step, phaseName, chainId, onUpdate) => {
    const id = step.id ?? step._tempId
    if (!id) return

    if (chainId && phaseName) {
      // cuz backend doesn't know current phase
      await chainApi.setPhase(chainId, phaseName)
    }

    // we cannot parallel steps for now, works for most kill chains
    setRunningIds((prev) => new Set(prev).add(id))
    onUpdate?.(id, { status: STEP_STATUS.RUNNING, raw_log: '' })

    try {
      let data
      // TODO: add status by WebSocket for long time operations, but needs backend proc refactoring
      if (step.step_type === STEP_TYPES.AGENT) {
        const res = await stepApi.runAgentCommand({
          chain_name: step.chain_name,
          callback_display_id: step.callback_display_id,
          command_params: step.command_params,
          tool: step.tool,
          is_analyze_llm: false,
        })
        data = res.data
      } else {
        const res = await stepApi.runLocalCommand({
          chain_name: step.chain_name,
          callback_display_id: step.callback_display_id,
          command: step.command,
          is_analyze_llm: false,
        })
        data = res.data
      }

      onUpdate?.(id, {
        status: STEP_STATUS.SUCCESS,
        raw_log: cleanBytesOutput(data.raw_output ?? ''),
      })
      return data
    } catch (err) {
      onUpdate?.(id, {
        status: STEP_STATUS.ERROR,
        raw_log: err?.response?.data?.detail ?? err.message,
      })
      throw err
    } finally {
      setRunningIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }, [])

  return { run, runningIds }
}
