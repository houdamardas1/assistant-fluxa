// Types alignes sur les reponses JSON du backend FastAPI (voir app/api/*.py).

export type Role =
  | 'tous' | 'finance' | 'direction' | 'it' | 'rh' | 'commerce' | 'juridique' | 'marketing'

export interface User {
  username: string
  display_name: string
  role: Role
  tenant_id: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export type Mode =
  | 'RAG' | 'MULTI_INTENT' | 'GENERAL' | 'ABSENT' | 'HORS_PERIMETRE' | 'CLARIFICATION'

export interface Source {
  verifie?: boolean
  n: number
  fichier: string | null
  page: number | null
  entreprise: string | null
  type: string | null
  demo: boolean
}

export interface AskResponse {
  request_id: string
  answer: string
  mode: Mode
  departement: string | null
  confidence: number
  sources: Source[]
}

export interface HistoryItem {
  request_id: string
  ts: string
  event_type: string
  question: string | null
  mode: Mode | null
  departement: string | null
  answer: string | null
  sources: Source[]
  confidence: number | null
  latency_ms: number | null
}

export interface CorpusFile {
  file: string
  entreprise: string | null
  type: string
  departements: string[]
  chunks: number
  max_page: number
  demo: boolean
}

export interface CorpusStats {
  role: Role
  total_chunks: number
  total_files: number
  total_pages: number
  by_company: { name: string; chunks: number; files: number }[]
  by_department: { name: string; chunks: number; files: number }[]
  by_type: { type: string; chunks: number; files: number }[]
  files: CorpusFile[]
}

export interface LatencyStats {
  n: number
  avg_ms: number | null
  p50_ms: number | null
  p95_ms: number | null
}

export interface AuditSummary {
  tenant_id: string
  counts: Record<string, number>
  latency: LatencyStats
  by_role: Record<string, number>
}

export interface DayPoint {
  day: string
  requests: number
  granted: number
  denied: number
  no_answer: number
  errors: number
}

export interface AuditTimeseries {
  tenant_id: string
  days: DayPoint[]
}

export interface AuditEvent {
  id: number
  ts: string
  request_id: string
  tenant_id: string | null
  user_id: string | null
  role: string | null
  event_type: string
  question: string | null
  mode: string | null
  departement: string | null
  sources: string | null
  confidence: number | null
  latency_ms: number | null
  answer_excerpt: string | null
  detail: string | null
  client_ip: string | null
}

export interface Health {
  status: string
  index_loaded: boolean
}

export type KpiPerimetre = 'social' | 'consolide' | 'non_precise'

export interface KpiItem {
  id: string
  entreprise: string
  indicateur: string
  libelle: string
  annee: number
  valeur: number
  unite: string
  perimetre: KpiPerimetre
  document: string
  page: number
  detail: string | null
  avertissement: string | null
  verifie: boolean
  annee_precedente: number | null
  valeur_precedente: number | null
  variation_pct: number | null
}
