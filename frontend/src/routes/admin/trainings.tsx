import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { Pager } from '@/components/pager'
import { SearchInput } from '@/components/search-input'
import { useDebounced } from '@/lib/use-debounced'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Button } from '@/components/ui/button'
import { trainingsQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { RequirePermission } from '@/features/auth/require-permission'
import { AssignTrainingDialog } from '@/features/trainings/assign-dialog'
import { TrainingRecords } from '@/features/trainings/records'
export const Route = createFileRoute('/admin/trainings')({
  component: () => (
    <RequirePermission permission="trainings.read">
      <TrainingsPage />
    </RequirePermission>
  ),
})
function TrainingsPage() {
  const { keys, can } = useStaff()
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const rows = useQuery(trainingsQuery(keys, { page, page_size: pageSize, search: debounced }))
  return (
    <>
      <PageHeader
        title="Trainings"
        actions={can('trainings.write') ? <AssignTrainingDialog trigger={<Button />} /> : null}
      />
      <SearchInput label="Search training or user name" value={search} onChange={value => { setSearch(value); setPage(1) }} />
      {rows.isPending ? (
        <LoadingRows />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => rows.refetch()} />
      ) : !rows.data.items.length ? (
        <EmptyState title="No training records" />
      ) : (
        <>
          <TrainingRecords rows={rows.data.items} canWrite={can('trainings.write')} />
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
    </>
  )
}
