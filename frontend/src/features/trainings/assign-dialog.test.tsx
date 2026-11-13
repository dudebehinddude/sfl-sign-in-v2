import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Button } from '@/components/ui/button'
import { staffKeys } from '@/lib/query-keys'
import { AssignTrainingDialog } from './assign-dialog'
const { staff } = vi.hoisted(() => ({ staff: vi.fn() }))
vi.mock('@/features/admin/use-staff', () => ({ useStaff: staff }))
afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})
it('operator assigns training directly without an own-training or level prerequisite', async () => {
  staff.mockReturnValue({
    user: { id: 'operator', role: 'operator' },
    keys: staffKeys('operator'),
    can: () => true,
    isAdmin: false,
    isSuperadmin: false,
  })
  const fetch = vi
    .fn()
    .mockImplementation(
      async (path: string) =>
        new Response(
          JSON.stringify(
            path.startsWith('/api/admin/training-types')
              ? {
                  items: [
                    { id: 'laser', name: 'Laser cutter', icon_key: 'laser-cutter', active: true },
                  ],
                  total: 1,
                  page: 1,
                  page_size: 1000,
                }
              : { id: 'award', has_training: true },
          ),
        ),
    )
  vi.stubGlobal('fetch', fetch)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <AssignTrainingDialog
        trigger={<Button />}
        user={{ id: 'visitor', display_name: 'Visitor Person' }}
      />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Assign training' }))
  const dialog = await screen.findByRole('dialog')
  await within(dialog).findByRole('option', { name: 'Laser cutter' })
  expect(within(dialog).queryByLabelText('Level')).toBeNull()
  fireEvent.change(within(dialog).getByLabelText('Training'), { target: { value: 'laser' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Assign training' }))
  await waitFor(() =>
    expect(fetch.mock.calls.some(([path]) => path === '/api/admin/trainings')).toBe(true),
  )
  const request = fetch.mock.calls.find(([path]) => path === '/api/admin/trainings')!
  expect(JSON.parse(request[1].body)).toEqual({ user_id: 'visitor', training_type_id: 'laser' })
  expect(fetch.mock.calls.some(([path]) => path === '/api/me/profile')).toBe(false)
  client.clear()
})
