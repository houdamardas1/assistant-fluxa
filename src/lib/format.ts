import type { CorpusStats, Mode, Role } from './types'

export type Tone = 'ok' | 'info' | 'warn' | 'danger' | 'neutral' | 'plum'

export const ROLE_LABELS: Record<string, string> = {
  tous: 'Accès général', finance: 'Finance', direction: 'Direction', it: 'IT',
  rh: 'Ressources humaines', commerce: 'Commerce', juridique: 'Juridique', marketing: 'Marketing',
}

export const DEPT_LABELS: Record<string, string> = ROLE_LABELS

export const TYPE_LABELS: Record<string, string> = {
  entreprise: "Documents d'entreprise",
  public_reglementaire: 'Textes réglementaires',
}

export function roleLabel(role: string | null | undefined): string {
  return role ? ROLE_LABELS[role] ?? role : '—'
}

export function cleanName(name: string): string {
  return name.replace(/_/g, ' ').trim()
}

/** "Code_du_Travail_Loi_65-99.pdf" -> "Code du Travail Loi 65-99" */
export function fileLabel(file: string): string {
  return cleanName(file.replace(/\.pdf$/i, ''))
}

export function modeMeta(mode: Mode | string | null | undefined): { label: string; tone: Tone } {
  switch (mode) {
    case 'RAG': return { label: 'Réponse sourcée', tone: 'ok' }
    case 'MULTI_INTENT': return { label: 'Comparaison', tone: 'ok' }
    case 'GENERAL': return { label: 'Réponse générale', tone: 'neutral' }
    case 'ABSENT': return { label: 'Information absente', tone: 'warn' }
    case 'HORS_PERIMETRE': return { label: 'Accès non autorisé', tone: 'danger' }
    case 'BLOQUE': return { label: 'Demande bloqu\u00e9e', tone: 'danger' }
    case 'CLARIFICATION': return { label: 'Précision nécessaire', tone: 'info' }
    case 'FICHIER': return { label: 'Réponse du fichier', tone: 'info' }
    default: return { label: mode ? String(mode) : '—', tone: 'neutral' }
  }
}

export function eventMeta(type: string): { label: string; tone: Tone } {
  switch (type) {
    case 'ACCESS_GRANTED': return { label: 'Réponse', tone: 'ok' }
    case 'FILE_UPLOADED': return { label: 'Fichier téléversé', tone: 'info' }
    case 'FILE_ANALYZED': return { label: 'Fichier analysé', tone: 'ok' }
    case 'FILE_REJECTED': return { label: 'Fichier refusé', tone: 'warn' }
    case 'REPORT_EXPORTED': return { label: 'Rapport exporté', tone: 'info' }
    case 'ACCESS_DENIED': return { label: 'Accès refusé', tone: 'danger' }
    case 'NO_ANSWER': return { label: 'Sans réponse', tone: 'warn' }
    case 'CLARIFICATION_REQUESTED': return { label: 'Précision', tone: 'info' }
    case 'LOGIN': return { label: 'Connexion', tone: 'neutral' }
    case 'AUTH_FAILED': return { label: 'Échec authentification', tone: 'danger' }
    case 'RATE_LIMITED': return { label: 'Limite de débit', tone: 'warn' }
    case 'QUOTA_ERROR': return { label: 'Quota du modèle', tone: 'warn' }
    case 'ERROR': return { label: 'Erreur', tone: 'danger' }
    case 'PROMPT_BLOCKED': return { label: 'Bloqu\u00e9', tone: 'danger' }
    case 'DOCUMENT_BLOCKED': return { label: 'Document \u00e9cart\u00e9', tone: 'warn' }
    case 'ADMIN_DENIED': return { label: 'Admin refusé', tone: 'danger' }
    default: return { label: type, tone: 'neutral' }
  }
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

export function formatDay(day: string): string {
  const [, m, d] = day.split('-')
  return d && m ? `${d}/${m}` : day
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

export function formatRelative(iso: string, now: number = Date.now()): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 60) return "à l'instant"
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`
  return `il y a ${Math.floor(s / 86400)} j`
}

export function firstName(displayName: string): string {
  return displayName.trim().split(/\s+/)[0] || displayName
}

/** Suggestions construites a partir des documents REELLEMENT accessibles. */
export function suggestionsFrom(stats: CorpusStats): string[] {
  const out: string[] = []
  const companies = stats.by_company.slice(0, 2).map((c) => cleanName(c.name))

  companies.forEach((c, i) => {
    out.push(`Quel est le chiffre d'affaires de ${c} ?`)
    out.push(i === 0 ? `Qui compose le conseil d'administration de ${c} ?` : `Quel est le résultat net de ${c} ?`)
  })

  stats.files
    .filter((f) => f.type === 'public_reglementaire')
    .slice(0, 2)
    .forEach((f) => out.push(`Quelles sont les principales dispositions de ${fileLabel(f.file)} ?`))

  return out.slice(0, 6)
}

export function isDirection(role: Role | undefined): boolean {
  return role === 'direction'
}
