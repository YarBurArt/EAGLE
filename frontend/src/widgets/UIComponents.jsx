const iconBtnBase =
  'flex h-6 w-6 items-center justify-center rounded border border-default bg-transparent text-[12px] text-secondary transition-colors'

const hoverColors = {
  accent: 'hover:border-accent hover:text-accent',
  success: 'hover:border-success hover:text-success',
  danger: 'hover:border-danger hover:text-danger',
}

export const IconButton = ({ hover = 'accent', className = '', ...props }) => (
  <button {...props} className={`${iconBtnBase} ${hoverColors[hover]} ${className}`} />
)

const dashedBtnBase =
  'flex h-6 w-6 items-center justify-center rounded border border-dashed border-default bg-transparent text-[12px] text-secondary transition-all hover:border-solid hover:border-accent hover:text-accent'

export const DashedIconButton = ({ className = '', ...props }) => (
  <button {...props} className={`${dashedBtnBase} ${className}`} />
)

export const DropdownItem = ({ onClick, children, className = '' }) => (
  <button
    onClick={onClick}
    className={`flex w-full items-center justify-between gap-2 border-b border-subtle px-3 py-2 text-left transition-colors hover:bg-card-hover ${className}`}
  >
    {children}
  </button>
)

const inputBase =
  'rounded border border-default bg-input px-2 py-1 text-xs text-primary outline-none transition-colors focus:border-accent'

export const Input = ({ as, className = '', ...props }) => {
  if (as === 'select') {
    return <select {...props} className={`${inputBase} ${className}`} />
  }
  return <input {...props} className={`${inputBase} ${className}`} />
}

export const TextInput = ({ className = '', ...props }) => (
  <input
    {...props}
    className={`mb-2 w-full rounded border border-default bg-input px-2 py-1 text-xs text-primary outline-none transition-colors focus:border-accent ${className}`}
  />
)

export const TransparentInput = ({ className = '', ...props }) => (
  <input
    {...props}
    className={`mb-2 w-full rounded border border-transparent bg-transparent px-1.5 py-1 text-xs font-semibold text-primary outline-none transition-colors hover:border-default focus:border-accent focus:bg-input ${className}`}
  />
)

const textareaBase =
  'max-h-[300px] min-h-[40px] w-full resize-none rounded border border-default bg-input p-2 font-mono text-[11px] leading-relaxed text-primary outline-none transition-colors focus:border-accent'

export const Textarea = ({ className = '', ...props }) => (
  <textarea {...props} className={`${textareaBase} ${className}`} />
)

export const ReadonlyTextarea = ({ className = '', ...props }) => (
  <textarea {...props} className={`${textareaBase} ${className}`} />
)

const actionBtnBase =
  'rounded px-2 py-1 text-[11px] text-secondary transition-colors hover:bg-card-hover'

export const ActionButton = ({ hover = 'primary', className = '', ...props }) => {
  const hoverClass = {
    primary: 'hover:text-primary',
    danger: 'hover:text-danger',
    accent: 'hover:text-accent',
  }[hover]
  return <button {...props} className={`${actionBtnBase} ${hoverClass} ${className}`} />
}

export const RunButton = ({ className = '', ...props }) => (
  <button
    {...props}
    className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] text-success transition-colors hover:bg-success/10 disabled:text-warning whitespace-nowrap ${className}`}
  />
)
