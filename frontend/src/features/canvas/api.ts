import { queryOptions } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import { staffKeys } from '@/lib/query-keys'
import type { CanvasPeople, CanvasPeopleFilters, CanvasQuizzes, CanvasStatus, SyncRequest } from './types'

export const canvasStatusQuery = (principalId: string) =>
  queryOptions({
    queryKey: staffKeys(principalId).topic('canvas', 'status'),
    queryFn: ({ signal }) => api<CanvasStatus>('/api/admin/canvas/status', { signal }),
    staleTime: Infinity,
    retry: false,
  })
export const canvasQuizzesQuery = (principalId: string) =>
  queryOptions({
    queryKey: staffKeys(principalId).topic('canvas', 'quizzes'),
    queryFn: ({ signal }) => api<CanvasQuizzes>('/api/admin/canvas/quizzes', { signal }),
    staleTime: Infinity,
    retry: false,
  })
export function requestCanvasSync(training_type_id?: string) {
  return api<SyncRequest>('/api/admin/canvas/sync', {
    method: 'POST',
    body: training_type_id ? { training_type_id } : {},
  })
}
export function refreshCanvasQuizzes() {
  return api<SyncRequest>('/api/admin/canvas/quizzes/refresh', { method: 'POST' })
}

export const canvasPeopleQuery = (principalId: string, filters: CanvasPeopleFilters) =>
  queryOptions({
    queryKey: staffKeys(principalId).topic('canvas', 'people', filters),
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        binding: filters.binding,
        search: filters.search,
        page: String(filters.page),
        page_size: String(filters.page_size),
      })
      return api<CanvasPeople>(`/api/admin/canvas/people?${params}`, { signal })
    },
    staleTime: Infinity,
    retry: false,
  })
