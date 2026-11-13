import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { formatDateTime } from '@/lib/format'
import { CanvasSummary } from '../index'

const { query } = vi.hoisted(() => ({ query: vi.fn() }))
vi.mock('@tanstack/react-query', async original => ({ ...(await original<typeof import('@tanstack/react-query')>()), useQuery: query }))
vi.mock('@tanstack/react-router', async original => ({ ...(await original<typeof import('@tanstack/react-router')>()), Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={to}>{children}</a> }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
const success = '2026-11-09T18:15:00Z'
function mount(status: 'running' | 'idle' | 'error', error: string | null = null) {
  query.mockReturnValue({ isPending: false, isError: false, data: {
    configured: true,
    overview: { status, last_success_at: success, last_error: error, started_at: null },
    trainings: Array.from({ length: 6 }, () => ({ status: 'running', canvas_assignment_id: 'synthetic-quiz', last_error: 'Individual diagnostic' })),
  } })
  render(<CanvasSummary principalId="synthetic-admin" />)
}
it('shows one overall running state and its last successful whole-sync checkpoint', () => {
  mount('running')
  expect(screen.getByText('Syncing')).toBeDefined()
  expect(screen.getByText(`Last successful sync: ${formatDateTime(success)}`)).toBeDefined()
  expect(screen.queryByText(/trainings connected|6 syncing|with errors/)).toBeNull()
})
it('uses overall idle state even when individual diagnostics differ', () => {
  mount('idle')
  expect(screen.getByText('Ready')).toBeDefined()
  expect(screen.queryByText('Individual diagnostic')).toBeNull()
})
it('shows the overall failure while retaining its last successful checkpoint', () => {
  mount('error', 'Canvas request failed')
  expect(screen.getByText('Last sync failed')).toBeDefined()
  expect(screen.getByText('Canvas request failed')).toBeDefined()
  expect(screen.getByText(`Last successful sync: ${formatDateTime(success)}`)).toBeDefined()
})
