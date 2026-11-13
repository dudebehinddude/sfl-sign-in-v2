import type { ReactNode } from 'react'
import { ShieldAlertIcon } from 'lucide-react'

import { EmptyState } from '@/components/query-state'
import type { Permission } from '@/lib/api/types'
import { useSession } from './session'

/**
 * Renders children only when the session holds the permission (and the
 * superadmin role, when required), so pages behind it never issue privileged
 * requests for an unauthorized user. The backend still enforces both.
 */
export function RequirePermission({
  permission,
  superadmin = false,
  children,
  description,
}: {
  permission: Permission
  superadmin?: boolean
  children: ReactNode
  description?: string
}) {
  const { can, isSuperadmin } = useSession()
  if (!can(permission) || (superadmin && !isSuperadmin)) {
    return (
      <EmptyState
        icon={<ShieldAlertIcon />}
        title="You do not have access to this page"
        description={
          description ??
          (superadmin
            ? 'Only superadmins can open this page.'
            : 'Your staff role cannot open this page.')
        }
      />
    )
  }
  return children
}
