import { useQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { ArrowLeftIcon, PrinterIcon, RefreshCwIcon } from 'lucide-react'

import { LoadingRows, ErrorState } from '@/components/query-state'
import { TrainingBadgeList } from '@/components/training-badge'
import { Typography } from '@/components/typography'
import { UserAvatar } from '@/components/user-avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { matchUserCanvas, printUserLabel, userQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import { RequirePermission } from '@/features/auth/require-permission'
import type { AdminUser } from '@/lib/api/types'
import { formatDateTime, humanize } from '@/lib/format'
import { ACCESS_LEVEL_LABEL } from '@/lib/levels'
import { UserTrainings } from '../_components/users/user-trainings'
import { AccessForm, IdentityForm, PasswordForm, RoleForm } from '../_components/users/user-forms'

export const Route = createFileRoute('/admin/users/$userId')({
  component: () => (
    <RequirePermission permission="users.read">
      <UserPage />
    </RequirePermission>
  ),
})

function UserPage() {
  const { userId } = Route.useParams()
  const { keys } = useStaff()
  const user = useQuery(userQuery(keys, userId))

  return (
    <div className="flex flex-col gap-8">
      <Button
        variant="ghost"
        size="sm"
        className="self-start"
        nativeButton={false}
        render={<Link to="/admin/users" />}
      >
        <ArrowLeftIcon data-icon="inline-start" />
        All people
      </Button>
      {user.isPending ? (
        <LoadingRows rows={6} />
      ) : user.isError ? (
        <ErrorState error={user.error} onRetry={() => user.refetch()} />
      ) : (
        <UserDetail key={user.data.updated_at} user={user.data} />
      )}
    </div>
  )
}

export function UserDetail({ user }: { user: AdminUser }) {
  const { can, isAdmin, isSuperadmin } = useStaff()
  const print = useStaffMutation({
    mutationFn: () => printUserLabel(user.id),
    topics: ['printing'],
    success: (result) => result.message,
  })
  const canvas = useStaffMutation({
    mutationFn: () => matchUserCanvas(user.id),
    topics: ['canvas', 'trainings', 'users'],
    success: 'Checked the latest Canvas roster for this person',
  })

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-6">
        <div className="flex items-center gap-4">
          <UserAvatar name={user.display_name} url={user.avatar_url} size="lg" />
          <div className="flex flex-col gap-1">
            <Typography variant="h1">{user.display_name}</Typography>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              {user.email ? <span>{user.email}</span> : <span>No email</span>}
              <Badge variant="outline">{ACCESS_LEVEL_LABEL[user.space_level]}</Badge>
              {user.active ? null : <Badge variant="destructive">Inactive</Badge>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {can('printing.write') ? (
            <Button
              variant="outline"
              disabled={print.isPending}
              onClick={() => print.mutate(undefined)}
            >
              <PrinterIcon data-icon="inline-start" />
              Print label
            </Button>
          ) : null}
          {can('canvas.write') ? (
            <Button
              variant="outline"
              disabled={canvas.isPending}
              onClick={() => canvas.mutate(undefined)}
            >
              <RefreshCwIcon data-icon="inline-start" />
              Match Canvas
            </Button>
          ) : null}
        </div>
      </header>

      <dl className="grid gap-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">IDs</dt>
          <dd className="flex flex-col">
            {user.identifiers.length
              ? user.identifiers.map((identifier) => (
                  <span key={`${identifier.provider}:${identifier.value}`}>
                    <span className="font-mono">{identifier.value}</span>{' '}
                    <span className="text-muted-foreground">({humanize(identifier.provider)})</span>
                  </span>
                ))
              : 'None'}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Keyholder priority</dt>
          <dd className="tabular-nums">{user.keyholder_priority}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Registered</dt>
          <dd>{formatDateTime(user.created_at)}</dd>
        </div>
      </dl>

      <section aria-label="Current badges">
        <TrainingBadgeList badges={user.badges} />
      </section>

      <div className="flex flex-col">
        {can('users.write') ? <IdentityForm user={user} /> : null}
        {can('users.write') && isAdmin && (isSuperadmin || user.role !== 'superadmin') ? (
          <AccessForm user={user} />
        ) : null}
        {isAdmin && (isSuperadmin || user.role !== 'superadmin') ? <RoleForm user={user} /> : null}
        {isSuperadmin ? <PasswordForm user={user} /> : null}
      </div>

      {can('trainings.read') ? <UserTrainings user={user} /> : null}
    </>
  )
}
