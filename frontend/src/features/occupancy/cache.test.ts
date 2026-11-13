import { QueryClient } from '@tanstack/react-query'
import { expect, it } from 'vitest'
import type { Occupancy } from '@/lib/api/types'
import { publicKeys } from '@/lib/query-keys'
import { applyOccupancySnapshot, newerOccupancy } from './cache'

const snapshot = (revision: number): Occupancy => ({
  revision,
  lab: { is_open: false, keyholder: null },
  occupants: [],
})
it('does not let delayed REST data replace a newer live snapshot', () => {
  const current = snapshot(12)
  expect(newerOccupancy(current, snapshot(11))).toBe(current)
  expect(newerOccupancy(current, snapshot(13)).revision).toBe(13)
})
it('replaces the cache authoritatively on reconnect even after database restore', () => {
  const client = new QueryClient()
  client.setQueryData(publicKeys.occupancy(), snapshot(12))
  applyOccupancySnapshot(client, snapshot(1), true)
  expect(client.getQueryData<Occupancy>(publicKeys.occupancy())?.revision).toBe(1)
  applyOccupancySnapshot(client, snapshot(0))
  expect(client.getQueryData<Occupancy>(publicKeys.occupancy())?.revision).toBe(1)
  client.clear()
})
