import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, isStatus, setCsrfToken } from '@/lib/api/client'
import type { Permission, SessionResponse, SessionUser } from '@/lib/api/types'
import { authKeys } from '@/lib/query-keys'

export const meQuery = queryOptions({
  queryKey: authKeys.me(),
  queryFn: async ({ signal }): Promise<SessionResponse | null> => {
    try {
      const session = await api<SessionResponse>('/api/auth/me', { signal })
      setCsrfToken(session.csrf_token)
      return session
    } catch (error) {
      if (isStatus(error, 401)) {
        setCsrfToken(null)
        return null
      }
      throw error
    }
  },
  staleTime: 60_000,
  retry: (count, error) => !isStatus(error, 401, 403) && count < 2,
})

export function hasPermission(
  user: SessionUser | null | undefined,
  permission: Permission,
): boolean {
  return Boolean(user?.permissions.includes(permission))
}

export function useSession() {
  const query = useQuery(meQuery)
  const user = query.data?.user ?? null
  return {
    query,
    user,
    can: (permission: Permission) => hasPermission(user, permission),
    isSuperadmin: user?.role === 'superadmin',
    /** Only admins may change physical access, activation and training type definitions. */
    isAdmin: user?.role === 'admin' || user?.role === 'superadmin',
  }
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: { identifier: string; password: string }) =>
      api<SessionResponse>('/api/auth/login', { method: 'POST', body: input }),
    onSuccess: (session) => {
      // Drop anything cached for a previous principal before the new one renders.
      client.clear()
      setCsrfToken(session.csrf_token)
      client.setQueryData(authKeys.me(), session)
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api<void>('/api/auth/logout', { method: 'POST' }),
    onSettled: () => {
      setCsrfToken(null)
      client.clear()
      client.setQueryData(authKeys.me(), null)
    },
  })
}
