import { useState, useCallback, useRef } from 'react'
import { Column } from '../../widgets/Column'
import { UCKC_PHASES } from '../../shared/config/mitre'
import { STEP_STATUS, STEP_TYPES } from '../../entities/types'
import { useRunStep } from '../../features/useRunStep'
import { useRunPhase } from '../../features/useRunPhase'
import { useAddPhase } from '../../features/useAddPhase'

export const ChainCanvas = ({ currentChain, onSetPhase }) => {
  const tempIdRef = useRef(0)

  const [phases, setPhases] = useState(() => {
    const phase = UCKC_PHASES.find((p) => p.name === currentChain.current_phase_name)
    return phase ? [phase] : []
  })
  const [widths, setWidths] = useState(() => {
    const phase = UCKC_PHASES.find((p) => p.name === currentChain.current_phase_name)
    return phase ? { [phase.id]: 420 } : {}
  })
  const [stepsByPhase, setStepsByPhase] = useState({})

  const updateStep = useCallback((stepId, patch) => {
    setStepsByPhase((prev) => {
      const next = { ...prev }
      for (const phase of Object.keys(next)) {
        next[phase] = next[phase].map((s) =>
          s.id === stepId || s._tempId === stepId ? { ...s, ...patch } : s,
        )
      }
      return next
    })
  }, [])

  const { run } = useRunStep()
  const { run: runPhase } = useRunPhase(updateStep)
  const { addPhase: handleAddPhase } = useAddPhase(currentChain?.chain_id ?? null)

  const addStep = useCallback(
    (phaseId) => {
      tempIdRef.current += 1
      // default API vars for run-command's
      const newStep = {
        _tempId: tempIdRef.current,
        chain_name: currentChain?.chain_name ?? '',
        step_type: STEP_TYPES.LOCAL,
        callback_display_id: 0,
        tool_name: '',
        command: '',
        command_params: '',
        tool: 'shell',
        status: STEP_STATUS.PENDING,
        raw_log: '',
      }
      setStepsByPhase((prev) => ({
        ...prev,
        [phaseId]: [...(prev[phaseId] ?? []), newStep],
      }))
    },
    [currentChain],
  )

  const deleteStep = useCallback((stepId) => {
    setStepsByPhase((prev) => {
      const next = { ...prev }
      for (const phase of Object.keys(next)) {
        next[phase] = next[phase].filter((s) => s.id !== stepId && s._tempId !== stepId)
      }
      return next
    })
  }, [])
  // for now just copy logs
  const copyStep = (step) => {
    const text = `Type: ${step.step_type}\nTool: ${step.tool_name}\nID: ${step.callback_display_id}\nStatus: ${step.status}\n\n${step.step_type === 'agent' ? 'Params' : 'Command'}:\n${step.step_type === 'agent' ? step.command_params : step.command}\n\nOutput:\n${step.raw_log}`
    navigator.clipboard.writeText(text)
  }
  // Backend don't know about phases, it know current phase for step, 
  // so if phase without runned steps, then should be store on frontend side for now  
  const removePhase = useCallback((phaseId) => {
    if (!window.confirm('Remove this phase?')) return
    setPhases((prev) => prev.filter((p) => p.id !== phaseId))
    setStepsByPhase((prev) => {
      const { [phaseId]: _, ...rest } = prev
      return rest
    })
  }, [])

  const insertPhaseAfter = useCallback((afterId, newPhaseId) => {
    const newPhase = UCKC_PHASES.find((p) => p.id === newPhaseId)
    if (!newPhase) return
    setPhases((prev) => {
      const idx = prev.findIndex((p) => p.id === afterId)
      if (idx === -1) return prev
      return [...prev.slice(0, idx + 1), newPhase, ...prev.slice(idx + 1)]
    })
    setWidths((prev) => ({ ...prev, [newPhaseId]: 420 }))
  }, [])

  const insertPhaseBefore = useCallback((beforeId, newPhaseId) => {
    const newPhase = UCKC_PHASES.find((p) => p.id === newPhaseId)
    if (!newPhase) return
    setPhases((prev) => {
      const idx = prev.findIndex((p) => p.id === beforeId)
      if (idx === -1) return prev
      return [...prev.slice(0, idx), newPhase, ...prev.slice(idx)]
    })
    setWidths((prev) => ({ ...prev, [newPhaseId]: 420 }))
  }, [])

  const onInsertPhase = useCallback(
    async (originId, newPhaseId) => {
      const newPhase = UCKC_PHASES.find((p) => p.id === newPhaseId)
      if (!newPhase || !currentChain) return
      try {
        await handleAddPhase(newPhase.name)
      } catch {
        return
      }
      insertPhaseAfter(originId, newPhaseId)
    },
    [currentChain, handleAddPhase, insertPhaseAfter],
  )

  const onInsertPhaseBefore = useCallback(
    async (originId, newPhaseId) => {
      const newPhase = UCKC_PHASES.find((p) => p.id === newPhaseId)
      if (!newPhase || !currentChain) return
      try {
        await handleAddPhase(newPhase.name)
      } catch {
        return
      }
      insertPhaseBefore(originId, newPhaseId)
    },
    [currentChain, handleAddPhase, insertPhaseBefore],
  )

  const existingOrders = phases.map((p) => p.order)

  return (
    <main className="flex-1 overflow-x-auto p-4">
      <div className="flex min-w-max items-start gap-4">
        {phases.map((phase, idx) => (
          <Column
            key={phase.id}
            phase={phase}
            index={idx}
            steps={stepsByPhase[phase.id] ?? []}
            width={widths[phase.id] ?? 420}
            onWidthChange={(w) => setWidths((prev) => ({ ...prev, [phase.id]: w }))}
            onAddStep={() => addStep(phase.id)}
            onUpdateStep={updateStep}
            onDeleteStep={deleteStep}
            onRunStep={(step) => run(step, updateStep)}
            onCopyStep={copyStep}
            onRunPhase={() => runPhase(phase.id, stepsByPhase[phase.id] ?? [])}
            onInsertPhase={onInsertPhase}
            onInsertPhaseBefore={onInsertPhaseBefore}
            onRemovePhase={() => removePhase(phase.id)}
            onSetPhase={onSetPhase}
            isActive={phase.name === currentChain.current_phase_name}
            isLast={idx === phases.length - 1}
            existingOrders={existingOrders}
          />
        ))}
      </div>
    </main>
  )
}
