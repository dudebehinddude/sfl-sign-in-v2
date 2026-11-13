import { useQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'

import { ConfirmAction } from '@/components/confirm-action'
import { PageHeader } from '@/components/page-header'
import { Pager } from '@/components/pager'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { closeVisit, visitsQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import { RequirePermission } from '@/features/auth/require-permission'
import type { Visit } from '@/lib/api/types'
import { formatDateTime, formatDuration } from '@/lib/format'

export const Route = createFileRoute('/admin/visits')({
  component: () => (
    <RequirePermission permission="visits.read">
      <VisitsPage />
    </RequirePermission>
  ),
})

type VisitFilter = 'all' | 'active' | 'ended'

function VisitsPage() {
  const { keys, can } = useStaff()
  const [filter, setFilter] = useState<VisitFilter>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const visits = useQuery(
    visitsQuery(keys, {
      page,
      page_size: pageSize,
      active: filter === 'all' ? undefined : filter === 'active',
    }),
  )
  const close = useStaffMutation({
    mutationFn: ({ id, forgot }: { id: string; forgot: boolean }) => closeVisit(id, forgot),
    topics: ['visits', 'metrics', 'overview'],
    success: () => 'Visit closed',
  })

  return (
    <>
      <PageHeader title="Visits" />
      <ToggleGroup
        aria-label="Which visits to show"
        variant="outline"
        value={[filter]}
        onValueChange={(value: string[]) => {
          const next = value[0] as VisitFilter | undefined
          if (!next) return
          setFilter(next)
          setPage(1)
        }}
      >
        <ToggleGroupItem value="all">All visits</ToggleGroupItem>
        <ToggleGroupItem value="active">Still signed in</ToggleGroupItem>
        <ToggleGroupItem value="ended">Signed out</ToggleGroupItem>
      </ToggleGroup>
      {visits.isPending ? (
        <LoadingRows rows={8} />
      ) : visits.isError ? (
        <ErrorState error={visits.error} onRetry={() => visits.refetch()} />
      ) : visits.data.items.length === 0 ? (
        <EmptyState title={filter === 'active' ? 'Nobody is signed in' : 'No visits yet'} />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Signed in</TableHead>
                <TableHead>Signed out</TableHead>
                <TableHead>Length</TableHead>
                <TableHead>How it ended</TableHead>
                {can('visits.write') ? <TableHead className="text-right">Actions</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {visits.data.items.map((visit) => (
                <TableRow key={visit.id}>
                  <TableCell>
                    <Link
                      to="/admin/users/$userId"
                      params={{ userId: visit.user_id }}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {visit.display_name ?? 'Person'}
                    </Link>
                  </TableCell>
                  <TableCell>{formatDateTime(visit.enter_time)}</TableCell>
                  <TableCell>
                    {visit.exit_time ? (
                      formatDateTime(visit.exit_time)
                    ) : (
                      <Badge variant="secondary">In the lab</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {visit.forgot_to_sign_out || !visit.exit_time
                      ? ''
                      : formatDuration(visit.enter_time, visit.exit_time)}
                  </TableCell>
                  <TableCell>
                    {visit.forgot_to_sign_out ? (
                      <Badge variant="destructive">Forgot to sign out</Badge>
                    ) : visit.exit_time ? (
                      'Signed out'
                    ) : (
                      ''
                    )}
                  </TableCell>
                  {can('visits.write') ? (
                    <TableCell className="text-right">
                      {visit.exit_time ? null : (
                        <CloseVisitActions
                          visit={visit}
                          onClose={(forgot) => close.mutate({ id: visit.id, forgot })}
                        />
                      )}
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager
            page={page}
            pageSize={pageSize}
            total={visits.data.total}
            onPage={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPage(1)
            }}
          />
        </>
      )}
    </>
  )
}

function CloseVisitActions({
  visit,
  onClose,
}: {
  visit: Visit
  onClose: (forgot: boolean) => void
}) {
  return (
    <div className="flex justify-end gap-2">
      <ConfirmAction
        trigger={<Button size="sm" variant="destructive" />}
        triggerLabel="Set forgot"
        title={`Mark ${visit.display_name ?? 'this visit'} as forgot?`}
        description="Ends the visit now and flags it as a forgotten sign-out. It still counts as a visit, but not toward hour totals."
        confirmLabel="Mark as forgot"
        destructive
        onConfirm={() => onClose(true)}
      />
      <ConfirmAction
        trigger={<Button size="sm" variant="outline" />}
        triggerLabel="Sign out"
        title={`Sign out ${visit.display_name ?? 'this person'}?`}
        description="Ends the visit now as a normal staff sign-out. The time counts toward hour totals."
        confirmLabel="Sign out"
        onConfirm={() => onClose(false)}
      />
    </div>
  )
}
