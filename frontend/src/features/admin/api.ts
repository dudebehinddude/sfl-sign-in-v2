import { keepPreviousData, queryOptions } from '@tanstack/react-query'

import { api } from '@/lib/api/client'
import type {
  AdminUser,
  AuditEvent,
  Training,
  ImportApplied,
  ImportPreview,
  KeyholderShift,
  Overview,
  Page,
  Profile,
  Role,
  TrainingType,
  TrainingTypeInput,
  TrainingTypePatch,
  UserCreateInput,
  UserPatchInput,
  Visit,
} from '@/lib/api/types'
import type { staffKeys } from '@/lib/query-keys'

type Keys = ReturnType<typeof staffKeys>

/** Some catalog endpoints may return a bare list instead of a page. */
export function itemsOf<T>(data: T[] | Page<T> | { items: T[] } | undefined): T[] {
  if (!data) return []
  return Array.isArray(data) ? data : data.items
}

const paged = { placeholderData: keepPreviousData }

// Overview and profile
export const overviewQuery = (keys: Keys) =>
  queryOptions({
    queryKey: keys.topic('overview'),
    queryFn: ({ signal }) => api<Overview>('/api/admin/overview', { signal }),
  })

export const profileQuery = (keys: Keys, params: { page: number; page_size: number }) =>
  queryOptions({
    queryKey: keys.topic('profile', params),
    queryFn: ({ signal }) => api<Profile>('/api/me/profile', { query: params, signal }),
    ...paged,
  })

export const patchProfile = (input: {
  first_name?: string
  last_name?: string
  email?: string | null
}) => api<AdminUser>('/api/me/profile', { method: 'PATCH', body: { ...input } })

export const uploadAvatar = (file: File) => {
  const body = new FormData()
  body.append('file', file)
  return api<unknown>('/api/me/avatar', { method: 'POST', body })
}

export const changeOwnPassword = (input: { current_password: string; new_password: string }) =>
  api<unknown>('/api/auth/password', { method: 'POST', body: input })

// People
export const usersQuery = (
  keys: Keys,
  params: { page: number; page_size: number; search: string },
) =>
  queryOptions({
    queryKey: keys.topic('users', 'list', params),
    queryFn: ({ signal }) => api<Page<AdminUser>>('/api/admin/users', { query: params, signal }),
    ...paged,
  })

export const userQuery = (keys: Keys, id: string) =>
  queryOptions({
    queryKey: keys.topic('users', 'detail', id),
    queryFn: ({ signal }) =>
      api<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}`, { signal }),
  })

export const createUser = (input: UserCreateInput) =>
  api<AdminUser>('/api/admin/users', { method: 'POST', body: { ...input } })

export const patchUser = (id: string, input: UserPatchInput) =>
  api<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { ...input },
  })

export const setUserRole = (id: string, role: Role | null) =>
  api<AdminUser>(`/api/admin/users/${encodeURIComponent(id)}/role`, {
    method: 'PUT',
    body: { role },
  })

export { printUserLabel } from '@/features/printing/api'

export const setUserPassword = (id: string, password: string) =>
  api<unknown>(`/api/admin/users/${encodeURIComponent(id)}/password`, {
    method: 'PUT',
    body: { password },
  })

export const matchUserCanvas = (id: string) =>
  api<unknown>(`/api/admin/users/${encodeURIComponent(id)}/canvas-sync`, { method: 'POST' })

export const previewUserImport = (csv_text: string) =>
  api<ImportPreview>('/api/admin/imports/users/preview', { method: 'POST', body: { csv_text } })

export const applyUserImport = (csv_text: string, fingerprint: string) =>
  api<ImportApplied>('/api/admin/imports/users/apply', {
    method: 'POST',
    body: { csv_text, fingerprint, confirm: true },
  })

// Trainings
export const trainingTypesQuery = (keys: Keys) =>
  queryOptions({
    queryKey: keys.topic('training-types'),
    queryFn: async ({ signal }) => {
      const all: TrainingType[] = []
      for (let page = 1; ; page += 1) {
        const data = await api<Page<TrainingType> | TrainingType[]>('/api/admin/training-types', {
          signal,
          query: { page, page_size: 1000 },
        })
        if (Array.isArray(data)) return data
        all.push(...data.items)
        if (!data.items.length || all.length >= data.total) return all
      }
    },
  })

export const TRAINING_ICON_MAX_BYTES = 2 * 1024 * 1024
export async function uploadTrainingIcon(file: File): Promise<{ icon_key: string; icon_url: string }> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    throw new Error('Choose a PNG, JPEG or WebP image.')
  }
  if (!file.size || file.size > TRAINING_ICON_MAX_BYTES) {
    throw new Error('Choose an image up to 2 MiB.')
  }
  const body = new FormData()
  body.append('file', file)
  const result = await api<{ icon_key: string; icon_url: string }>('/api/admin/training-icons', {
    method: 'POST', body,
  })
  if (!/^training-icons\/[a-f0-9]{32}\.png$/.test(result.icon_key) ||
    result.icon_url !== `/media/${result.icon_key}`) {
    throw new Error('The server returned an invalid icon reference. Try uploading again.')
  }
  return result
}

export const createTrainingType = (input: TrainingTypeInput) =>
  api<TrainingType>('/api/admin/training-types', { method: 'POST', body: { ...input } })
export const patchTrainingType = (id: string, input: TrainingTypePatch) =>
  api<TrainingType>(`/api/admin/training-types/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { ...input },
  })

export const trainingsQuery = (
  keys: Keys,
  params: { page: number; page_size: number; user_id?: string; search?: string },
) =>
  queryOptions({
    queryKey: keys.topic('trainings', params),
    queryFn: ({ signal }) => api<Page<Training>>('/api/admin/trainings', { query: params, signal }),
    ...paged,
  })

export const awardTraining = (input: {
  user_id: string
  training_type_id: string
  awarded_at?: string | null
  expires_at?: string | null
}) => api<Training>('/api/admin/trainings', { method: 'POST', body: input })

export const revokeTraining = (id: string, reason: string) =>
  api<Training>(`/api/admin/trainings/${encodeURIComponent(id)}/revoke`, {
    method: 'POST',
    body: { reason },
  })

// Visits
export const visitsQuery = (
  keys: Keys,
  params: { page: number; page_size: number; user_id?: string; active?: boolean },
) =>
  queryOptions({
    queryKey: keys.topic('visits', params),
    queryFn: ({ signal }) => api<Page<Visit>>('/api/admin/visits', { query: params, signal }),
    ...paged,
  })

export const closeVisit = (id: string, forgot_to_sign_out: boolean) =>
  api<Visit>(`/api/admin/visits/${encodeURIComponent(id)}/close`, {
    method: 'POST',
    body: { forgot_to_sign_out },
  })

export const keyholderShiftsQuery = (keys: Keys, params: { page: number; page_size: number }) =>
  queryOptions({
    queryKey: keys.topic('keyholders', params),
    queryFn: ({ signal }) =>
      api<Page<KeyholderShift>>('/api/admin/keyholder-shifts', { query: params, signal }),
    ...paged,
  })

// Audit
export const auditQuery = (keys: Keys, params: { page: number; page_size: number }) =>
  queryOptions({
    queryKey: keys.topic('audit', params),
    queryFn: ({ signal }) =>
      api<Page<AuditEvent>>('/api/admin/audit-events', { query: params, signal }),
    ...paged,
  })
