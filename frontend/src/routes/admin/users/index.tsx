import { useQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'

import { PageHeader } from '@/components/page-header'
import { Pager } from '@/components/pager'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { SearchInput } from '@/components/search-input'
import { TrainingBadgeList } from '@/components/training-badge'
import { UserAvatar } from '@/components/user-avatar'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { usersQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { RequirePermission } from '@/features/auth/require-permission'
import { ACCESS_LEVEL_LABEL, ROLE_LABEL } from '@/lib/levels'
import { useDebounced } from '@/lib/use-debounced'
import { CreateUserDialog } from '../_components/users/create-user-dialog'
import { ImportUsersDialog } from '../_components/users/import-users-dialog'

export const Route = createFileRoute('/admin/users/')({
  component: () => (
    <RequirePermission permission="users.read">
      <UsersPage />
    </RequirePermission>
  ),
})

function UsersPage() {
  const { keys, can, isAdmin } = useStaff()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const debounced = useDebounced(search)
  const users = useQuery(usersQuery(keys, { page, page_size: pageSize, search: debounced }))

  return (
    <>
      <PageHeader
        title="People"
        actions={
          can('users.write') && isAdmin ? (
            <>
              <ImportUsersDialog />
              <CreateUserDialog />
            </>
          ) : null
        }
      />
      <SearchInput
        label="Search by name, email or ID"
        value={search}
        onChange={(value) => {
          setSearch(value)
          setPage(1)
        }}
      />
      {users.isPending ? (
        <LoadingRows rows={8} />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      ) : users.data.items.length === 0 ? (
        <EmptyState
          title="Nobody found"
          description={debounced ? 'Try a different search.' : 'Nobody has registered yet.'}
        />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Lab access</TableHead>
                <TableHead>Keyholder priority</TableHead>
                <TableHead>Staff role</TableHead>
                <TableHead>Trainings</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.items.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <Link
                      to="/admin/users/$userId"
                      params={{ userId: user.id }}
                      className="flex items-center gap-3 font-medium hover:underline"
                    >
                      <UserAvatar name={user.display_name} url={user.avatar_url} />
                      <span className="flex flex-col">
                        <span>{user.display_name}</span>
                        {user.email ? (
                          <span className="text-xs font-normal text-muted-foreground">
                            {user.email}
                          </span>
                        ) : null}
                      </span>
                      {user.active ? null : <Badge variant="destructive">Inactive</Badge>}
                    </Link>
                  </TableCell>
                  <TableCell>{ACCESS_LEVEL_LABEL[user.space_level] ?? user.space_level}</TableCell>
                  <TableCell className="tabular-nums">{user.keyholder_priority}</TableCell>
                  <TableCell>{user.role ? ROLE_LABEL[user.role] : '—'}</TableCell>
                  <TableCell className="whitespace-normal">
                    <TrainingBadgeList badges={user.badges} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager
            page={page}
            pageSize={pageSize}
            total={users.data.total}
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
