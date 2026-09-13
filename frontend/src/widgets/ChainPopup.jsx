import { useEffect, useRef, useState } from 'react'
import { PlusCircleIcon, XIcon } from '@phosphor-icons/react'

export const ChainPopup = ({ chains = [], onClose, onSelect, onCreate, onDelete }) => {
  const popupRef = useRef(null)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const onClick = (e) => {
      // check is click inside Popup element by reference, if not then close 
      if (popupRef.current && !popupRef.current.contains(e.target)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [onClose])

  // create chain object just by chain name, then select to edit phases/steps 
  const handleCreate = async (e) => {
    e.preventDefault()
    setError('')
    if (!newName.trim()) return
    setLoading(true)
    try {
      const created = await onCreate(newName.trim())
      setNewName('')
      onSelect(created.chain_id)
      onClose()
    } catch {
      setError('Failed to create chain, try different chain name')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (chainId, chainName) => {
    if (!window.confirm(`Delete chain "${chainName}"?`)) return
    try {
      await onDelete(chainId)
    } catch {
      setError(`Failed to delete chain: ${chainName}`)
    }
  }

  const handleSelect = (chainId) => {
    onSelect(chainId)
    onClose()
  }

  return (
    <div
      ref={popupRef}
      className="absolute left-2 top-full z-[110] mt-2 w-80 rounded-md border border-default bg-card shadow-xl"
    >
      <div className="px-4 py-3 border-b border-subtle">
        <h3 className="text-sm font-semibold text-primary">Chains</h3>
      </div>

      <div className="px-4 py-3 border-b border-subtle">
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Chain name"
            className="flex-1 rounded border border-default bg-input px-2 py-1 text-xs text-primary outline-none transition-colors focus:border-accent"
          />
          <button
            type="submit"
            disabled={loading || !newName.trim()}
            className="rounded bg-accent px-3 py-1 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <PlusCircleIcon className="inline h-3 w-3" /> Create
          </button>
        </form>
      </div>

      {error && <div className="px-4 py-2 text-xs text-danger">{error}</div>}

      <div className="max-h-60 overflow-y-auto">
        {chains.length === 0 ? (
          <div className="px-4 py-3 text-xs text-muted">No chains yet</div>
        ) : (
          chains.map((c) => (
            <div
              key={c.chain_id}
              className="flex items-center justify-between gap-2 border-b border-subtle px-4 py-2"
            >
              <div className="min-w-0 flex-1">
                <div
                  className="truncate text-xs font-medium text-primary cursor-pointer hover:text-accent"
                  onClick={() => handleSelect(c.chain_id)}
                >
                  {c.chain_name}
                </div>
                <div className="text-[10px] text-muted">{c.current_phase_name}</div>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  onClick={() => handleSelect(c.chain_id)}
                  title="Select chain"
                  className="rounded px-1.5 py-0.5 text-[10px] text-secondary transition-colors hover:bg-card-hover hover:text-primary"
                >
                  Select
                </button>
                <button
                  onClick={() => handleDelete(c.chain_id, c.chain_name)}
                  title="Delete chain"
                  className="rounded px-1.5 py-0.5 text-[10px] text-secondary transition-colors hover:bg-card-hover hover:text-danger"
                >
                  <XIcon className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
