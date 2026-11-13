import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { Pager } from '@/components/pager'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { auditQuery } from '@/features/admin/api'
import { auditSummary } from '@/features/admin/audit-details'
import { useStaff } from '@/features/admin/use-staff'
import { RequirePermission } from '@/features/auth/require-permission'
import { formatDateTime } from '@/lib/format'
export const Route = createFileRoute('/admin/audit')({
  component: () => (
    <RequirePermission permission="audit.read">
      <AuditPage />
    </RequirePermission>
  ),
})
export function AuditPage() {
  const { keys } = useStaff()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const events = useQuery(auditQuery(keys, { page, page_size: pageSize }))
  return (
    <>
      <PageHeader title="Audit log" />
      {events.isPending ? (
        <LoadingRows />
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => events.refetch()} />
      ) : !events.data.items.length ? (
        <EmptyState title="No events" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Details</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data.items.map((event) => (
                <TableRow key={event.id}>
                  <TableCell className="whitespace-nowrap">
                    {formatDateTime(event.occurred_at)}
                  </TableCell>
                  <TableCell>{event.action_label}</TableCell>
                  <TableCell>
                    {event.actor_href ? (
                      <a href={event.actor_href} className="underline-offset-4 hover:underline">
                        {event.actor_name}
                      </a>
                    ) : (
                      event.actor_name
                    )}
                  </TableCell>
                  <TableCell>
                    {event.target_href ? (
                      <a href={event.target_href} className="underline-offset-4 hover:underline">
                        {event.target_name}
                      </a>
                    ) : (
                      event.target_name
                    )}
                  </TableCell>
                  <TableCell className="max-w-xl whitespace-normal">
                    {auditSummary(event.details) || '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager
            page={page}
            pageSize={pageSize}
            total={events.data.total}
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
