import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api/client'
import { MetricsPage } from './dashboard'
import type { MetricsResponse } from './data'

const { session } = vi.hoisted(() => ({ session: vi.fn() }))
vi.mock('@/features/auth/session', () => ({ useSession: session }))
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<typeof import('@/lib/api/client')>()),
  api: vi.fn(),
}))
vi.mock('./daily-charts', () => ({
  DailyCharts: () => <div aria-label="Chart test substitute" />,
}))

const data: MetricsResponse = {
  start: '2026-10-01',
  end: '2026-11-01',
  timezone: 'America/New_York',
  summary: {
    unique_visitors: 4,
    visits: 6,
    finalized_visits: 2,
    total_hours: 1.5,
    average_visit_minutes: 45,
    new_visitors: 1,
    excluded_visits: 2,
    open_visits: 2,
  },
  daily: [
    { date: '2026-11-01', visits: 3, unique_visitors: 3, total_hours: 0.75 },
    { date: '2026-11-02', visits: 3, unique_visitors: 2, total_hours: 0.75 },
  ],
  definitions: {},
}
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.restoreAllMocks()
})
beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-11-09T17:00:00Z'))
  session.mockReturnValue({
    query: { isPending: false, isError: false },
    user: { id: 'reporter' },
    can: () => true,
  })
  vi.mocked(api).mockResolvedValue(data)
})

it('does not request reporting data without reporting permission', () => {
  session.mockReturnValue({
    query: { isPending: false, isError: false },
    user: { id: 'operator' },
    can: () => false,
  })
  render(<MetricsPage />)
  expect(screen.getByText('You need reporting permission to view lab metrics.')).toBeDefined()
  expect(api).not.toHaveBeenCalled()
})
it('defaults to last calendar month, removes timezone controls and keeps CSV on the applied inclusive range', async () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MetricsPage />
    </QueryClientProvider>,
  )
  expect(await screen.findByText('Calculated across 2 finalized visits.')).toBeDefined()
  expect(screen.getByText('2 open visits')).toBeDefined()
  expect(screen.getByText('2 other excluded visits')).toBeDefined()
  expect(screen.queryByLabelText('Reporting timezone')).toBeNull()
  expect((screen.getByLabelText('Start date') as HTMLInputElement).value).toBe('2026-10-01')
  expect((screen.getByLabelText('End date') as HTMLInputElement).value).toBe('2026-10-31')
  expect(api).toHaveBeenCalledWith('/api/admin/metrics', expect.objectContaining({ query: { start: '2026-10-01', end: '2026-11-01', timezone: 'America/New_York' } }))
  const link = screen.getByRole('link', {
    name: 'Export CSV',
  }) as HTMLAnchorElement
  expect(new URL(link.href).searchParams.get('start')).toBe(data.start)
  fireEvent.change(screen.getByLabelText('Start date'), {
    target: { value: '2026-10-15' },
  })
  expect(new URL(link.href).searchParams.get('start')).toBe(data.start)
  expect(new URL(link.href).searchParams.get('timezone')).toBe('America/New_York')
  client.clear()
})


it('includes a same-day end date by requesting the next midnight', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MetricsPage /></QueryClientProvider>)
  await screen.findByRole('link', { name: 'Export CSV' })
  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-11-01' } })
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-11-01' } })
  fireEvent.click(screen.getByRole('button', { name: 'Apply dates' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/admin/metrics', expect.objectContaining({ query: { start: '2026-11-01', end: '2026-11-02', timezone: 'America/New_York' } })))
  client.clear()
})
