import { expect, it } from 'vitest'
import type { Permission, Role, SessionUser } from '@/lib/api/types'
import { visibleNav } from './nav'
function principal(role: Role | null, permissions: Permission[]): SessionUser {
  return {
    id: 'actor',
    display_name: 'Test Staff',
    email: 'staff@charlotte.edu',
    role,
    permissions,
  }
}
it('admin can discover read-only SQL without storage or superadmin access', () => {
  const routes = visibleNav(
    principal('admin', ['users.read', 'trainings.read', 'database.read', 'audit.read']),
  ).map((item) => item.to)
  expect(routes).toContain('/admin/database')
  expect(routes).toContain('/admin/audit')
  expect(routes).toContain('/admin/trainings')
  expect(routes).toContain('/admin/training-types')
  expect(routes).not.toContain('/admin/storage')
})
it('operator can read audit and trainings while SQL and storage remain absent', () => {
  const routes = visibleNav(
    principal('operator', ['users.read', 'trainings.read', 'audit.read']),
  ).map((item) => item.to)
  expect(routes).toContain('/admin/audit')
  expect(routes).not.toContain('/admin/database')
  expect(routes).not.toContain('/admin/storage')
})
it('superadmin can discover in-app storage and a visitor gets no staff navigation', () => {
  expect(
    visibleNav(principal('superadmin', ['users.read', 'database.read'])).map((item) => item.to),
  ).toContain('/admin/storage')
  expect(visibleNav(principal(null, []))).toEqual([])
})
