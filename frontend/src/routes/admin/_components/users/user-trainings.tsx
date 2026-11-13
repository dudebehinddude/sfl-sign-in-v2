import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Pager } from '@/components/pager'
import { Typography } from '@/components/typography'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Button } from '@/components/ui/button'
import { trainingsQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { AssignTrainingDialog } from '@/features/trainings/assign-dialog'
import { TrainingRecords } from '@/features/trainings/records'
import type { AdminUser } from '@/lib/api/types'
export function UserTrainings({ user }: { user: AdminUser }) {
  const { keys, can } = useStaff()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const rows = useQuery(trainingsQuery(keys, { page, page_size: pageSize, user_id: user.id }))
  return (
    <section className="flex flex-col gap-3 border-t py-5">
      <div className="flex items-center justify-between gap-3">
        <Typography variant="h2">Trainings</Typography>
        {can('trainings.write') ? <AssignTrainingDialog user={user} trigger={<Button />} /> : null}
      </div>
      {rows.isPending ? (
        <LoadingRows rows={3} />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      ) : !rows.data.items.length ? (
        <EmptyState title="No training records" />
      ) : (
        <>
          <TrainingRecords
            rows={rows.data.items}
            canWrite={can('trainings.write')}
            showPerson={false}
          />
          <Pager
            page={page}
            pageSize={pageSize}
            total={rows.data.total}
            onPage={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPage(1)
            }}
          />
        </>
      )}
    </section>
  )
}
