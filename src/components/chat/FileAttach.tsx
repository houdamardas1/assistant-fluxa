import { useRef, type ChangeEvent } from 'react'
import type { FileInfo } from '../../lib/types'

export const ACCEPT = '.pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp'

function Clip({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

function Cross() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" aria-hidden="true">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  )
}

function taille(t: number): string {
  return t < 1024 * 1024
    ? `${Math.max(1, Math.round(t / 1024))} Ko`
    : `${(t / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`
}

export function FileAttachButton({ onPick, disabled }: { onPick: (f: File) => void; disabled: boolean }) {
  const ref = useRef<HTMLInputElement>(null)
  const change = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (f) onPick(f)
  }
  return (
    <>
      <input ref={ref} type="file" accept={ACCEPT} className="hidden" onChange={change} />
      <button
        type="button" disabled={disabled} onClick={() => ref.current?.click()}
        aria-label="Joindre un fichier" title="Joindre un fichier (PDF, Word, TXT, CSV, image)"
        className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-line/60 hover:text-ink disabled:opacity-40"
      >
        <Clip />
      </button>
    </>
  )
}

export function FileChip({ attachment, uploading, error, onRemove }: {
  attachment: FileInfo | null
  uploading: boolean
  error: string | null
  onRemove: () => void
}) {
  if (uploading) {
    return (
      <div className="mb-2 flex items-center gap-2 rounded-xl border border-line bg-surface/70 px-3 py-2 text-sm text-muted" role="status">
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-brand border-t-transparent" />
        Lecture et analyse du fichier…
      </div>
    )
  }
  if (error) {
    return (
      <div className="mb-2 rounded-xl border border-danger/30 bg-danger/5 px-3 py-2 text-sm text-danger" role="alert">
        {error}
      </div>
    )
  }
  if (!attachment) return null
  const estImage = ['png', 'jpg', 'jpeg', 'webp'].includes(attachment.type)
  const detail = estImage ? 'image' : `${attachment.pages} ${attachment.type === 'pdf' ? 'page(s)' : 'section(s)'}`
  return (
    <div className="mb-2 rounded-xl border border-brand/30 bg-brand/5 px-3 py-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-brand"><Clip size={16} /></span>
        <span className="min-w-0 flex-1 truncate font-medium">{attachment.nom}</span>
        <span className="shrink-0 text-xs text-muted">{taille(attachment.taille)} · {detail}</span>
        <button
          type="button" onClick={onRemove} aria-label="Retirer le fichier"
          className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-muted hover:bg-line/60 hover:text-ink"
        >
          <Cross />
        </button>
      </div>
      <p className="mt-1 text-xs text-muted">
        Vos questions portent sur ce fichier. Il reste en mémoire 30 minutes au maximum et n'est jamais enregistré.
      </p>
      {attachment.avertissements.map((a) => (
        <p key={a} className="mt-1 text-xs text-warn">{a}</p>
      ))}
    </div>
  )
}
