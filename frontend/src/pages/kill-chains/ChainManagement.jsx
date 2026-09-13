import { useCallback } from 'react'
import { NavBar } from '../../widgets/Navbar'
import { ChainCanvas } from './ChainCanvas'
import { chainApi } from '../../entities/chainApi'
import { useChainSwitch } from '../../features/useChainSwitch'
import { MinifyProvider } from '../../context/MinifyContext.jsx'
import { LinkIcon } from '@phosphor-icons/react'
import { toast } from 'react-toastify'

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
    <div className="flex min-h-screen flex-col bg-app text-primary">
      <NavBar
        chains={chains}
        onSelect={switchChain}
        onCreateChain={createChain}
        onDeleteChain={deleteChain}
        currentChain={currentChain}
      />

      <div className="border-b border-subtle px-5 py-2 text-xs text-muted">
        Current chain: <span className="font-medium text-secondary">{currentChain.chain_name}</span>
        <span className="ml-2">Phase: {currentChain.current_phase_name}</span>
      </div>

      <ChainCanvas
        key={currentChain.chain_id}
        currentChain={currentChain}
        onSetPhase={setCurrentPhase}
      />
    </div>
  )
}
