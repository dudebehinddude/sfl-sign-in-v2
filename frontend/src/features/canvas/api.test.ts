import { afterEach, expect, it, vi } from 'vitest'
import { setCsrfToken } from '@/lib/api/client'
import {
  canvasPeopleQuery,
  canvasQuizzesQuery,
  canvasStatusQuery,
  refreshCanvasQuizzes,
  requestCanvasSync,
} from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  setCsrfToken(null)
})
it('returns cached quiz assignment IDs and scopes choices to the staff principal', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [{ id: '202', title: 'Laser training', points_possible: 10 }],
          refreshed_at: null,
        }),
      ),
    ),
  )
  const query = canvasQuizzesQuery('staff-1')
  const data = await query.queryFn!({ signal: new AbortController().signal } as never)
  expect(data.items[0]).toEqual({ id: '202', title: 'Laser training', points_possible: 10 })
  expect(query.queryKey).toEqual(['staff', 'staff-1', 'canvas', 'quizzes'])
})
it('requests one training or the full sync through the same command and CSRF handling', async () => {
  const fetch = vi
    .fn()
    .mockImplementation(
      async () => new Response(JSON.stringify({ status: 'queued', message: 'Requested' })),
    )
  vi.stubGlobal('fetch', fetch)
  setCsrfToken('synthetic-csrf')
  await requestCanvasSync('training-1')
  expect(fetch.mock.calls[0][0]).toBe('/api/admin/canvas/sync')
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ training_type_id: 'training-1' })
  expect(fetch.mock.calls[0][1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
  await requestCanvasSync()
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({})
  await refreshCanvasQuizzes()
  expect(fetch.mock.calls[2][0]).toBe('/api/admin/canvas/quizzes/refresh')
})
it('reads the genuine whole-sync checkpoint separately from per-training status', async () => {
  const status = {
    configured: true,
    setup_message: null,
    overview: { status: 'idle', started_at: null, last_success_at: '2026-11-01T12:00:00Z', last_error: null },
    trainings: [
      {
        training_type_id: 't',
        name: 'Laser',
        canvas_assignment_id: '202',
        started_at: null,
        last_success_at: null,
        last_error: null,
        status: 'idle',
      },
    ],
    unmatched: [],
    conflicts: [],
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(status))))
  const query = canvasStatusQuery('staff-1')
  const data = await query.queryFn!({ signal: new AbortController().signal } as never)
  expect(data.trainings[0].canvas_assignment_id).toBe('202')
  expect(data.overview.last_success_at).toBe('2026-11-01T12:00:00Z')
})

it('queries the full server-side people cache with principal-scoped page, search and binding filters', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    items: [], total: 205, page: 3, page_size: 100,
  })))
  vi.stubGlobal('fetch', fetch)
  const filters = { binding: 'all' as const, search: 'Synthetic + person', page: 3, page_size: 100 }
  const query = canvasPeopleQuery('staff-2', filters)
  const result = await query.queryFn!({ signal: new AbortController().signal } as never)
  const url = new URL(fetch.mock.calls[0][0], 'http://testserver')
  expect(url.pathname).toBe('/api/admin/canvas/people')
  expect(Object.fromEntries(url.searchParams)).toEqual({
    binding: 'all', search: 'Synthetic + person', page: '3', page_size: '100',
  })
  expect(query.queryKey).toEqual(['staff', 'staff-2', 'canvas', 'people', filters])
  expect(result.total).toBe(205)
})
