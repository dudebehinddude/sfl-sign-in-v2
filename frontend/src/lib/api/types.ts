// Wire types. Endpoints with a response model in backend/openapi.json come
// from the generated schema.gen.ts; the rest mirror backend/app/routes/*.py
// and are listed in frontend/docs/integration-notes.md.
import type * as S from './schema.gen'

// FastAPI serializes fields that have defaults, so these are always present
// in responses even though the schema marks them optional.
type Present<T, K extends keyof T> = Omit<T, K> & { [P in K]-?: Exclude<T[P], undefined> }

export type Role = 'superadmin' | 'admin' | 'operator'
export type AccessLevel = S.SpaceLevel

export type Permission =
  | 'users.read'
  | 'users.write'
  | 'trainings.read'
  | 'trainings.write'
  | 'visits.read'
  | 'visits.write'
  | 'metrics.read'
  | 'canvas.read'
  | 'canvas.write'
  | 'printing.read'
  | 'printing.write'
  | 'audit.read'
  | 'roles.write'
  | 'database.read'
  | 'database.write'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// Public projection. Never extend with identifiers, emails or admin fields.
export type PublicPerson = S.PublicPerson
export interface Badge {
  training_type_id: string
  name: string
  icon_key: string
}
export type Occupant = Omit<Present<S.Occupant, 'badges'>, 'badges'> & { badges: Badge[] }
export interface Occupancy extends Omit<S.Occupancy, 'occupants'> {
  occupants: Occupant[]
}

/** GET /api/public/training-types (untyped in OpenAPI). */
export interface PublicTrainingType {
  id: string
  name: string
  icon_key: string
  display_order: number
}

// Auth
export interface SessionUser extends Omit<S.SessionUser, 'permissions' | 'roles'> {
  permissions: Permission[]
  role: Role | null
}
export interface SessionResponse extends Omit<S.AuthResponse, 'user'> {
  user: SessionUser
}

// Kiosk
export type TapStatus = S.KioskResult['status']
export type KeyholderAction = S.KeyholderInput['action']
export interface TapResponse extends Omit<S.KioskResult, 'actions'> {
  actions?: KeyholderAction[] | null
}
export type KioskActivity = S.RecentActivity
export interface KioskState extends Omit<S.KioskState, 'occupants'> {
  occupants: Occupant[]
}

// People
export type Identifier = S.Identifier
export interface AdminUser extends Omit<S.UserDetail, 'roles' | 'badges'> {
  role: Role | null
  badges: Badge[]
}
export type UserCreateInput = S.UserCreate
export type UserPatchInput = S.UserPatch

export interface TrainingType {
  id: string
  display_order: number
  name: string
  icon_key: string
  active: boolean
  canvas_assignment_id: string | null
  canvas_minimum_score: number | null
  canvas_sync_started_at: string | null
  canvas_synced_at: string | null
  canvas_sync_error: string | null
  created_at: string
  updated_at: string
}
export type TrainingTypeInput = Pick<
  TrainingType,
  'name' | 'icon_key' | 'display_order' | 'active' | 'canvas_assignment_id' | 'canvas_minimum_score'
>
export type TrainingTypePatch = Partial<TrainingTypeInput>
export interface Training {
  id: string
  user_id: string | null
  user_name: string
  user_href: string | null
  training_type_id: string
  training_type_name: string
  source: string
  awarded_at: string | null
  expires_at: string | null
  revoked_at: string | null
  has_training: boolean
  score: number | null
  grade: string | null
  passed: boolean | null
  completed_at: string | null
  fetched_at: string | null
  submission_id: string | null
  attempt: number | null
  created_at: string
  updated_at: string
}

// Visits
export type Visit = S.VisitDetail

export interface KeyholderShift {
  id: string
  user_id: string
  display_name: string
  started_at: string
  ended_at: string | null
}

export interface Overview {
  counts: { users: number; present: number; training_types: number }
  revision: number
}

// Metrics
export type Metrics = S.MetricsResponse
export type MetricsSummary = S.MetricsSummary
export type MetricsDay = S.DailyMetrics

export interface AuditEvent {
  id: string
  occurred_at: string
  action: string
  action_label: string
  actor_name: string
  actor_href: string | null
  target_name: string
  target_href: string | null
  details: Record<string, unknown>
}

// Self-service profile
export interface Profile extends Omit<S.ProfileResponse, 'user'> {
  user: AdminUser
}

// Database workbench
export type DatabaseColumn = S.ColumnMetadata
export type DatabaseTable = S.TableMetadata
export type DatabaseRows = S.RowsResponse
export type QueryResult = S.QueryResponse

// Bulk import
export type ImportPreview = S.PreviewResponse
export type ImportRow = S.PreviewRow
export type ImportRowStatus = S.PreviewRow['status']
export type ImportApplied = S.ApplyResponse
