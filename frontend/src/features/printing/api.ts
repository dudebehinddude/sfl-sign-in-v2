import { queryOptions } from '@tanstack/react-query'
import { api } from '@/lib/api/client'
import type { AdminUser, Page } from '@/lib/api/types'
import { staffKeys } from '@/lib/query-keys'
import type { PrintResult, PrintingStatus } from './types'

export const printingStatusQuery = (principalId: string) =>
  queryOptions({
    queryKey: staffKeys(principalId).topic('printing', 'status'),
    queryFn: ({ signal }) => api<PrintingStatus>('/api/admin/printing/status', { signal }),
    staleTime: Infinity,
    retry: false,
  })
export const printPeopleQuery = (principalId: string, search: string) =>
  queryOptions({
    queryKey: staffKeys(principalId).topic('users', 'print-search', search),
    queryFn: ({ signal }) =>
      api<Page<AdminUser>>('/api/admin/users', {
        signal,
        query: { search, page: 1, page_size: 8 },
      }),
    staleTime: Infinity,
    retry: false,
  })
export function printUserLabel(userId: string) {
  return api<PrintResult>(`/api/admin/users/${encodeURIComponent(userId)}/print`, {
    method: 'POST',
  })
}
