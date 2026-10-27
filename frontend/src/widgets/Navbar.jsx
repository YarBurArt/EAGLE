import { useState, useEffect } from 'react'
import { ListIcon } from '@phosphor-icons/react'
import { ChainPopup } from './ChainPopup'
import { chainApi } from '../entities/chainApi'
import { api } from '../shared/api/axios'
import { toast } from 'react-toastify'
import { useMinify } from '../context/useMinify.js'

const NavButton = ({ children, ...props }) => (
  <button
    {...props}
    className="rounded px-2.5 py-1 text-xs text-secondary transition-colors hover:bg-card hover:text-primary"
  >
    {children}
  </button>
)

export const NavBar = ({ onSelect, onCreateChain, onDeleteChain, chains = [], currentChain }) => {
  const [chainsOpen, setChainsOpen] = useState(false)
  const [username, setUsername] = useState(null)
  const { toggle } = useMinify()

  useEffect(() => {
    const loadUser = async () => {
      try {
        const data = await chainApi.getCurrentUser()
        setUsername(data.username ?? data.email)
      } catch {
        toast.error('Who are you ? ...')
      }
    }
    loadUser()
  }, [])

  const handleStopChain = async () => {
    if (!currentChain) return
    try {
      await chainApi.cancelChain(currentChain.chain_id, currentChain.chain_name)
      toast.warning(
        'Chain stopped, but some consequences of steps can still appear in next 5 minutes !',
      )
    } catch {
      toast.error('Failed to stop chain, if critical just kill backend :)')
    }
  }

  const handleRunChain = async () => {
    if (!currentChain) return
    try {
      await chainApi.runChain(currentChain.chain_id)
      toast.success('Chain is maybe running...')
    } catch {
      toast.error('Chain run failed, backend maybe unreachable')
    }
  }

  const handleMinify = () => {
    toggle()
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
    <div className="relative">
      <nav className="sticky top-0 z-[100] flex items-center justify-between border-b border-subtle bg-nav px-5 py-2.5">
        <div className="flex items-center justify-center gap-1.5">
          <h2 className="mr-2 translate-y-1 text-[15px] font-bold tracking-wider text-primary">
            EAGLE
          </h2>

          <button
            onClick={() => setChainsOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded border border-default bg-transparent px-3 py-1 text-xs text-secondary transition-colors hover:border-strong hover:bg-card hover:text-primary"
          >
            <ListIcon />
            <span>Chain List</span>
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <NavButton onClick={handleStopChain} disabled={!currentChain}>
            Stop chain
          </NavButton>
          <NavButton onClick={handleRunChain} disabled={!currentChain}>
            Run chain
          </NavButton>
          <NavButton onClick={handleMinify}>Minify</NavButton>
          {username && <span className="text-xs text-secondary">{username}</span>}
          <NavButton onClick={handleLogout}>Logout</NavButton>
        </div>
      </nav>

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
  )
}
