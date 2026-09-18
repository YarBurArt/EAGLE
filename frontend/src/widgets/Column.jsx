import { useRef, useState, useEffect } from 'react'
import { StepCard } from './StepCard'
import { getAvailablePhasesAfter, getAvailablePhasesBefore } from '../shared/config/mitre'
import { PlusCircleIcon, MinusCircleIcon, PlayIcon, XIcon } from '@phosphor-icons/react'
import { IconButton, DashedIconButton, DropdownItem } from './UIComponents'

// for column resize
const MIN_WIDTH = 320
const MAX_WIDTH = 700
const DEFAULT_WIDTH = 420

export const Column = ({
  phase,
  index: _index,
  steps,
  width = DEFAULT_WIDTH,
  onWidthChange,
  onAddStep,
  onUpdateStep,
  onDeleteStep,
  onRunStep,
  onCopyStep,
  onRunPhase,
  onInsertPhase,
  onInsertPhaseBefore,
  onRemovePhase,
  onSetPhase,
  isActive,
  isLast,
  existingOrders,
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [beforeDropdownOpen, setBeforeDropdownOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [beforeSearch, setBeforeSearch] = useState('')
  const dropdownRef = useRef(null)
  const beforeDropdownRef = useRef(null)

  useEffect(() => {
    if (!dropdownOpen) return
    const onClick = (e) => {
      // if click outside new Next phase dropdown menu then close
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [dropdownOpen])

  useEffect(() => {
    if (!beforeDropdownOpen) return
    const onClick = (e) => {
      // if click outside new Prev phase dropdown menu then close
      if (beforeDropdownRef.current && !beforeDropdownRef.current.contains(e.target)) {
        setBeforeDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [beforeDropdownOpen])

  // dynamic column resize for long commands and raw outputs, only for prev column on click
  const startResize = (e) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = width

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const onMove = (ev) => {
      // check on correct phase column width
      const next = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth + (ev.clientX - startX)))
      onWidthChange(next)
    }
    const onUp = () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  // check is new phase correct by UCKC
  const availablePhases = getAvailablePhasesAfter(phase.order, existingOrders)
  const filteredPhases = availablePhases.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.desc.toLowerCase().includes(search.toLowerCase()),
  )

  const availablePhasesBefore = getAvailablePhasesBefore(phase.order, existingOrders)
  const filteredPhasesBefore = availablePhasesBefore.filter(
    (p) =>
      p.name.toLowerCase().includes(beforeSearch.toLowerCase()) ||
      p.desc.toLowerCase().includes(beforeSearch.toLowerCase()),
  )

  return (
    <>
      <div
        className="shrink-0 cursor-pointer"
        style={{ width: `${width}px` }}
        onClick={() => onSetPhase(phase.name)}
      >
        <div
          className={`relative mb-2 flex items-center justify-between gap-2 rounded-md border border-subtle bg-card p-2 ${isActive ? 'ring-1 ring-accent' : ''}`}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="shrink-0 rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold text-accent">
              {String(phase.order).padStart(2, '0')}
            </span>
            <span className="truncate text-xs font-semibold text-primary">{phase.name}</span>
          </div>

          <div className="flex shrink-0 gap-1">
            <DashedIconButton
              onClick={() => setBeforeDropdownOpen((v) => !v)}
              title="Insert phase before"
            >
              <MinusCircleIcon />
            </DashedIconButton>
            <DashedIconButton onClick={() => setDropdownOpen((v) => !v)} title="Insert phase after">
              <PlusCircleIcon />
            </DashedIconButton>
            <IconButton onClick={onRunPhase} title="Run all steps in phase" hover="success">
              <PlayIcon />
            </IconButton>
            <IconButton onClick={onRemovePhase} title="Remove phase" hover="danger">
              <XIcon />
            </IconButton>
          </div>

          {dropdownOpen && (
            <div
              ref={dropdownRef}
              className="absolute right-0 top-full z-50 mt-1 max-h-80 min-w-[280px] overflow-y-auto rounded-md border border-default bg-dropdown shadow-xl"
            >
              <div className="sticky top-0 bg-dropdown px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
                Insert after {phase.name}
              </div>
              <input
                autoFocus
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search..."
                className="w-full border-b border-subtle bg-dropdown px-3 py-1.5 text-xs text-primary outline-none"
              />
              {filteredPhases.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted">No available phases</div>
              ) : (
                filteredPhases.map((p) => (
                  <DropdownItem
                    key={p.id}
                    onClick={() => {
                      onInsertPhase(phase.id, p.id)
                      setDropdownOpen(false)
                      setSearch('')
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-primary">{p.name}</div>
                      <div className="text-[10px] text-muted">{p.desc}</div>
                    </div>
                    <span className="text-muted">+</span>
                  </DropdownItem>
                ))
              )}
            </div>
          )}

          {beforeDropdownOpen && (
            <div
              ref={beforeDropdownRef}
              className="absolute right-0 top-full z-50 mt-1 max-h-80 min-w-[280px] overflow-y-auto rounded-md border border-default bg-dropdown shadow-xl"
            >
              <div className="sticky top-0 bg-dropdown px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted">
                Insert before {phase.name}
              </div>
              <input
                autoFocus
                type="text"
                value={beforeSearch}
                onChange={(e) => setBeforeSearch(e.target.value)}
                placeholder="Search..."
                className="w-full border-b border-subtle bg-dropdown px-3 py-1.5 text-xs text-primary outline-none"
              />
              {filteredPhasesBefore.length === 0 ? (
                <div className="px-3 py-2 text-xs text-muted">No available phases</div>
              ) : (
                filteredPhasesBefore.map((p) => (
                  <DropdownItem
                    key={p.id}
                    onClick={() => {
                      onInsertPhaseBefore(phase.id, p.id)
                      setBeforeDropdownOpen(false)
                      setBeforeSearch('')
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-primary">{p.name}</div>
                      <div className="text-[10px] text-muted">{p.desc}</div>
                    </div>
                    <span className="text-muted">+</span>
                  </DropdownItem>
                ))
              )}
            </div>
          )}
        </div>

        <div className="space-y-0">
          {steps.length === 0 ? (
            <div className="rounded-md border border-dashed border-subtle p-5 text-center text-xs text-muted">
              No steps yet
            </div>
          ) : (
            steps.map((step) => (
              <StepCard
                key={step.id ?? step._tempId}
                step={step}
                onRun={onRunStep}
                onDelete={onDeleteStep}
                onCopy={onCopyStep}
                onUpdate={onUpdateStep}
              />
            ))
          )}
        </div>

        <button
          onClick={(e) => { e.stopPropagation(); onAddStep(); }}
          className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-default bg-transparent py-2 text-xs text-muted transition-colors hover:border-accent hover:bg-accent/5 hover:text-accent"
        >
          <PlusCircleIcon /> Add step
        </button>
      </div>

      {!isLast && (
        <div
          onMouseDown={startResize}
          className="group flex w-2 shrink-0 cursor-col-resize items-center justify-center"
        >
          <div className="h-8 w-0.5 rounded bg-default transition-all group-hover:h-12 group-hover:bg-accent" />
        </div>
      )}
    </>
  )
}
