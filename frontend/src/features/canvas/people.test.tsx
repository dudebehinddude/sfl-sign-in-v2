import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/lib/api/client'
import { CanvasPeopleList } from './people'

vi.mock('@/lib/api/client', async original => ({
  ...(await original<typeof import('@/lib/api/client')>()), api: vi.fn(),
}))
const clients: QueryClient[] = []
afterEach(() => {
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.clearAllMocks()
})
const rows = Array.from({ length: 205 }, (_, index) => ({
  id: `fixture-${index + 1}`, display_name: `Synthetic person ${index + 1}`,
  email: `synthetic-${index + 1}@charlotte.edu`, canvas_id: `${index + 1}`,
  user_id: null, conflict: index === 204 ? 'Synthetic conflict' : null,
}))
function setup() {
  vi.mocked(api).mockImplementation(async path => {
    const params = new URL(String(path), 'http://testserver').searchParams
    const binding = params.get('binding')
    const search = params.get('search') ?? ''
    const page = Number(params.get('page'))
    const pageSize = Number(params.get('page_size'))
    const matches = rows.filter(row =>
      (binding !== 'conflicts' || row.conflict) &&
      `${row.display_name} ${row.email}`.includes(search),
    )
    return { items: matches.slice((page - 1) * pageSize, page * pageSize),
      total: matches.length, page, page_size: pageSize } as never
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  render(<QueryClientProvider client={client}>
    <CanvasPeopleList principalId="synthetic-staff" canReadUsers={false} />
  </QueryClientProvider>)
}
it('pages beyond the first 100 cached people and searches the entire server-side cache', async () => {
  setup()
  await screen.findByText('1–100 of 205')
  expect(screen.queryByText('Synthetic person 205')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await screen.findByText('101–200 of 205')
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await screen.findByText('201–205 of 205')
  expect(screen.getByText('Synthetic person 205')).toBeVisible()
  fireEvent.change(screen.getByLabelText('Search name or email'), {
    target: { value: 'synthetic-205@charlotte.edu' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  await screen.findByText('1–1 of 1')
  expect(screen.getByText('Synthetic person 205')).toBeVisible()
  const last = String(vi.mocked(api).mock.calls.at(-1)?.[0])
  expect(new URL(last, 'http://testserver').searchParams.get('page')).toBe('1')
})
it('resets page for binding and row-size changes, including 1000 rows', async () => {
  setup()
  await screen.findByText('1–100 of 205')
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await screen.findByText('101–200 of 205')
  fireEvent.change(screen.getByLabelText('Binding'), { target: { value: 'conflicts' } })
  await screen.findByText('1–1 of 1')
  expect(screen.getByText('Synthetic conflict')).toBeVisible()
  fireEvent.change(screen.getByLabelText('Binding'), { target: { value: 'all' } })
  await screen.findByText('1–100 of 205')
  fireEvent.change(screen.getByLabelText('Rows per page'), { target: { value: '1000' } })
  await screen.findByText('1–205 of 205')
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  const last = new URL(String(vi.mocked(api).mock.calls.at(-1)?.[0]), 'http://testserver')
  expect(last.searchParams.get('binding')).toBe('all')
  expect(last.searchParams.get('page_size')).toBe('1000')
  expect(last.searchParams.get('page')).toBe('1')
})
it('shows a retryable people-query error without presenting a false empty cache', async () => {
  setup()
  await screen.findByText('1–100 of 205')
  vi.mocked(api).mockRejectedValueOnce(new Error('Synthetic request failed'))
  fireEvent.change(screen.getByLabelText('Search name or email'), { target: { value: 'missing' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
  await screen.findByText('Synthetic request failed')
  expect(screen.queryByText('No matching Canvas people')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(screen.getByText('No matching Canvas people')).toBeVisible())
})
