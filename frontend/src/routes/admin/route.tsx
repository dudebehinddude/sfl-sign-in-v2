import { Outlet, createFileRoute, redirect } from '@tanstack/react-router'
import { ShieldAlertIcon } from 'lucide-react'

import { LiveStatusBadge } from '@/components/live-status'
import { EmptyState, ErrorState } from '@/components/query-state'
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import { Spinner } from '@/components/ui/spinner'
import { useAdminLive } from '@/features/admin/use-admin-live'
import { canOpenAdmin } from '@/features/auth/nav'
import { meQuery, useSession } from '@/features/auth/session'
import { AdminSidebar } from './_components/admin-sidebar'

export const Route = createFileRoute('/admin')({
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData(meQuery)
    if (!session) throw redirect({ to: '/login', search: { redirect: location.href } })
  },
  pendingComponent: () => (
    <div className="flex min-h-svh items-center justify-center">
      <Spinner className="size-8" aria-label="Checking your session" />
    </div>
  ),
  errorComponent: ({ error, reset }) => (
    <div className="mx-auto max-w-xl p-6">
      <ErrorState error={error} onRetry={reset} title="Could not check your session" />
    </div>
  ),
  component: AdminLayout,
})

function AdminLayout() {
  const { user } = useSession()
  const status = useAdminLive(user && canOpenAdmin(user) ? user.id : null)

  if (!user) return null
  if (!canOpenAdmin(user)) {
    return (
      <main className="mx-auto flex min-h-svh max-w-xl items-center p-6">
        <EmptyState
          icon={<ShieldAlertIcon />}
          title="Your account has no staff permissions"
          description="You are logged in, but no staff role is assigned. Ask an administrator for access."
        />
      </main>
    )
  }

  return (
    <SidebarProvider>
      <AdminSidebar user={user} />
      <SidebarInset>
        <div className="flex min-w-0 w-full flex-col gap-4 p-4 md:p-5">
          <div className="md:hidden">
            <SidebarTrigger aria-label="Open navigation" />
          </div>
          <LiveStatusBadge status={status} />
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
