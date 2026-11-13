import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { staffKeys } from '@/lib/query-keys'
import { StorageBrowser } from './browser'
import { STORAGE_UPLOAD_BYTES, type StorageObject, type StoragePage } from './api'

const staff = vi.hoisted(() => ({ isSuperadmin: true }))
vi.mock('@/features/admin/use-staff', () => ({
  useStaff: () => ({
    user: { id: 'principal' },
    isSuperadmin: staff.isSuperadmin,
    keys: staffKeys('principal'),
  }),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))
afterEach(() => {
  vi.unstubAllGlobals()
  staff.isSuperadmin = true
})

const row: StorageObject = {
  key: 'uploads/a',
  size: 7,
  last_modified: null,
  etag: 'fixture',
  users: [],
}
function page(items = [row], next_cursor: string | null = null): StoragePage {
  return { items, prefix: '', next_cursor, limit: 100, upload_max_bytes: STORAGE_UPLOAD_BYTES }
}
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function show() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <StorageBrowser />
    </QueryClientProvider>,
  )
  return client
}

it('uses server cursors and clears the page when browsing another prefix', async () => {
  const fetcher = vi.fn().mockImplementation((url: string) => {
    const params = new URL(url, 'http://lab.invalid').searchParams
    return Promise.resolve(
      response(params.has('cursor') ? page([{ ...row, key: 'uploads/b' }]) : page([row], row.key)),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  show()
  await screen.findByText('uploads/a')
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  await screen.findByText('uploads/b')
  expect(
    fetcher.mock.calls.some(
      ([path]) => new URL(path, 'http://lab.invalid').searchParams.get('cursor') === row.key,
    ),
  ).toBe(true)
  fireEvent.change(screen.getByLabelText('Path prefix'), { target: { value: 'avatars/' } })
  fireEvent.click(screen.getByRole('button', { name: 'Browse' }))
  await waitFor(() =>
    expect(
      new URL(fetcher.mock.lastCall![0], 'http://lab.invalid').searchParams.get('prefix'),
    ).toBe('avatars/'),
  )
  expect(new URL(fetcher.mock.lastCall![0], 'http://lab.invalid').searchParams.has('cursor')).toBe(
    false,
  )
  expect(await screen.findByRole('button', { name: 'Previous' })).toBeDisabled()
})

it('disables deletion of linked photos and provides the person link', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      response(
        page([
          {
            ...row,
            key: 'avatars/photo.jpg',
            users: [{ id: 'ab', display_name: 'Ada Fixture', href: '/admin/users/ab' }],
          },
        ]),
      ),
    ),
  )
  show()
  expect(await screen.findByRole('link', { name: 'Ada Fixture' })).toHaveAttribute(
    'href',
    '/admin/users/ab',
  )
  expect(screen.getByRole('button', { name: 'Delete avatars/photo.jpg' })).toBeDisabled()
})

it('shows a race-time linked-photo conflict without claiming deletion succeeded', async () => {
  const fetcher = vi.fn().mockImplementation((_url: string, options: RequestInit) =>
    Promise.resolve(
      options.method === 'DELETE'
        ? response(
            {
              detail: {
                message: 'Photo is now in use.',
                users: [{ id: 'ab', display_name: 'Ada Fixture', href: '/admin/users/ab' }],
              },
            },
            409,
          )
        : response(page()),
    ),
  )
  vi.stubGlobal('fetch', fetcher)
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Delete uploads/a' }))
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  expect(await screen.findByText('Photo is now in use.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Ada Fixture' })).toHaveAttribute(
    'href',
    '/admin/users/ab',
  )
  expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
})

it('offers image thumbnails, hover previews and an enlarged preview on click without a generic upload form', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(response(page([{ ...row, key: 'avatars/photo.jpg' }]))),
  )
  show()
  const button = await screen.findByRole('button', { name: 'Preview avatars/photo.jpg' })
  const thumbnail = button.querySelector('img')!
  expect(thumbnail).toHaveAttribute(
    'src',
    '/api/admin/storage/preview?key=avatars%2Fphoto.jpg&size=128',
  )
  fireEvent.mouseEnter(button)
  fireEvent.mouseMove(button)
  expect(await screen.findByAltText('Preview of avatars/photo.jpg')).toHaveAttribute(
    'src',
    '/api/admin/storage/preview?key=avatars%2Fphoto.jpg&size=1024',
  )
  fireEvent.click(button)
  expect(await screen.findByRole('dialog')).toBeVisible()
  expect(screen.getByAltText('Enlarged preview of avatars/photo.jpg')).toBeVisible()
  expect(screen.queryByLabelText('Upload file')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Uploads' })).not.toBeInTheDocument()
})

it('shows a clear failed thumbnail and leaves downloads available for unsupported objects', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      response(
        page([
          { ...row, key: 'avatars/broken.jpg' },
          { ...row, key: 'document.svg' },
        ]),
      ),
    ),
  )
  show()
  const button = await screen.findByRole('button', { name: 'Preview avatars/broken.jpg' })
  fireEvent.error(button.querySelector('img')!)
  expect(screen.getByText('Preview unavailable')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Preview document.svg' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Download' })).toHaveLength(2)
})

it('browses the training-icons prefix from the section shortcut', async () => {
  const fetcher = vi.fn().mockResolvedValue(response(page()))
  vi.stubGlobal('fetch', fetcher)
  show()
  await screen.findByText('uploads/a')
  fireEvent.click(screen.getByRole('button', { name: 'Training icons' }))
  await waitFor(() =>
    expect(
      new URL(fetcher.mock.lastCall![0], 'http://lab.invalid').searchParams.get('prefix'),
    ).toBe('training-icons/'),
  )
})

it('does not fetch storage data for a non-superadmin', async () => {
  staff.isSuperadmin = false
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  show()
  await Promise.resolve()
  expect(fetcher).not.toHaveBeenCalled()
})
