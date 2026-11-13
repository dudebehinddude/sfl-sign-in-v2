import type { LiveStatus } from '@/lib/live/socket'

export function LiveStatusBadge({ status }: { status: LiveStatus }) {
  if (status === 'live' || status === 'connecting') return null
  return <span role="status" className="text-xs text-destructive">{status === 'reconnecting' ? 'Reconnecting…' : 'Connection lost'}</span>
}
