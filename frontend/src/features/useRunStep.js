import { useState, useCallback } from 'react'
import { stepApi } from '../entities/stepApi'
import { STEP_STATUS, STEP_TYPES } from '../entities/types'

export const useRunStep = () => {
  const [runningIds, setRunningIds] = useState(new Set())

  const run = useCallback(async (step, onUpdate) => {
    const id = step.id ?? step._tempId
    if (!id) return

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
        })
        data = res.data
      } else {
        const res = await stepApi.runLocalCommand({
          chain_name: step.chain_name,
          callback_display_id: step.callback_display_id,
          command: step.command,
        })
        data = res.data
      }

      onUpdate?.(id, {
        status: STEP_STATUS.SUCCESS,
        raw_log: data.raw_output ?? '',
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
