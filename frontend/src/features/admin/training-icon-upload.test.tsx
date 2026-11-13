import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { setCsrfToken } from '@/lib/api/client'
import type { TrainingType } from '@/lib/api/types'
import { staffKeys } from '@/lib/query-keys'
import { TrainingTypeForm } from '@/routes/admin/training-types'
import { TRAINING_ICON_MAX_BYTES, uploadTrainingIcon } from './api'

vi.mock('@/features/admin/use-staff', () => ({ useStaff: () => ({ keys: staffKeys('synthetic-admin') }) }))
vi.mock('@/features/canvas/quiz-fields', () => ({ CanvasQuizFields: () => null }))
vi.mock('@/components/training-badge', () => ({
  TrainingIcon: ({ iconKey }: { iconKey: string }) => <span data-testid="icon-preview">{iconKey}</span>,
}))
const iconKey = `training-icons/${'a'.repeat(32)}.png`
const uploaded = { icon_key: iconKey, icon_url: `/media/${iconKey}` }
const clients: QueryClient[] = []
afterEach(() => {
  clients.forEach(client => client.clear())
  clients.length = 0
  vi.unstubAllGlobals()
  setCsrfToken(null)
})
function mount(type?: TrainingType) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  clients.push(client)
  const done = vi.fn()
  render(<QueryClientProvider client={client}><Dialog open><DialogContent>
    <TrainingTypeForm type={type} onDone={done} />
  </DialogContent></Dialog></QueryClientProvider>)
  return done
}
function choose(file = new File(['synthetic PNG bytes'], 'synthetic.png', { type: 'image/png' })) {
  fireEvent.change(screen.getByLabelText('Icon'), { target: { files: [file] } })
}
const existing: TrainingType = {
  id: 'synthetic-training', name: 'Synthetic training', icon_key: 'orientation', active: true,
  display_order: 7, canvas_assignment_id: null, canvas_minimum_score: null,
  canvas_sync_started_at: null, canvas_synced_at: null, canvas_sync_error: null,
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z',
}
it('uploads exactly one multipart file with session CSRF and no JSON Content-Type', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(uploaded)))
  vi.stubGlobal('fetch', fetch)
  setCsrfToken('synthetic-csrf')
  const file = new File(['synthetic JPEG bytes'], 'fixture.jpg', { type: 'image/jpeg' })
  await expect(uploadTrainingIcon(file)).resolves.toEqual(uploaded)
  const [path, options] = fetch.mock.calls[0]
  expect(path).toBe('/api/admin/training-icons')
  expect(options.method).toBe('POST')
  expect(options.body).toBeInstanceOf(FormData)
  expect(options.body.get('file')).toBe(file)
  expect([...options.body.keys()]).toEqual(['file'])
  expect(options.headers['X-CSRF-Token']).toBe('synthetic-csrf')
  expect(options.headers['Content-Type']).toBeUndefined()
})
it('rejects unsupported, empty and oversized files without sending them', async () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  await expect(uploadTrainingIcon(new File(['x'], 'fixture.svg', { type: 'image/svg+xml' }))).rejects.toThrow('PNG, JPEG or WebP')
  await expect(uploadTrainingIcon(new File([], 'fixture.png', { type: 'image/png' }))).rejects.toThrow('2 MiB')
  await expect(uploadTrainingIcon(new File([new Uint8Array(TRAINING_ICON_MAX_BYTES + 1)], 'big.png', { type: 'image/png' }))).rejects.toThrow('2 MiB')
  expect(fetch).not.toHaveBeenCalled()
})
it('rejects arbitrary media paths returned by an invalid upload response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    icon_key: '../private.png', icon_url: 'https://untrusted.invalid/private.png',
  }))))
  await expect(uploadTrainingIcon(new File(['x'], 'fixture.png', { type: 'image/png' }))).rejects.toThrow('invalid icon reference')
})
it('uploads before creating, blocks Save while pending, then saves only the returned key and display order', async () => {
  let resolveUpload!: (value: Response) => void
  const fetch = vi.fn()
    .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveUpload = resolve }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...existing, icon_key: iconKey })))
  vi.stubGlobal('fetch', fetch)
  const done = mount()
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Synthetic new training' } })
  fireEvent.change(screen.getByLabelText('Display order'), { target: { value: '4' } })
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  expect(screen.getByLabelText('Icon')).toHaveAttribute('type', 'file')
  expect(screen.queryByRole('combobox', { name: 'Icon' })).toBeNull()
  choose()
  await screen.findByText('Uploading icon…')
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  expect(fetch).toHaveBeenCalledTimes(1)
  resolveUpload(new Response(JSON.stringify(uploaded)))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled())
  expect(screen.getByTestId('icon-preview')).toHaveTextContent(iconKey)
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(done).toHaveBeenCalledOnce())
  expect(fetch.mock.calls[1][0]).toBe('/api/admin/training-types')
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
    name: 'Synthetic new training', icon_key: iconKey, display_order: 4, active: true,
    canvas_assignment_id: null, canvas_minimum_score: null,
  })
})
it('blocks Save after server upload failure until explicitly keeping the existing icon', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Synthetic storage unavailable' }), { status: 503 }))
  vi.stubGlobal('fetch', fetch)
  mount(existing)
  expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
  choose()
  await screen.findByText('Synthetic storage unavailable')
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  expect(screen.getByTestId('icon-preview')).toHaveTextContent('orientation')
  expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Keep current icon' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled())
  expect(screen.queryByText('Synthetic storage unavailable')).toBeNull()
  expect(screen.getByLabelText('Display order')).toHaveValue(7)
})
it('shows client file errors and keeps new training unsavable after clearing a failed file', async () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  mount()
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Synthetic new training' } })
  choose(new File(['x'], 'fixture.gif', { type: 'image/gif' }))
  await screen.findByText('Choose a PNG, JPEG or WebP image.')
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Clear file' }))
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
})


it('accepts WebP artwork for server-side normalization to PNG', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(uploaded)))
  vi.stubGlobal('fetch', fetch)
  const file = new File(['synthetic WebP bytes'], 'fixture.webp', { type: 'image/webp' })
  await expect(uploadTrainingIcon(file)).resolves.toEqual(uploaded)
  expect(fetch.mock.calls[0][1].body.get('file')).toBe(file)
})
