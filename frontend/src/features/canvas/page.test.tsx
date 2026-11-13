import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api/client'
import { CanvasPage } from './page'
import type { CanvasStatus } from './types'

const { session } = vi.hoisted(() => ({ session: vi.fn() }))
vi.mock('@/features/auth/session', () => ({ useSession: session }))
vi.mock('@/lib/api/client', async original => ({ ...(await original<typeof import('@/lib/api/client')>()), api: vi.fn() }))
const clients: QueryClient[] = []
afterEach(() => { clients.forEach(client => client.clear()); clients.length = 0; vi.clearAllMocks() })
function mount({ wholeSuccess = '2026-11-01T12:00:00Z', running = false, write = true, allowed = true }: {
  wholeSuccess?: string | null; running?: boolean; write?: boolean; allowed?: boolean
} = {}) {
  const status: CanvasStatus = {
    configured: true, setup_message: null,
    overview: { status: running ? 'running' : 'idle', started_at: null, last_success_at: wholeSuccess, last_error: null },
    trainings: [{ training_type_id: 'synthetic-training', name: 'Hidden individual training', canvas_assignment_id: '202', started_at: null,
      last_success_at: '2026-11-08T12:00:00Z', last_error: null, status: 'idle' }], unmatched: [], conflicts: [],
  }
  session.mockReturnValue({ user: { id: 'synthetic-staff' }, can: (permission: string) => allowed && (permission !== 'canvas.write' || write) })
  vi.mocked(api).mockImplementation(async path => {
    if (path.endsWith('/status')) return status as never
    if (path.startsWith('/api/admin/canvas/people')) return { items: [], total: 0, page: 1, page_size: 100 } as never
    if (path.endsWith('/sync')) return { status: 'queued', message: 'Synthetic sync queued' } as never
    throw new Error('Unexpected synthetic request')
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}><CanvasPage /></QueryClientProvider>)
}
it('shows only the whole-sync checkpoint and one sync action with Canvas Users', async () => {
  mount()
  await screen.findByText('Last successful sync:')
  expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-11-01T12:00:00Z')
  expect(screen.getByRole('heading', { name: 'Canvas Users' })).toBeVisible()
  expect(screen.queryByText('Hidden individual training')).toBeNull()
  expect(screen.queryByText('Training sync status')).toBeNull()
  expect(screen.queryByText('Cached quiz results keep badges ready before people scan in.')).toBeNull()
  expect(screen.queryByText(/Failed syncs preserve previously cached results/)).toBeNull()
  expect(screen.getAllByRole('button', { name: /sync/i })).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: 'Sync Canvas' }))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/admin/canvas/sync', { method: 'POST', body: {} }))
})
it('does not substitute a recent individual-training success for a missing whole-sync success', async () => {
  mount({ wholeSuccess: null })
  await screen.findByText('Never')
  expect(document.querySelector('time')).toBeNull()
})
it('disables the only sync command while the backend reports a queued or running job', async () => {
  mount({ running: true })
  expect(await screen.findByRole('button', { name: 'Syncing…' })).toBeDisabled()
})
it('retains the user list for a read-only operator without a sync control', async () => {
  mount({ write: false })
  await screen.findByText('Last successful sync:')
  expect(screen.getByRole('heading', { name: 'Canvas Users' })).toBeVisible()
  expect(screen.queryByRole('button', { name: /sync/i })).toBeNull()
})
it('requests no protected data without Canvas read access', () => {
  mount({ allowed: false })
  expect(screen.getByText('Canvas access required')).toBeVisible()
  expect(api).not.toHaveBeenCalled()
})
