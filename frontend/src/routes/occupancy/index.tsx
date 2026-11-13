import { useQuery } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { SearchIcon, UsersIcon, WifiOffIcon } from 'lucide-react'
import { useState } from 'react'

import { isStale } from '@/lib/live/socket'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { SiteHeader } from '@/components/site-header'
import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { occupancyQuery, publicTrainingTypesQuery } from '@/features/occupancy/api'
import { filterOccupants, trainingCounts, type OccupantFilter } from '@/features/occupancy/filter'
import { usePublicLive } from '@/features/occupancy/use-public-live'
import { OccupantTable } from './_components/occupant-table'
import { TrainingFilter } from './_components/training-filter'

export const Route = createFileRoute('/occupancy/')({
  component: OccupancyPage,
})

function OccupancyPage() {
  const status = usePublicLive()
  const occupancy = useQuery(occupancyQuery)
  const catalog = useQuery(publicTrainingTypesQuery)
  const [filter, setFilter] = useState<OccupantFilter>({
    search: '',
    trainingTypeId: null,
  })

  return (
    <div className="min-h-svh min-w-0">
      <SiteHeader />
      <main className="mx-auto flex min-w-0 max-w-6xl flex-col gap-4 px-3 py-4 sm:px-4 sm:py-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <Typography variant="h1">In the lab</Typography>
            {occupancy.data ? (
              <Typography variant="muted">
                {occupancy.data.lab.is_open
                  ? `Keyholder: ${occupancy.data.lab.keyholder?.display_name ?? 'unknown'}`
                  : 'The lab is closed'}
              </Typography>
            ) : null}
          </div>
        </div>

        {isStale(status) && occupancy.data ? (
          <Alert>
            <WifiOffIcon />
            <AlertTitle>Reconnecting to the lab server</AlertTitle>
            <AlertDescription>
              This list may be out of date until the connection comes back.
            </AlertDescription>
          </Alert>
        ) : null}

        {occupancy.isPending ? (
          <LoadingRows rows={6} label="Loading who is in the lab" />
        ) : occupancy.isError ? (
          <ErrorState error={occupancy.error} onRetry={() => occupancy.refetch()} />
        ) : (
          <div className="grid min-w-0 items-start gap-4 sm:grid-cols-[14rem_minmax(0,1fr)] lg:grid-cols-[16rem_minmax(0,1fr)]">
            <aside aria-label="Training filters" className="min-w-0">
              <TrainingFilter
                counts={trainingCounts(occupancy.data.occupants, filter, catalog.data?.items)}
                filter={filter}
                onChange={setFilter}
              />
            </aside>
            <div className="flex min-w-0 flex-col gap-3">
              <InputGroup className="h-11">
                <InputGroupAddon>
                  <SearchIcon />
                </InputGroupAddon>
                <InputGroupInput
                  type="search"
                  placeholder="Search by name"
                  aria-label="Search by name"
                  value={filter.search}
                  onChange={(event) => setFilter({ ...filter, search: event.target.value })}
                />
              </InputGroup>
              <Results occupancyData={occupancy.data.occupants} filter={filter} />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function Results({
  occupancyData,
  filter,
}: {
  occupancyData: Parameters<typeof filterOccupants>[0]
  filter: OccupantFilter
}) {
  if (!occupancyData.length) {
    return (
      <EmptyState
        icon={<UsersIcon />}
        title="Nobody is signed in"
        description="People appear here as soon as they tap in at the station."
      />
    )
  }
  const visible = filterOccupants(occupancyData, filter)
  return (
    <div className="flex flex-col gap-2">
      <Typography variant="small" role="status" aria-live="polite">
        Showing {visible.length} of {occupancyData.length}{' '}
        {occupancyData.length === 1 ? 'person' : 'people'}
      </Typography>
      {visible.length ? (
        <OccupantTable occupants={visible} />
      ) : (
        <EmptyState
          title="Nobody matches these filters"
          description="Clear the search or pick another training."
        />
      )}
    </div>
  )
}
