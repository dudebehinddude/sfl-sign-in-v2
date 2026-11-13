import { afterEach, expect, it, vi } from 'vitest'
import { ApiError, setCsrfToken } from '@/lib/api/client'
import { staffKeys } from '@/lib/query-keys'
import {
  deleteObject,
  formatStorageSize,
  canPreviewObject,
  storagePreviewUrl,
  storageConflict,
  storageDownloadUrl,
  storageQuery,
} from './api'

afterEach(() => {
  vi.unstubAllGlobals()
  setCsrfToken(null)
})

it('scopes lists to the principal and URL-encodes the real key and cursor', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] })))
  vi.stubGlobal('fetch', fetcher)
  const query = storageQuery('person-a', 'uploads/a & b/', 'uploads/a & b/item', 100)
  expect(query.queryKey).toEqual(
    staffKeys('person-a').topic('storage', 'uploads/a & b/', 'uploads/a & b/item', 100),
  )
  const controller = new AbortController()
  await query.queryFn!({ signal: controller.signal } as never)
  const [path, options] = fetcher.mock.calls[0]
  const parsed = new URL(path, 'http://lab.invalid')
  expect(parsed.pathname).toBe('/api/admin/storage/objects')
  expect(parsed.searchParams.get('prefix')).toBe('uploads/a & b/')
  expect(parsed.searchParams.get('cursor')).toBe('uploads/a & b/item')
  expect(options.credentials).toBe('same-origin')
  expect(storageDownloadUrl('uploads/a?b#c')).toBe(
    '/api/admin/storage/object?key=uploads%2Fa%3Fb%23c',
  )
})

it('previews only bounded known raster files and keeps preview/download URLs same-origin', () => {
  expect(canPreviewObject({ key: 'avatars/a.JPG', size: 20 })).toBe(true)
  expect(canPreviewObject({ key: 'training-icons/a.png', size: 20 })).toBe(true)
  expect(canPreviewObject({ key: 'unsafe.svg', size: 20 })).toBe(false)
  expect(canPreviewObject({ key: 'unsafe.html', size: 20 })).toBe(false)
  expect(canPreviewObject({ key: 'large.png', size: 5 * 1024 * 1024 + 1 })).toBe(false)
  expect(storagePreviewUrl('avatars/a?b.png', 128)).toBe(
    '/api/admin/storage/preview?key=avatars%2Fa%3Fb.png&size=128',
  )
})

it('deletes through the authenticated API with CSRF', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetcher)
  setCsrfToken('fixture-csrf')
  await deleteObject('avatars/a & b')
  expect(fetcher.mock.calls[0][0]).toContain('key=avatars%2Fa+%26+b')
  expect(fetcher.mock.calls[0][1].method).toBe('DELETE')
  expect(fetcher.mock.calls[0][1].headers['X-CSRF-Token']).toBe('fixture-csrf')
})

it('keeps only person links from a deletion conflict', () => {
  const error = new ApiError(
    409,
    {
      message: 'Photo is in use.',
      users: [
        { id: 'ab', display_name: 'Ada', href: '/admin/users/ab' },
        { id: 'cd', display_name: 'Unsafe', href: 'https://elsewhere.invalid' },
      ],
    },
    'Request failed',
  )
  expect(storageConflict(error)).toEqual({
    message: 'Photo is in use.',
    users: [{ id: 'ab', display_name: 'Ada', href: '/admin/users/ab' }],
  })
  expect(storageConflict(new ApiError(503, {}, 'Unavailable'))).toBeNull()
  expect(formatStorageSize(42)).toBe('42 B')
  expect(formatStorageSize(1536)).toBe('1.5 KB')
})
