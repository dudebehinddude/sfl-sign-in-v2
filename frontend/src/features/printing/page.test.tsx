import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api/client'
import { PrintingPage } from './page'

const { session } = vi.hoisted(() => ({ session: vi.fn() }))
vi.mock('@/features/auth/session', () => ({ useSession: session }))
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<typeof import('@/lib/api/client')>()),
  api: vi.fn(),
}))
afterEach(() => vi.clearAllMocks())
it('does not request printer information for an unauthorized account', () => {
  session.mockReturnValue({ user: { id: 'visitor' }, can: () => false })
  render(<PrintingPage />)
  expect(screen.getByText('Printing access required')).toBeDefined()
  expect(api).not.toHaveBeenCalled()
})
it('shows an offline printer as a dropped label rather than a pending queue', async () => {
  session.mockReturnValue({ user: { id: 'staff' }, can: () => true })
  vi.mocked(api).mockImplementation(async (path) =>
    path.endsWith('/status')
      ? { connected: false, busy: false, last_result: null }
      : {
          items: [{ id: 'person', display_name: 'Test Person', email: null, active: true }],
          total: 1,
          page: 1,
          page_size: 8,
        },
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PrintingPage />
    </QueryClientProvider>,
  )
  expect(await screen.findByText('Offline', { exact: true })).toBeDefined()
  fireEvent.change(screen.getByLabelText('Find a person'), { target: { value: 'Test' } })
  await screen.findByText('Test Person')
  expect(screen.getByRole('button', { name: 'Print label' })).toBeDisabled()
  expect(
    screen.getByText(
      'When the printer is offline or busy, the label is dropped. Connecting later does not print old labels.',
    ),
  ).toBeDefined()
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/print'))).toBe(false)
  client.clear()
})
