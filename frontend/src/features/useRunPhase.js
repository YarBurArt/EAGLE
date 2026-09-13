import { useCallback } from 'react'
import { useRunStep } from './useRunStep'

export const useRunPhase = (onUpdate) => {
  const { run: runStep, runningIds } = useRunStep(onUpdate)

  const run = useCallback(
    async (_phaseId, steps) => {
      for (const [i, step] of steps.entries()) {
        // run each step, after response next with little timeout for host
        if (i > 0) await new Promise((resolve) => setTimeout(resolve, 700))
        await runStep(step, onUpdate)
      }
    },
    [runStep, onUpdate],
  )

  return { run, runningIds }
}
