import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Suspense, type ComponentProps, type ReactElement } from 'react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'
import { SidebarProvider } from '@/components/ui/sidebar'
import type { SessionUser } from '@/lib/api/types'
import { Route } from '../route'
const AdminLayout = Route.options.component as () => ReactElement
import { AdminSidebar } from './admin-sidebar'

const { mobile } = vi.hoisted(() => ({ mobile: vi.fn(() => false) }))
vi.mock('@/hooks/use-mobile', () => ({ useIsMobile: mobile }))
vi.mock('@tanstack/react-router', async original => ({
  ...(await original<typeof import('@tanstack/react-router')>()),
  Link: ({ to, children, onClick, ...props }: ComponentProps<'a'> & { to: string }) => <a href={to} {...props} onClick={event => { event.preventDefault(); onClick?.(event) }}>{children}</a>,
  useRouterState: () => '/admin/users', useNavigate: () => vi.fn(),
  Outlet: () => <div>Actual page content</div>,
}))
vi.mock('@/features/admin/use-admin-live', () => ({ useAdminLive: () => 'live' }))
vi.mock('@/features/auth/session', async original => ({
  ...(await original<typeof import('@/features/auth/session')>()),
  useLogout: () => ({ mutate: vi.fn() }),
  useSession: () => ({ user: { id: 'synthetic-staff', role: 'admin', permissions: ['users.read'] } }),
}))
const user: SessionUser = { id: 'synthetic-staff', display_name: 'Synthetic Staff', email: null, role: 'admin', permissions: ['users.read'] }
beforeAll(async () => {
  await (Route.options.component as { preload?: () => Promise<unknown> }).preload?.()
})
afterEach(() => { mobile.mockReturnValue(false) })
it('keeps collapse and expand controls in the desktop sidebar header', () => {
  render(<SidebarProvider><AdminSidebar user={user} /></SidebarProvider>)
  const sidebar = document.querySelector('[data-slot="sidebar"]')
  expect(sidebar).toHaveAttribute('data-state', 'expanded')
  const collapse = screen.getByRole('button', { name: 'Collapse navigation' })
  expect(collapse.closest('[data-slot="sidebar-header"]')).not.toBeNull()
  fireEvent.click(collapse)
  expect(sidebar).toHaveAttribute('data-state', 'collapsed')
  expect(sidebar).toHaveAttribute('data-collapsible', 'icon')
  fireEvent.click(screen.getByRole('button', { name: 'Expand navigation' }))
  expect(sidebar).toHaveAttribute('data-state', 'expanded')
})
it('removes the redundant dashboard topbar without removing the actual page', async () => {
  render(<Suspense><AdminLayout /></Suspense>)
  await screen.findByText('Actual page content')
  expect(screen.queryByText('Staff dashboard')).toBeNull()
  expect(document.querySelector('header')).toBeNull()
  expect(screen.getByText('Actual page content')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Collapse navigation' })).toBeInTheDocument()
})
it('opens the mobile drawer from outside and closes it after choosing a page', async () => {
  mobile.mockReturnValue(true)
  render(<Suspense><AdminLayout /></Suspense>)
  await screen.findByText('Actual page content')
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
  await screen.findByRole('dialog')
  expect(screen.getByRole('button', { name: 'Close navigation' })).toBeVisible()
  fireEvent.click(screen.getByRole('link', { name: 'People' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(screen.getByRole('button', { name: 'Open navigation' })).toBeVisible()
})
