import { queryOptions } from '@tanstack/react-query'

import { api, isStatus, ResponseError } from '@/lib/api/client'
import type { KioskState, TapResponse } from '@/lib/api/types'
import { kioskKeys } from '@/lib/query-keys'
import type { KioskRequest } from './machine'

export const kioskStateQuery = queryOptions({
  queryKey: kioskKeys.state(),
  queryFn: ({ signal }) => api<KioskState>('/api/kiosk/state', { signal }),
  staleTime: Infinity,
  retry: (count, error) => !isStatus(error, 401, 403) && count < 2,
})

const statuses = new Set([
  'signed_in',
  'signed_out',
  'registration_required',
  'keyholder_action_required',
  'lab_closed',
])
const actions = new Set(['open', 'override', 'continue', 'handoff', 'close'])

function isKioskResult(data: unknown): data is TapResponse {
  if (!data || typeof data !== 'object') return false
  const value = data as Record<string, unknown>
  if (
    typeof value.status !== 'string' || !statuses.has(value.status) ||
    typeof value.message !== 'string' || !Number.isSafeInteger(value.revision) ||
    (value.revision as number) < 0
  ) return false
  if (value.user != null) {
    if (typeof value.user !== 'object') return false
    const user = value.user as Record<string, unknown>
    if (
      typeof user.id !== 'string' || typeof user.display_name !== 'string' ||
      (user.avatar_url != null && typeof user.avatar_url !== 'string')
    ) return false
  }
  if (value.status === 'keyholder_action_required') {
    if (
      !Object.hasOwn(value, 'expected_shift_id') ||
      (value.expected_shift_id !== null && typeof value.expected_shift_id !== 'string') ||
      !Array.isArray(value.actions) || !value.actions.length ||
      !value.actions.every(action => typeof action === 'string' && actions.has(action))
    ) return false
  }
  return true
}

export async function sendKioskRequest(request: KioskRequest): Promise<TapResponse> {
  const { kind, ...body } = request
  const result = await api<unknown>(`/api/kiosk/${kind}`, { method: 'POST', body })
  if (!isKioskResult(result)) throw new ResponseError('Invalid kiosk result')
  return result
}


export interface ForgottenPerson {
  display_name: string
  total_visits: number
  forgotten_signouts: number
  ratio: number
}
export const forgottenLeaderboardQuery = queryOptions({
  queryKey: kioskKeys.leaderboard(),
  queryFn: ({ signal }) => api<{ items: ForgottenPerson[] }>('/api/public/leaderboard', { signal }),
  staleTime: Infinity,
})
