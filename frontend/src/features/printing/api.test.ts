import { afterEach, expect, it, vi } from 'vitest'
import { printingStatusQuery, printUserLabel } from './api'
afterEach(() => vi.unstubAllGlobals())
it('requests live printer status with principal-scoped cache', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ connected: false, busy: false, last_result: null })),
    )
  vi.stubGlobal('fetch', fetch)
  const options = printingStatusQuery('staff-1')
  const result = await options.queryFn!({ signal: new AbortController().signal } as never)
  expect(result.connected).toBe(false)
  expect(fetch.mock.calls[0][0]).toBe('/api/admin/printing/status')
  expect(options.queryKey).toEqual(['staff', 'staff-1', 'printing', 'status'])
})
it('reports offline drops without treating them as queued success', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'offline', message: 'Printer is offline; label dropped.' }),
      ),
    )
  vi.stubGlobal('fetch', fetch)
  const result = await printUserLabel('user-1')
  expect(fetch.mock.calls[0][0]).toBe('/api/admin/users/user-1/print')
  expect(result.status).toBe('offline')
})
