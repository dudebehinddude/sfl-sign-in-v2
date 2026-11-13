import { useQuery } from '@tanstack/react-query'
import { Link, createFileRoute } from '@tanstack/react-router'
import { AwardIcon, LayoutDashboardIcon, ScanLineIcon, UsersIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { LiveStatusBadge } from '@/components/live-status'
import { SiteHeader } from '@/components/site-header'
import { Typography } from '@/components/typography'
import { UserAvatar } from '@/components/user-avatar'
import { Skeleton } from '@/components/ui/skeleton'
import { canOpenAdmin } from '@/features/auth/nav'
import { useSession } from '@/features/auth/session'
import { occupancyQuery } from '@/features/occupancy/api'
import { usePublicLive } from '@/features/occupancy/use-public-live'
import { errorMessage } from '@/lib/api/client'

export const Route = createFileRoute('/')({
  component: HomePage,
})

function HomePage() {
  const { user, can } = useSession()
  return (
    <div className="min-h-svh">
      <SiteHeader />
      <main className="mx-auto flex max-w-3xl flex-col gap-10 px-4 py-12">
        <div className="flex flex-col gap-3 text-center">
          <Typography variant="display">Welcome to the Super Fab Lab</Typography>
          <LabSummary />
        </div>
        <nav aria-label="Lab pages" className="grid gap-3 sm:grid-cols-2">
          <HomeLink
            to="/kiosk"
            icon={<ScanLineIcon />}
            title="Go to station"
            detail="Sign in or out with your card"
          />
          <HomeLink
            to="/occupancy"
            icon={<UsersIcon />}
            title="View current users"
            detail="Who is in the lab and their trainings"
          />
          {can('trainings.write') ? (
            <HomeLink
              to="/admin/trainings"
              icon={<AwardIcon />}
              title="Add a training"
              detail="Assign a training"
            />
          ) : null}
          {canOpenAdmin(user) ? (
            <HomeLink
              to="/admin"
              icon={<LayoutDashboardIcon />}
              title="Staff dashboard"
              detail="People, visits and metrics"
            />
          ) : null}
        </nav>
      </main>
    </div>
  )
}

function HomeLink({
  to,
  icon,
  title,
  detail,
}: {
  to: '/kiosk' | '/occupancy' | '/admin' | '/admin/trainings'
  icon: ReactNode
  title: string
  detail: string
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-4 rounded-xl border bg-card p-5 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-6 [&_svg]:text-primary"
    >
      {icon}
      <span className="flex flex-col">
        <span className="font-heading text-lg font-medium">{title}</span>
        <span className="text-sm text-muted-foreground">{detail}</span>
      </span>
    </Link>
  )
}

function LabSummary() {
  const status = usePublicLive()
  const occupancy = useQuery(occupancyQuery)

  if (occupancy.isPending) return <Skeleton className="mx-auto h-7 w-72" />
  if (occupancy.isError) {
    return (
      <Typography variant="muted">
        Live lab status is unavailable: {errorMessage(occupancy.error)}
      </Typography>
    )
  }
  const { lab, occupants } = occupancy.data
  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      {lab.keyholder ? (
        <UserAvatar name={lab.keyholder.display_name} url={lab.keyholder.avatar_url} size="sm" />
      ) : null}
      <Typography variant="lead" as="p">
        {lab.is_open
          ? `Open with ${lab.keyholder?.display_name ?? 'a keyholder'} as keyholder, ${occupants.length} ${occupants.length === 1 ? 'person' : 'people'} in the lab`
          : 'The lab is closed right now'}
      </Typography>
      <LiveStatusBadge status={status} />
    </div>
  )
}
