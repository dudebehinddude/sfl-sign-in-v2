import { expect, it } from 'vitest'
import type { Occupant } from '@/lib/api/types'
import { filterOccupants, trainingCounts } from './filter'

const orientation = {
  training_type_id: 'orientation',
  name: 'Orientation',
  icon_key: 'orientation',
}
const laser = { training_type_id: 'laser', name: 'Laser Cutter', icon_key: 'laser-cutter' }
const people: Occupant[] = [
  { id: 'one', display_name: 'Ada Lovelace', badges: [orientation, laser] },
  { id: 'two', display_name: 'Grace Hopper', badges: [orientation, orientation] },
  { id: 'three', display_name: 'New Visitor', badges: [] },
]

it('filters by person name and completed training without a level taxonomy', () => {
  expect(
    filterOccupants(people, { search: '  ADA ', trainingTypeId: 'laser' }).map((p) => p.id),
  ).toEqual(['one'])
  expect(filterOccupants(people, { search: 'Grace', trainingTypeId: 'laser' })).toEqual([])
  expect(filterOccupants(people, { search: '', trainingTypeId: null })).toHaveLength(3)
})

it('counts each trained person once, includes empty catalog entries, and respects the search', () => {
  const catalog = [
    { id: 'orientation', name: 'Orientation', icon_key: 'orientation' },
    { id: 'waterjet', name: 'Waterjet', icon_key: 'waterjet' },
  ]
  const counts = trainingCounts(people, { search: '', trainingTypeId: 'laser' }, catalog)
  expect(counts.total).toBe(3)
  expect(counts.trainings.find((t) => t.id === 'orientation')?.count).toBe(2)
  expect(counts.trainings.find((t) => t.id === 'waterjet')?.count).toBe(0)
  const filtered = trainingCounts(people, { search: 'Ada', trainingTypeId: null }, catalog)
  expect(filtered.total).toBe(1)
  expect(filtered.trainings.find((t) => t.id === 'orientation')?.count).toBe(1)
})

it('retains the catalog printer-label order and appends unknown badges in stable input order', () => {
  const catalog = [
    { id: 'policies', name: 'Policies and Procedures', icon_key: 'policies' },
    { id: 'orientation', name: 'Orientation', icon_key: 'orientation' },
    { id: 'fdm', name: 'FDM Printing', icon_key: '3d-printer' },
    { id: 'laser', name: 'Laser Cutter', icon_key: 'laser-cutter' },
    { id: 'resin', name: 'Resin Printing', icon_key: 'resin-printer' },
    { id: 'waterjet', name: 'Waterjet', icon_key: 'waterjet' },
  ]
  const extraPeople: Occupant[] = [
    ...people,
    {
      id: 'four',
      display_name: 'Another Visitor',
      badges: [
        { training_type_id: 'unknown-z', name: 'Z training', icon_key: 'z-icon' },
        { training_type_id: 'unknown-a', name: 'A training', icon_key: 'a-icon' },
      ],
    },
  ]
  const result = trainingCounts(extraPeople, { search: '', trainingTypeId: null }, catalog)
  expect(result.trainings.map((training) => training.id)).toEqual([
    'policies',
    'orientation',
    'fdm',
    'laser',
    'resin',
    'waterjet',
    'unknown-z',
    'unknown-a',
  ])
  expect(result.trainings[0]).toEqual({
    id: 'policies',
    name: 'Policies and Procedures',
    icon_key: 'policies',
    count: 0,
  })
  expect(result.trainings.at(-2)?.icon_key).toBe('z-icon')
})

it('uses catalog metadata without renaming or reordering entries from badge evidence', () => {
  const catalog = [
    { id: 'laser', name: 'Z catalog name', icon_key: 'laser-cutter' },
    { id: 'orientation', name: 'A catalog name', icon_key: 'orientation' },
  ]
  const result = trainingCounts(people, { search: 'Ada', trainingTypeId: 'orientation' }, catalog)
  expect(result.trainings).toEqual([
    { id: 'laser', name: 'Z catalog name', icon_key: 'laser-cutter', count: 1 },
    { id: 'orientation', name: 'A catalog name', icon_key: 'orientation', count: 1 },
  ])
})
