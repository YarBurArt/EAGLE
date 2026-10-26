import { useRef, useEffect, useState } from 'react'
import { STEP_TYPES, STEP_STATUS } from '../entities/types'
import { ArrowClockwiseIcon, PlayIcon } from '@phosphor-icons/react'
import { useMinify } from '../context/useMinify.js'
import {
  Input,
  TextInput,
  TransparentInput,
  Textarea,
  ReadonlyTextarea,
  ActionButton,
  RunButton,
} from './UIComponents'

const statusMeta = {
  pending: { label: 'pending', cls: 'text-muted' },
  running: { label: 'running', cls: 'text-warning' },
  success: { label: 'success', cls: 'text-success' },
  error: { label: 'error', cls: 'text-danger' },
  rejected: { label: 'rejected', cls: 'text-muted line-through' },
}

export const StepCard = ({ step, onRun, onDelete, onCopy, onUpdate }) => {
  const cmdRef = useRef(null)
  const outRef = useRef(null)
  const { minified } = useMinify()
  const [elapsed, setElapsed] = useState(0)
  const startTimeRef = useRef(null)
  const intervalRef = useRef(null)

  // backend drives run state by events stream, here just elapsed clock
  useEffect(() => {
    if (step.status === STEP_STATUS.RUNNING) {
      startTimeRef.current = Date.now()
      intervalRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000))
      }, 1000)
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [step.status])

  const autoResize = (el) => {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 300) + 'px'
  }

  useEffect(() => {
    autoResize(cmdRef.current)
    autoResize(outRef.current)
  }, [step.command, step.command_params, step.raw_log])

  const meta = statusMeta[step.status] ?? statusMeta.pending
  const isAgent = step.step_type === STEP_TYPES.AGENT

  return (
    <div className="mb-2 rounded-md border border-subtle bg-card p-2.5 transition-colors hover:border-default">
      {/* card types depends on proc.py */}
      <div className="mb-2 flex items-center justify-between gap-2">
        <Input
          as="select"
          value={step.step_type}
          onChange={(e) => onUpdate(step.id ?? step._tempId, { step_type: e.target.value })}
          className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide"
        >
          <option value={STEP_TYPES.LOCAL}>Local</option>
          <option value={STEP_TYPES.AGENT}>Agent</option>
        </Input>

        <div className="flex items-center gap-1">
          <label className="text-[10px] text-muted">C2 Display ID:</label>
          <Input
            type="text"
            inputMode="numeric"
            value={step.callback_display_id ?? 0}
            onChange={(e) =>
              onUpdate(step.id ?? step._tempId, {
                callback_display_id: parseInt(e.target.value) || 0,
              })
            }
            className="w-16 px-1.5 py-0.5 font-mono text-[10px] [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
        </div>
      </div>

      {/* tool name depends on mythic agent tools and proc.py */}
      <TransparentInput
        type="text"
        value={step.tool_name ?? ''}
        onChange={(e) => onUpdate(step.id ?? step._tempId, { tool_name: e.target.value })}
        placeholder="Tool name..."
      />

      {/* if runned on remote mythic agent */}
      {isAgent && (
        <>
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
            Tool
          </div>
          <TextInput
            type="text"
            value={step.tool ?? ''}
            onChange={(e) => onUpdate(step.id ?? step._tempId, { tool: e.target.value })}
            placeholder="shell, libinject, etc..."
          />
        </>
      )}

      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
        {isAgent ? 'Command Params' : 'Command'}
      </div>
      <Textarea
        ref={cmdRef}
        value={isAgent ? (step.command_params ?? '') : (step.command ?? '')}
        onChange={(e) =>
          onUpdate(step.id ?? step._tempId, {
            [isAgent ? 'command_params' : 'command']: e.target.value,
          })
        }
        placeholder={isAgent ? 'uname -a; lscpu; free...' : 'Enter command...'}
      />
      {/* TODO: TTPs like kill chain view on minify, or by LLM analyze summary
          for now just disable output on minified context
      */}
      {!minified && (
        <>
          <div className="mb-1 mt-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
            Output
          </div>
          <ReadonlyTextarea
            ref={outRef}
            value={step.raw_log ?? ''}
            onChange={(e) => onUpdate(step.id ?? step._tempId, { raw_log: e.target.value })}
            placeholder="Raw output / logs..."
            readOnly
          />
          {step.status === STEP_STATUS.RUNNING && (
            <div className="mt-2">
              <div className="text-[10px] font-mono text-muted">
                elapsed {elapsed}s, live output goes by events stream
              </div>
            </div>
          )}
        </>
      )}

      <div className="mt-2.5 flex items-center justify-between gap-1 border-t border-subtle pt-2">
        <div className="flex gap-1">
          <ActionButton
            hover="danger"
            onClick={(e) => {
              e.stopPropagation() // prevent other event handlers here
              if (!window.confirm('Delete this step?')) return
              onDelete(step.id ?? step._tempId)
            }}
          >
            Delete
          </ActionButton>
          <ActionButton
            hover="accent"
            onClick={(e) => {
              e.stopPropagation()
              onCopy(step)
            }}
          >
            Copy
          </ActionButton>
        </div>

        <span className={`font-mono text-[10px] ${meta.cls}`}>{meta.label}</span>
        {step.id && <span className="font-mono text-[10px] text-muted">ID: {step.id}</span>}

        <RunButton
          onClick={(e) => {
            e.stopPropagation()
            onRun(step)
          }}
          disabled={step.status === 'running'}
        >
          {step.status === 'running' ? <ArrowClockwiseIcon /> : <PlayIcon />} Run
        </RunButton>
      </div>
    </div>
  )
}
