import { useState, useEffect } from 'react'
import { CaretDownIcon, ListIcon } from '@phosphor-icons/react'
import { ChainPopup } from './ChainPopup'
import { chainApi } from '../entities/chainApi'
import { api } from '../shared/api/axios'
import { toast } from 'react-toastify'
import { useMinify } from '../context/useMinify.js'
import { runControl } from '../shared/runControl'

const QuietButton = ({ children, className = '', ...props }) => (
  <button
    type="button"
    {...props}
    className={`rounded-md px-2.5 py-1.5 text-xs text-secondary transition-colors hover:bg-card-hover hover:text-primary disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
  >
    {children}
  </button>
)

export const NavBar = ({
  onSelect,
  onCreateChain,
  onDeleteChain,
  chains = [],
  currentChain,
  layout = 'columns',
  onToggleLayout,
}) => {
  const [chainsOpen, setChainsOpen] = useState(false)
  const [username, setUsername] = useState(null)
  const { minified, toggle } = useMinify()

  useEffect(() => {
    const loadUser = async () => {
      try {
        const data = await chainApi.getCurrentUser()
        setUsername(data.username ?? data.email)
      } catch {
        // the session chip is optional; a failed lookup must not interrupt work
      }
    }

    loadUser()
  }, [])

  const handleStopChain = async () => {
    if (!currentChain) return

    runControl.stop()
    try {
      await chainApi.cancelChain(currentChain.chain_id, currentChain.chain_name)
      toast.warning('Chain stop requested. In-flight steps may report for a few minutes')
    } catch {
      toast.error('Could not stop the chain')
    }
  }

  const handleRunChain = async () => {
    if (!currentChain) return

    const toastId = toast.loading('Running chain')

    try {
      const { steps, errors } = await chainApi.runChain(currentChain.chain_id)
      if (errors.length) {
        toast.update(toastId, {
          render: `Chain stopped on ${errors.length} step(s): ${errors[0]}`,
          type: 'error',
          isLoading: false,
          autoClose: 6000,
        })
      } else if (!steps.length) {
        toast.update(toastId, {
          render: 'Nothing to run: no pending or successful steps with a command',
          type: 'warning',
          isLoading: false,
          autoClose: 5000,
        })
      } else {
        toast.update(toastId, {
          render: `Chain finished: ${steps.length} step(s) executed`,
          type: 'success',
          isLoading: false,
          autoClose: 4000,
        })
      }
    } catch (err) {
      toast.update(toastId, {
        render: err.message || 'Could not run the chain',
        type: 'error',
        isLoading: false,
        autoClose: 6000,
      })
    }
  }

  const handleLogout = async () => {
    // cookie session: revoke refresh server side, cookies die with the response
    try {
      await api.post('/auth/logout')
    } catch {
      // logout best-effort, cookie clearing happens server side
    }

    window.location.href = '/login'
  }

  return (
    <nav className="sticky top-0 z-[100] flex items-center gap-3 border-b border-subtle bg-nav px-4 py-2">
      <span className="text-[15px] font-medium tracking-[0.02em] text-primary">EAGLE</span>
      <span className="h-4 w-px bg-subtle" aria-hidden="true" />

      <div className="relative">
        <button
          type="button"
          onClick={() => setChainsOpen((v) => !v)}
          aria-label="Chain list"
          aria-expanded={chainsOpen}
          className="flex items-center gap-2 rounded-md border border-subtle bg-card px-2.5 py-1.5 text-xs transition-colors hover:border-default hover:bg-card-hover"
        >
          <ListIcon size={14} className="text-muted" />
          <span className="max-w-[220px] truncate text-primary">
            {currentChain?.chain_name ?? 'Select chain'}
          </span>
          <CaretDownIcon size={14} className="text-muted" />
        </button>

        {chainsOpen && (
          <ChainPopup
            chains={chains}
            onClose={() => setChainsOpen(false)}
            onSelect={onSelect}
            onCreate={onCreateChain}
            onDelete={onDeleteChain}
          />
        )}
      </div>

      <div className="ml-auto flex items-center gap-1">
        <QuietButton onClick={handleRunChain} disabled={!currentChain}>
          Run chain
        </QuietButton>
        <QuietButton onClick={handleStopChain} disabled={!currentChain}>
          Stop
        </QuietButton>

        <span className="mx-2 h-4 w-px bg-subtle" aria-hidden="true" />

        <QuietButton onClick={toggle} title="Hide step output">
          {minified ? 'Show output' : 'Hide output'}
        </QuietButton>
        <QuietButton onClick={onToggleLayout} title="Switch phase layout">
          {layout === 'columns' ? 'Stack phases' : 'Side by side'}
        </QuietButton>

        {username && (
          <span className="ml-2 font-mono text-[11px] text-muted" title={username}>
            {username}
          </span>
        )}
        <QuietButton onClick={handleLogout}>Log out</QuietButton>
      </div>
    </nav>
  )
}
