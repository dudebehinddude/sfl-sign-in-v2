import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type { Occupancy } from '@/lib/api/types'
import type { LiveSocketOptions } from '@/lib/live/socket'
import { publicKeys } from '@/lib/query-keys'
import { trainingCounts } from './filter'
import { usePublicLive } from './use-public-live'

const live = vi.hoisted(() => ({ handlers: null as LiveSocketOptions | null }))
vi.mock('@/lib/live/use-live-socket', () => ({
  useLiveSocket: (_path: string, handlers: LiveSocketOptions) => {
    live.handlers = handlers
    return 'live'
  },
}))
afterEach(cleanup)

const snapshot = (revision: number): Occupancy => ({
  revision,
  lab: { is_open: false, keyholder: null },
  occupants: [],
})
const oldCatalog = [
  { id: 'orientation', name: 'Orientation', icon_key: 'old-icon' },
  { id: 'laser', name: 'Laser Cutter', icon_key: 'laser-cutter' },
]
const newCatalog = [oldCatalog[1], { ...oldCatalog[0], icon_key: 'uploaded-icon' }]

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(publicKeys.occupancy(), snapshot(10))
  client.setQueryData(publicKeys.trainingTypes(), { items: oldCatalog })
  const fetchCatalog = vi.fn(async () => ({ items: newCatalog }))
  function Sidebar() {
    usePublicLive()
    const catalog = useQuery({
      queryKey: publicKeys.trainingTypes(),
      queryFn: fetchCatalog,
      staleTime: Infinity,
    })
    const counts = trainingCounts([], { search: '', trainingTypeId: null }, catalog.data?.items)
    return (
      <ol>
        {counts.trainings.map((training) => (
          <li key={training.id}>{training.name}:{training.icon_key}</li>
        ))}
      </ol>
    )
  }
  render(<QueryClientProvider client={client}><Sidebar /></QueryClientProvider>)
  return { client, fetchCatalog }
}
function receive(revision: number, firstOfConnection = false) {
  act(() => {
    live.handlers!.onMessage(
      { type: 'snapshot', topic: 'occupancy', data: snapshot(revision) },
      { connectionId: firstOfConnection ? 2 : 1, firstOfConnection },
    )
  })
}

it('refreshes cached sidebar icons and order when a changed public snapshot arrives', async () => {
  const { client, fetchCatalog } = mount()
  expect(fetchCatalog).not.toHaveBeenCalled()
  expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Orientation:old-icon', 'Laser Cutter:laser-cutter'])
  receive(11)
  await waitFor(() => expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Laser Cutter:laser-cutter', 'Orientation:uploaded-icon']))
  expect(fetchCatalog).toHaveBeenCalledTimes(1)
  client.clear()
})

it.each([10, 1])('refreshes the cached catalog on an authoritative reconnect at revision %i', async (revision) => {
  const { client, fetchCatalog } = mount()
  receive(revision, true)
  await waitFor(() => expect(fetchCatalog).toHaveBeenCalledTimes(1))
  expect(client.getQueryData<Occupancy>(publicKeys.occupancy())?.revision).toBe(revision)
  client.clear()
})

it('ignores old or repeated snapshots and refreshes the catalog on invalidation', async () => {
  const { client, fetchCatalog } = mount()
  receive(9)
  receive(10)
  expect(fetchCatalog).not.toHaveBeenCalled()
  act(() => live.handlers!.onMessage({ type: 'invalidate', revision: 11 }, { connectionId: 1, firstOfConnection: false }))
  await waitFor(() => expect(fetchCatalog).toHaveBeenCalledTimes(1))
  client.clear()
})
