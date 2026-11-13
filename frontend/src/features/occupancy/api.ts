import { queryOptions } from '@tanstack/react-query'

import { api } from '@/lib/api/client'
import type { Occupancy, PublicTrainingType } from '@/lib/api/types'
import { publicKeys } from '@/lib/query-keys'
import { newerOccupancy } from './cache'

export const occupancyQuery = queryOptions({
  queryKey: publicKeys.occupancy(),
  queryFn: async ({ client, signal }) => {
    const fresh = await api<Occupancy>('/api/public/occupancy', { signal })
    return newerOccupancy(client.getQueryData<Occupancy>(publicKeys.occupancy()), fresh)
  },
  // The live socket keeps this current; REST is only the first load and recovery path.
  staleTime: Infinity,
})

export const publicTrainingTypesQuery = queryOptions({
  queryKey: publicKeys.trainingTypes(),
  queryFn: ({ signal }) =>
    api<{ items: PublicTrainingType[] }>('/api/public/training-types', { signal }),
  staleTime: 5 * 60_000,
  retry: false,
})
