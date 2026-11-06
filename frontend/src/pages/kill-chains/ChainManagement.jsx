import { useCallback, useEffect, useState } from 'react'
import { NavBar } from '../../widgets/Navbar'
import { AgentPanel } from '../agent/AgentPanel'
import { ChainCanvas } from './ChainCanvas'
import { chainApi } from '../../entities/chainApi'
import { useChainSwitch } from '../../features/useChainSwitch'
import { MinifyProvider } from '../../context/MinifyContext.jsx'
import { LinkIcon } from '@phosphor-icons/react'
import { toast } from 'react-toastify'

const PANEL_MIN_WIDTH = 320
const PANEL_DEFAULT_WIDTH = 380
const PANEL_MAX_RATIO = 0.5
const PANEL_COLLAPSED_KEY = 'eagle_agent_collapsed'
const PANEL_WIDTH_KEY = 'eagle_agent_width'

export const ChainManagement = () => (
  <MinifyProvider>
    <ChainManagementView />
  </MinifyProvider>
)

const ChainManagementView = () => {
  const {
    currentChain,
    loading,
    error: _error,
    initialized,
    switchChain,
    chains,
    createChain,
    deleteChain,
  } = useChainSwitch()

  const [panelWidth, setPanelWidth] = useState(() => {
    const stored = Number(localStorage.getItem(PANEL_WIDTH_KEY))
    return Number.isFinite(stored) && stored >= PANEL_MIN_WIDTH ? stored : PANEL_DEFAULT_WIDTH
  })
  const [panelCollapsed, setPanelCollapsed] = useState(
    () => localStorage.getItem(PANEL_COLLAPSED_KEY) === '1',
  )
  const [canvasReload, setCanvasReload] = useState(0)
  const [layout, setLayout] = useState(
    () => localStorage.getItem('eagle_phase_layout') || 'columns',
  )

  useEffect(() => {
    localStorage.setItem(PANEL_WIDTH_KEY, String(panelWidth))
  }, [panelWidth])

  const togglePanel = useCallback(() => {
    setPanelCollapsed((prev) => {
      localStorage.setItem(PANEL_COLLAPSED_KEY, prev ? '0' : '1')
      return !prev
    })
  }, [])

  const startPanelResize = useCallback(
    (event) => {
      event.preventDefault()
      const startX = event.clientX
      const startWidth = panelWidth
      const maxWidth = Math.max(PANEL_MIN_WIDTH, window.innerWidth * PANEL_MAX_RATIO)

      const onMove = (moveEvent) => {
        const next = Math.max(
          PANEL_MIN_WIDTH,
          Math.min(maxWidth, startWidth + moveEvent.clientX - startX),
        )
        setPanelWidth(next)
      }
      const onUp = () => {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }

      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)

      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    },
    [panelWidth],
  )

  // imported proposals are already persisted, so the canvas just refetches
  const handleImportDraft = useCallback(() => {
    setCanvasReload((value) => value + 1)
  }, [])

  const toggleLayout = useCallback(() => {
    setLayout((current) => {
      const next = current === 'columns' ? 'rows' : 'columns'
      localStorage.setItem('eagle_phase_layout', next)
      return next
    })
  }, [])

  const setCurrentPhase = useCallback(
    async (phaseName) => {
      if (!currentChain) return

      try {
        await chainApi.setPhase(currentChain.chain_id, phaseName)
        await switchChain(currentChain.chain_id)
      } catch {
        toast.error('Failed to set  UCKC phase')
      }
    },
    [currentChain, switchChain],
  )

  if (!currentChain) {
    return (
      <div className="flex min-h-screen flex-col bg-app text-primary">
        <NavBar
          chains={chains}
          onSelect={switchChain}
          onCreateChain={createChain}
          onDeleteChain={deleteChain}
          currentChain={currentChain}
        />
        <div className="flex flex-1 items-center justify-center">
          {!initialized || loading ? (
            <span className="text-sm text-muted">Loading chains...</span>
          ) : chains.length === 0 ? (
            <span className="text-sm text-muted">No chains yet — create one to start</span>
          ) : (
            <div className="flex flex-col gap-3">
              <h2 className="text-sm font-semibold text-secondary">Select a chain</h2>
              <div className="flex flex-col gap-1">
                {chains.map((c) => (
                  <button
                    key={c.chain_id}
                    onClick={() => switchChain(c.chain_id)}
                    className="group flex items-center gap-3 rounded-md border border-subtle bg-card px-4 py-3 text-left transition-colors hover:border-accent hover:bg-card-hover"
                  >
                    <LinkIcon className="shrink-0 text-muted group-hover:text-accent" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-primary">
                        {c.chain_name}
                      </div>
                      <div className="mt-0.5 text-xs text-muted">Phase: {c.current_phase_name}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-app text-primary">
      <NavBar
        chains={chains}
        onSelect={switchChain}
        onCreateChain={createChain}
        onDeleteChain={deleteChain}
        currentChain={currentChain}
        layout={layout}
        onToggleLayout={toggleLayout}
      />

      <div className="flex min-h-0 flex-1">
        <div className="h-full shrink-0" style={{ width: panelCollapsed ? 40 : panelWidth }}>
          <AgentPanel
            chainId={currentChain.chain_id}
            chainName={currentChain.chain_name}
            collapsed={panelCollapsed}
            onToggleCollapse={togglePanel}
            onImportDraft={handleImportDraft}
            onChainChanged={handleImportDraft}
          />
        </div>

        {!panelCollapsed && (
          <div
            onMouseDown={startPanelResize}
            className="group flex w-2 shrink-0 cursor-col-resize items-stretch justify-center bg-app"
            title="Resize analyst panel"
          >
            <span className="w-px bg-subtle transition-colors group-hover:bg-default" />
          </div>
        )}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ChainCanvas
            key={currentChain.chain_id}
            currentChain={currentChain}
            onSetPhase={setCurrentPhase}
            reloadToken={canvasReload}
            layout={layout}
          />
        </div>
      </div>
    </div>
  )
}
