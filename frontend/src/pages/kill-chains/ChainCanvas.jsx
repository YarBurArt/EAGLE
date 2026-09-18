import { useState, useCallback, useRef, useEffect } from 'react'
import { Column } from '../../widgets/Column'
import { UCKC_PHASES } from '../../shared/config/mitre'
import { STEP_STATUS, STEP_TYPES } from '../../entities/types'
import { chainApi } from '../../entities/chainApi'
import { stepApi } from '../../entities/stepApi'
import { useRunStep } from '../../features/useRunStep'
import { useRunPhase } from '../../features/useRunPhase'
import { useAddPhase } from '../../features/useAddPhase'
import { toast } from 'react-toastify'

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

  useEffect(() => {
    if (!currentChain) return
    const loadSteps = async () => {
      try {
        const data = await chainApi.getChainWithSteps(currentChain.chain_id)
        const stepsByPhaseMap = {}
        const phasesFromSteps = []
        
        for (const step of data.steps) {
          const phaseName = step.phase
          const phaseObj = UCKC_PHASES.find((p) => p.name === phaseName)
          const phaseId = phaseObj ? phaseObj.id : phaseName
          const isAgent = step.tool_name?.startsWith('agent_')
          if (!stepsByPhaseMap[phaseId]) {
            stepsByPhaseMap[phaseId] = []
            if (phaseObj) phasesFromSteps.push(phaseObj)
          }

          stepsByPhaseMap[phaseId].push({
            id: step.id,
            chain_name: currentChain.chain_name,
            step_type: isAgent ? STEP_TYPES.AGENT : STEP_TYPES.LOCAL,
            callback_display_id: step.callback_display_id ?? 0,
            tool_name: step.tool_name,
            command: isAgent ? '' : step.command,
            command_params: isAgent ? step.command : '',
            tool: isAgent ? step.tool_name.replace('agent_', '') : 'shell',
            status: step.status,
            raw_log: step.raw_log,
          })
        }
        setPhases((prev) => {
          const existingIds = new Set(prev.map((p) => p.id))
          const newPhases = phasesFromSteps.filter((p) => !existingIds.has(p.id))
          if (newPhases.length === 0) return prev
          return [...prev, ...newPhases].sort((a, b) => a.order - b.order)
        })
        setStepsByPhase((prev) => {
          const hasExistingSteps = Object.values(prev).some((s) => s.length > 0)
          if (hasExistingSteps) return prev
          return stepsByPhaseMap
        })
      } catch {
        toast.error('Steps load failed, backend maybe died')
      }
    }
    loadSteps()
  }, [currentChain])

  const updateStep = useCallback(async (stepId, patch) => {
    setStepsByPhase((prev) => {
      const next = { ...prev }
      for (const phase of Object.keys(next)) {
        next[phase] = next[phase].map((s) =>
          s.id === stepId || s._tempId === stepId ? { ...s, ...patch } : s,
        )
      }
      return next
    })
    if (stepId) {
      try {
        await stepApi.updateStep(stepId, patch)
        // cuz AttackStep table doesn't store specific order for now, so move step to the end of phase 
        setStepsByPhase((prev) => {
          const next = { ...prev }
          for (const phase of Object.keys(next)) {
            const list = next[phase]
            const idx = list.findIndex(
              (s) => s.id === stepId || s._tempId === stepId,
            )
            if (idx !== -1) {
              const [moved] = list.splice(idx, 1)
              next[phase] = [...list, moved]
              break
            }
          }
          return next
        })
        if (patch.command || patch.tool_name) {
          toast.info(
            'Step will be placed at the end of the chain after reload (due to AttackStep table ordering)',
          )
        }
      } catch {
        toast.error('Step update failed, check backend connection')
      }
    }
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

  const deleteStep = useCallback(
    async (stepId) => {
      const isTemp = !Object.values(stepsByPhase).some((steps) =>
        steps.some((s) => s.id === stepId && s.id != null),
      )
      if (!isTemp) {
        try {
          await stepApi.deleteStep(stepId)
        } catch {
          toast.error('Step delete failed, maybe not found')
        }
      }
      setStepsByPhase((prev) => {
        const next = { ...prev }
        for (const phase of Object.keys(next)) {
          next[phase] = next[phase].filter((s) => 
            s.id !== stepId && s._tempId !== stepId)
        }
        return next
      })
    },
    [stepsByPhase],
  )
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
            onRunStep={(step) => run(step, phase.name, currentChain.chain_id, updateStep)}
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
