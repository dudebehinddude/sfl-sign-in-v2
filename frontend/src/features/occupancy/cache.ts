import type { QueryClient } from '@tanstack/react-query'

import type { Occupancy } from '@/lib/api/types'
import { publicKeys } from '@/lib/query-keys'

/**
 * Picks which occupancy snapshot the cache should hold. A late REST response
 * or a delayed message must not replace a newer revision. The first snapshot
 * on a new socket is authoritative even if its revision is lower, because a
 * restored backend may restart its counter.
 */
export function newerOccupancy(
  current: Occupancy | undefined,
  incoming: Occupancy,
  authoritative = false,
): Occupancy {
  if (!current || authoritative) return incoming
  return incoming.revision >= current.revision ? incoming : current
}

export function applyOccupancySnapshot(
  client: QueryClient,
  incoming: Occupancy,
  authoritative = false,
) {
  client.setQueryData<Occupancy>(publicKeys.occupancy(), (current) =>
    newerOccupancy(current, incoming, authoritative),
  )
}
