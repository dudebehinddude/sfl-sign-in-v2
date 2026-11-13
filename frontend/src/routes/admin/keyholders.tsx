import { useQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'

import { PageHeader } from '@/components/page-header'
import { Pager } from '@/components/pager'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { keyholderShiftsQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { RequirePermission } from '@/features/auth/require-permission'
import { formatDateTime, formatDuration } from '@/lib/format'

export const Route = createFileRoute('/admin/keyholders')({
  component: () => (
    <RequirePermission permission="visits.read">
      <KeyholdersPage />
    </RequirePermission>
  ),
})

function KeyholdersPage() {
  const { keys } = useStaff()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const shifts = useQuery(keyholderShiftsQuery(keys, { page, page_size: pageSize }))

  return (
    <>
      <PageHeader title="Keyholder history" />
      {shifts.isPending ? (
        <LoadingRows rows={8} />
      ) : shifts.isError ? (
        <ErrorState error={shifts.error} onRetry={() => shifts.refetch()} />
      ) : shifts.data.items.length === 0 ? (
        <EmptyState
          title="No keyholder shifts yet"
          description="Shifts appear when someone opens the lab at the station."
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Keyholder</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>Ended</TableHead>
                <TableHead>Length</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shifts.data.items.map((shift) => (
                <TableRow key={shift.id}>
                  <TableCell>
                    <Link
                      to="/admin/users/$userId"
                      params={{ userId: shift.user_id }}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {shift.display_name}
                    </Link>
                  </TableCell>
                  <TableCell>{formatDateTime(shift.started_at)}</TableCell>
                  <TableCell>
                    {shift.ended_at ? (
                      formatDateTime(shift.ended_at)
                    ) : (
                      <Badge>Current keyholder</Badge>
                    )}
                  </TableCell>
                  <TableCell>{formatDuration(shift.started_at, shift.ended_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager
            page={page}
            pageSize={pageSize}
            total={shifts.data.total}
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
