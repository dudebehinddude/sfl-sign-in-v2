export interface CanvasIdentityIssue {
  id: string
  display_name: string
  email: string | null
  canvas_id: string
  user_id: string | null
  conflict: string | null
}
export interface CanvasTrainingStatus {
  training_type_id: string
  name: string
  canvas_assignment_id: string | null
  started_at: string | null
  last_success_at: string | null
  last_error: string | null
  status: 'idle' | 'running' | 'error' | 'unconfigured'
}
export interface CanvasSyncOverview {
  status: 'idle' | 'running' | 'error' | 'unconfigured'
  started_at: string | null
  last_success_at: string | null
  last_error: string | null
}
export interface CanvasStatus {
  overview: CanvasSyncOverview
  configured: boolean
  setup_message: string | null
  trainings: CanvasTrainingStatus[]
  unmatched: CanvasIdentityIssue[]
  conflicts: CanvasIdentityIssue[]
}
export interface CanvasQuiz {
  id: string
  title: string
  points_possible: number | null
}
export interface CanvasQuizzes {
  items: CanvasQuiz[]
  refreshed_at: string | null
}
export interface SyncRequest {
  status: 'queued'
  message: string
}

export type CanvasBinding = 'unmatched' | 'conflicts' | 'all'
export interface CanvasPeopleFilters {
  binding: CanvasBinding
  search: string
  page: number
  page_size: number
}
export interface CanvasPeople {
  items: CanvasIdentityIssue[]
  total: number
  page: number
  page_size: number
}
