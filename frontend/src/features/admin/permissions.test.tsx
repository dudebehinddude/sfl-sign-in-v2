import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { UserDetail } from '@/routes/admin/users/$userId'
import type { AdminUser, Permission, Role } from '@/lib/api/types'
import { staffKeys } from '@/lib/query-keys'

const { staff } = vi.hoisted(() => ({ staff: vi.fn() }))
vi.mock('@/features/admin/use-staff', () => ({ useStaff: staff }))
vi.mock('@/routes/admin/_components/users/user-trainings', () => ({
  UserTrainings: () => <div>Training records</div>,
}))
const clients: QueryClient[] = []
afterEach(() => {
  for (const client of clients) client.clear()
  clients.length = 0
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})
const person: AdminUser = {
  id: 'person-1',
  first_name: 'Ada',
  last_name: 'Lovelace',
  display_name: 'Ada Lovelace',
  email: 'ada@charlotte.edu',
  role: 'operator',
  space_level: 0,
  keyholder_priority: -1,
  active: true,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
  identifiers: [],
  badges: [],
}
function mount(role: Role, target = person) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  staff.mockReturnValue({
    user: { id: 'actor', role },
    keys: staffKeys('actor'),
    isAdmin: role !== 'operator',
    isSuperadmin: role === 'superadmin',
    can: (permission: Permission) =>
      ['users.read', 'users.write', 'trainings.read', 'trainings.write'].includes(permission),
  })
  render(
    <QueryClientProvider client={client}>
      <UserDetail user={target} />
    </QueryClientProvider>,
  )
}
it('operator can edit basic details without access, role or password controls', () => {
  mount('operator')
  expect(screen.getByLabelText('First name')).toBeVisible()
  expect(screen.getByLabelText('University email')).toBeVisible()
  expect(screen.queryByLabelText('Space level')).toBeNull()
  expect(screen.queryByLabelText('Keyholder priority')).toBeNull()
  expect(screen.queryByLabelText('Account active')).toBeNull()
  expect(screen.queryByLabelText('Role')).toBeNull()
  expect(screen.queryByLabelText('New password')).toBeNull()
})
it('administrator can assign one non-superadmin role without permission dumps', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ ...person, role: 'admin' })))
  vi.stubGlobal('fetch', fetch)
  mount('admin')
  expect(screen.getByLabelText('Space level')).toBeVisible()
  const role = screen.getByLabelText('Role')
  expect(role).toHaveValue('operator')
  expect(screen.queryByRole('option', { name: 'Superadmin' })).toBeNull()
  expect(screen.queryByLabelText('New password')).toBeNull()
  fireEvent.change(role, { target: { value: 'admin' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save role' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
  const [path, options] = fetch.mock.calls[0]
  expect(path).toBe('/api/admin/users/person-1/role')
  expect(options.method).toBe('PUT')
  expect(JSON.parse(options.body)).toEqual({ role: 'admin' })
  expect(document.body.textContent).not.toMatch(/users\.write|database\.read/)
})
it('administrator has no access/security/role controls on a superadmin target', () => {
  mount('admin', { ...person, role: 'superadmin' })
  expect(screen.getByLabelText('First name')).toBeVisible()
  expect(screen.queryByLabelText('Space level')).toBeNull()
  expect(screen.queryByLabelText('Role')).toBeNull()
  expect(screen.queryByLabelText('New password')).toBeNull()
})
it('superadmin retains full role and password controls', () => {
  mount('superadmin', { ...person, role: 'superadmin' })
  expect(screen.getByRole('option', { name: 'Superadmin' })).toBeVisible()
  expect(screen.getByLabelText('Role')).toHaveValue('superadmin')
  expect(screen.getByLabelText('New password')).toBeVisible()
})
it('basic editing blocks non-university addresses while accepting the university alias', () => {
  mount('operator')
  fireEvent.change(screen.getByLabelText('University email'), {
    target: { value: 'ada@example.com' },
  })
  expect(screen.getByText('Use your @charlotte.edu or @uncc.edu email.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Save details' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('University email'), { target: { value: 'Ada@UNCC.edu' } })
  expect(screen.getByRole('button', { name: 'Save details' })).toBeEnabled()
})
