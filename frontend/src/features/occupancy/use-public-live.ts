import { useQueryClient } from '@tanstack/react-query'

import type { Occupancy } from '@/lib/api/types'
import { useLiveSocket } from '@/lib/live/use-live-socket'
import { publicKeys } from '@/lib/query-keys'
import { applyOccupancySnapshot } from './cache'

/** Subscribes to /ws/public and keeps the occupancy cache current. */
export function usePublicLive(onRevision?: (revision: number) => void) {
  const client = useQueryClient()
  return useLiveSocket('/ws/public', {
    onMessage: (message, { firstOfConnection }) => {
      if (message.type === 'snapshot' && message.topic === 'occupancy' && message.data) {
        const data = message.data as Occupancy
        const current = client.getQueryData<Occupancy>(publicKeys.occupancy())
        applyOccupancySnapshot(client, data, firstOfConnection)
        if (firstOfConnection || !current || data.revision > current.revision) {
          client.invalidateQueries({ queryKey: publicKeys.trainingTypes() })
        }
        onRevision?.(data.revision)
        return
      }
      if (message.type === 'invalidate' || message.resnapshot) {
        client.invalidateQueries({ queryKey: publicKeys.occupancy() })
        client.invalidateQueries({ queryKey: publicKeys.trainingTypes() })
        if (typeof message.revision === 'number') onRevision?.(message.revision)
      }
    },
  })
}
