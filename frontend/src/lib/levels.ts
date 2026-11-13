import type { AccessLevel, Role } from '@/lib/api/types'

export const ACCESS_LEVELS: AccessLevel[] = [0, 1, 2, 3]
export const ACCESS_LEVEL_LABEL: Record<AccessLevel, string> = {
  0: 'Member',
  1: 'Volunteer',
  2: 'Keyholder',
  3: 'Staff',
}
export const ROLES: Role[] = ['operator', 'admin', 'superadmin']
export const ROLE_LABEL: Record<Role, string> = {
  operator: 'Operator',
  admin: 'Admin',
  superadmin: 'Superadmin',
}
