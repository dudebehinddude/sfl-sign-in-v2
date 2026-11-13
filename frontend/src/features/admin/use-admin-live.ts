import { useQueryClient, type QueryClient } from '@tanstack/react-query'

import type { LiveMessage } from '@/lib/live/socket'
import { useLiveSocket } from '@/lib/live/use-live-socket'
import { authKeys, publicKeys, staffKeys, staffTopicsFor } from '@/lib/query-keys'

const SESSION_TOPICS = new Set(['users', 'roles', 'permissions', 'all'])
// Mirrors the topics backend/app/events.py fans out to the public scope.
const PUBLIC_TOPICS = new Set([
  'occupancy',
  'users',
  'training-types',
  'trainings',
  'visits',
  'keyholders',
  'all',
])

export function invalidateForMessage(
  client: QueryClient,
  principalId: string,
  message: LiveMessage,
) {
  if (message.type === 'permissions_changed') {
    // The server closes the socket next; the refreshed session decides what stays visible.
    client.invalidateQueries({ queryKey: authKeys.me() })
    client.invalidateQueries({ queryKey: staffKeys(principalId).all })
    return
  }
  if (message.type !== 'invalidate' && message.type !== 'snapshot' && !message.resnapshot) return
  const keys = staffKeys(principalId)
  const topics = message.topics ?? (message.topic ? [message.topic] : ['all'])
  if (topics.some((topic) => SESSION_TOPICS.has(topic))) {
    client.invalidateQueries({ queryKey: authKeys.me() })
  }
  if (message.resnapshot || topics.some((topic) => PUBLIC_TOPICS.has(topic))) {
    client.invalidateQueries({ queryKey: publicKeys.occupancy() })
  }
  const mapped = message.resnapshot ? 'all' : staffTopicsFor(topics)
  if (mapped === 'all') {
    client.invalidateQueries({ queryKey: keys.all })
    return
  }
  for (const topic of mapped) client.invalidateQueries({ queryKey: keys.topic(topic) })
}

/**
 * Subscribes to /ws/admin for the signed-in principal. Messages are
 * invalidation hints; TanStack Query refetches only the affected active
 * queries. A reconnect refetches everything because events may have been
 * missed while disconnected.
 */
export function useAdminLive(principalId: string | null) {
  const client = useQueryClient()
  return useLiveSocket(principalId ? '/ws/admin' : null, {
    onMessage: (message) => {
      if (principalId) invalidateForMessage(client, principalId, message)
    },
    onReconnected: () => {
      if (!principalId) return
      client.invalidateQueries({ queryKey: authKeys.me() })
      client.invalidateQueries({ queryKey: staffKeys(principalId).all })
    },
    onAuthRejected: () => {
      client.invalidateQueries({ queryKey: authKeys.me() })
    },
  })
}
