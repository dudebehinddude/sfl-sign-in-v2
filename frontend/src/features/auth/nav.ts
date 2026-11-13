import type { LucideIcon } from 'lucide-react'
import {
  AwardIcon,
  BarChart3Icon,
  DatabaseIcon,
  DoorOpenIcon,
  GaugeIcon,
  FolderArchiveIcon,
  GraduationCapIcon,
  KeyRoundIcon,
  PrinterIcon,
  RefreshCwIcon,
  ScrollTextIcon,
  UsersIcon,
} from 'lucide-react'

import type { Permission, SessionUser } from '@/lib/api/types'
import { hasPermission } from './session'

type AdminRoute =
  | '/admin'
  | '/admin/users'
  | '/admin/trainings'
  | '/admin/training-types'
  | '/admin/storage'
  | '/admin/visits'
  | '/admin/keyholders'
  | '/admin/metrics'
  | '/admin/canvas'
  | '/admin/printing'
  | '/admin/audit'
  | '/admin/database'

export type AdminNavItem = {
  label: string
  icon: LucideIcon
  permission: Permission | null
  /** The backend additionally requires the superadmin role for these routes. */
  superadmin?: boolean
  group: 'Lab' | 'Integrations' | 'System'
  to: AdminRoute
}

export const ADMIN_NAV: AdminNavItem[] = [
  {
    to: '/admin/storage',
    label: 'Storage',
    icon: FolderArchiveIcon,
    permission: null,
    superadmin: true,
    group: 'System',
  },
  { to: '/admin', label: 'Overview', icon: GaugeIcon, permission: null, group: 'Lab' },
  { to: '/admin/users', label: 'People', icon: UsersIcon, permission: 'users.read', group: 'Lab' },
  {
    to: '/admin/visits',
    label: 'Visits',
    icon: DoorOpenIcon,
    permission: 'visits.read',
    group: 'Lab',
  },
  {
    to: '/admin/keyholders',
    label: 'Keyholder history',
    icon: KeyRoundIcon,
    permission: 'visits.read',
    group: 'Lab',
  },
  {
    to: '/admin/training-types',
    label: 'Training types',
    icon: GraduationCapIcon,
    permission: 'trainings.read',
    group: 'Lab',
  },
  {
    to: '/admin/trainings',
    label: 'Trainings',
    icon: AwardIcon,
    permission: 'trainings.read',
    group: 'Lab',
  },
  {
    to: '/admin/metrics',
    label: 'Metrics',
    icon: BarChart3Icon,
    permission: 'metrics.read',
    group: 'Lab',
  },
  {
    to: '/admin/canvas',
    label: 'Canvas sync',
    icon: RefreshCwIcon,
    permission: 'canvas.read',
    group: 'Integrations',
  },
  {
    to: '/admin/printing',
    label: 'Label printing',
    icon: PrinterIcon,
    permission: 'printing.read',
    group: 'Integrations',
  },
  {
    to: '/admin/audit',
    label: 'Audit log',
    icon: ScrollTextIcon,
    permission: 'audit.read',
    group: 'System',
  },
  {
    to: '/admin/database',
    label: 'Database',
    icon: DatabaseIcon,
    permission: 'database.read',
    group: 'System',
  },
]

export function canSeeNavItem(user: SessionUser | null | undefined, item: AdminNavItem) {
  if (item.superadmin && user?.role !== 'superadmin') return false
  return item.permission === null || hasPermission(user, item.permission)
}

const STAFF_PERMISSIONS = ADMIN_NAV.flatMap((item) => (item.permission ? [item.permission] : []))

export function canOpenAdmin(user: SessionUser | null | undefined) {
  return (
    Boolean(user?.role) && STAFF_PERMISSIONS.some((permission) => hasPermission(user, permission))
  )
}

export function visibleNav(user: SessionUser | null | undefined) {
  if (!canOpenAdmin(user)) return []
  return ADMIN_NAV.filter((item) => canSeeNavItem(user, item))
}
