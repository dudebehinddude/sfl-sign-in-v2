import { createFileRoute } from '@tanstack/react-router'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { useSession } from '@/features/auth/session'
import { StorageBrowser } from '@/features/storage/browser'

export const Route = createFileRoute('/admin/storage')({ component: StoragePage })

function StoragePage() {
  const { query, isSuperadmin } = useSession()
  if (query.isPending) return <LoadingRows />
  if (query.isError) return <ErrorState error={query.error} />
  if (!isSuperadmin) return <EmptyState title="Only superadmins can manage storage" />
  return <StorageBrowser />
}
