import { useEffect, useRef, useState } from 'react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, Loader2 } from 'lucide-react'

type ButtonVariant = 'primary' | 'ghost' | 'outline' | 'danger'

export function Button({
  variant = 'primary',
  loading,
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean }) {
  const styles: Record<ButtonVariant, string> = {
    primary: 'bg-primary text-primary-fg hover:opacity-90',
    ghost: 'text-muted hover:bg-surface-2 hover:text-text',
    outline: 'border border-border hover:bg-surface-2',
    danger: 'bg-danger text-white hover:opacity-90',
  }
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-border bg-surface p-4 ${className}`}>{children}</div>
}

export function Badge({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'ok' | 'warn' | 'danger' | 'primary' }) {
  const styles = {
    muted: 'bg-surface-2 text-muted',
    ok: 'bg-ok/10 text-ok',
    warn: 'bg-warn/10 text-warn',
    danger: 'bg-danger/10 text-danger',
    primary: 'bg-primary/10 text-primary',
  }
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[tone]}`}>{children}</span>
}

export function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  disabled,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  format?: (v: number) => string
  disabled?: boolean
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-mono text-text">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        className="range w-full"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  )
}

export function TextInput({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none transition placeholder:text-muted/60 focus:border-primary ${className}`}
      {...rest}
    />
  )
}

/**
 * 点击 / 拖拽两用的文件选择区：点击打开文件对话框，拖入文件即触发 onFile。
 * accept 只约束文件对话框；拖入文件的类型校验由调用方在 onFile 里做。
 */
export function FileDrop({
  accept, onFile, className = '', children,
}: {
  accept?: string
  onFile: (f: File) => void
  className?: string
  children: ReactNode
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={(e) => {
        // 仅在真正离开容器时取消高亮（划过子元素会触发 dragleave，contains 判断避免闪烁）
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragOver(false)
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        const f = e.dataTransfer.files?.[0]
        if (f) onFile(f)
      }}
      className={`cursor-pointer transition ${dragOver ? 'ring-2 ring-primary bg-primary/5' : ''} ${className}`}
    >
      {children}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) onFile(f)
          e.target.value = '' // 允许连续选择同一个文件也能触发 onChange
        }}
      />
    </div>
  )
}

export function EmptyState({ icon, title, desc }: { icon?: ReactNode; title: string; desc?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center">
      {icon && <div className="text-muted">{icon}</div>}
      <div className="font-medium">{title}</div>
      {desc && <div className="max-w-md text-sm text-muted">{desc}</div>}
    </div>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin text-muted" />
}

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text">✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

/**
 * 自绘下拉：弹出层经 portal 挂到 body，用触发按钮的实时 rect 做 fixed 定位，
 * 保证弹层永远贴合控件（原生 <select> 的弹层由浏览器绘制，缩放场景下会错位且无法定制）。
 * 在 Modal（overflow-y-auto）内也不会被裁剪；窗口滚动/缩放时实时跟随。
 */
export function Select({
  value,
  options,
  onChange,
  placeholder = '请选择',
  searchable = false,
  disabled = false,
  size = 'md',
  className = '',
}: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  placeholder?: string
  searchable?: boolean
  disabled?: boolean
  size?: 'sm' | 'md'
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [kw, setKw] = useState('')
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popupRef = useRef<HTMLDivElement>(null)

  const current = options.find((o) => o.value === value)
  const kwNorm = kw.trim().toLowerCase()
  const filtered = kwNorm ? options.filter((o) => o.label.toLowerCase().includes(kwNorm)) : options
  const shown = filtered.slice(0, 500)

  const place = () => {
    const el = triggerRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const estH = Math.min(filtered.length || 1, 10) * 34 + (searchable ? 48 : 10)
    const width = Math.max(r.width, 140)
    const up = window.innerHeight - r.bottom < estH + 12 && r.top > estH + 12
    setPos({
      top: up ? Math.max(8, r.top - estH - 8) : r.bottom + 6,
      left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)),
      width,
    })
  }

  useEffect(() => {
    if (!open) return
    place()
    const onDocPointerDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (triggerRef.current?.contains(t) || popupRef.current?.contains(t)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    document.addEventListener('pointerdown', onDocPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      document.removeEventListener('pointerdown', onDocPointerDown)
      document.removeEventListener('keydown', onKey)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, filtered.length, searchable])

  useEffect(() => {
    if (!open) setKw('')
  }, [open])

  useEffect(() => {
    if (!open) return
    requestAnimationFrame(() => {
      popupRef.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: 'nearest' })
    })
  }, [open])

  const pad = size === 'sm' ? 'px-2 py-1.5 text-sm' : 'px-3 py-2 text-sm'
  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title={current?.label || placeholder}
        className={`inline-flex items-center justify-between gap-1.5 rounded-lg border border-border bg-surface outline-none transition focus:border-primary disabled:cursor-not-allowed disabled:opacity-50 ${pad} ${className}`}
      >
        <span className={`min-w-0 truncate ${current ? '' : 'text-muted/70'}`}>{current?.label ?? placeholder}</span>
        <ChevronDown size={14} className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open &&
        pos &&
        createPortal(
          <div
            ref={popupRef}
            className="fixed z-[60] max-h-64 overflow-y-auto rounded-lg border border-border bg-surface py-1 shadow-xl"
            style={{ top: pos.top, left: pos.left, width: pos.width }}
          >
            {searchable && (
              <div className="sticky top-0 z-10 bg-surface px-2 pb-1.5 pt-1">
                <input
                  autoFocus
                  className="w-full rounded-md border border-border bg-surface-2 px-2 py-1.5 text-xs outline-none focus:border-primary"
                  placeholder="搜索音色…"
                  value={kw}
                  onChange={(e) => setKw(e.target.value)}
                />
              </div>
            )}
            {shown.length === 0 && <div className="px-3 py-2 text-xs text-muted">无匹配项</div>}
            {shown.map((o) => {
              const sel = o.value === value
              return (
                <button
                  key={o.value || '__none__'}
                  type="button"
                  data-selected={sel || undefined}
                  disabled={o.disabled}
                  title={o.label}
                  onClick={() => {
                    if (o.disabled) return
                    onChange(o.value)
                    setOpen(false)
                  }}
                  className={`block w-full truncate px-3 py-1.5 text-left text-sm transition ${
                    o.disabled
                      ? 'cursor-not-allowed text-muted/50'
                      : sel
                        ? 'bg-primary/10 font-medium text-primary'
                        : 'text-text hover:bg-surface-2'
                  }`}
                >
                  {o.label}
                </button>
              )
            })}
          </div>,
          document.body,
        )}
    </>
  )
}
