import { useCallback } from 'react'
import { useRunStep } from './useRunStep'
import { runControl } from '../shared/runControl'

export const useRunPhase = (onUpdate) => {
  const { run: runStep, runningIds } = useRunStep(onUpdate)

  const run = useCallback(
    async (phaseName, chainId, steps) => {
      runControl.reset()

      // replay phase: every step with a command, except one already running
      const runnable = steps.filter(
        (step) => step.status !== 'running' && (step.command || step.command_params || '').trim(),
      )

      for (const [i, step] of runnable.entries()) {
        if (runControl.stopped) break
        // run each step, after response next with little timeout for host
        if (i > 0) await new Promise((resolve) => setTimeout(resolve, 700))
        if (runControl.stopped) break
        await runStep(step, phaseName, chainId, onUpdate)
      }
    },
    [runStep, onUpdate],
  )

  return { run, runningIds }
}
