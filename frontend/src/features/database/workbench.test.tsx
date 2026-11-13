import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { NetworkError, api } from '@/lib/api/client'
import { DatabasePage } from './workbench'
import type { DatabaseCatalog, SqlResult } from './data'

const { session, editorCommand } = vi.hoisted(() => ({ session: vi.fn(), editorCommand: { run: undefined as undefined | ((sql: string) => void) } }))
vi.mock('@/features/auth/session', () => ({ useSession: session }))
vi.mock('@/lib/api/client', async original => ({ ...(await original<typeof import('@/lib/api/client')>()), api: vi.fn() }))
vi.mock('./sql-editor', () => ({ default: ({ value, onChange, disabled, onRun }: { value: string; onChange: (value: string) => void; disabled: boolean; onRun: (sql: string) => void }) => { editorCommand.run = onRun; return <textarea aria-label="SQL query" value={value} disabled={disabled} onChange={event => onChange(event.target.value)} /> } }))

const catalog: DatabaseCatalog = { tables: [{ schema: 'public', name: 'users', columns: [{ name: 'id', type: 'uuid', nullable: false, primary_key: true }] }] }
const readResult: SqlResult = { columns: ['value'], rows: [[null], ['']], row_count: 2, truncated: false, duration_ms: 4, transaction_status: 'read_only' }
function previewResult(): SqlResult {
  return { ...readResult, columns: ['first_name'], rows: [['Changed']], row_count: 1, transaction_status: 'preview', preview_id: 'preview-one', expires_at: new Date(Date.now() + 90_000).toISOString(), changes: [{ before: { id: 'row-1', first_name: 'Original' }, after: { id: 'row-1', first_name: 'Changed' } }] }
}
function account(role: 'superadmin' | 'admin' | 'operator') {
  session.mockReturnValue({ query: { isPending: false, isError: false }, user: { id: role, role }, can: (permission: string) => permission === 'database.read' ? role !== 'operator' : permission === 'database.write' && role === 'superadmin' })
}
let client: QueryClient
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  account('superadmin')
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path.endsWith('/tables')) return catalog
    if (path.endsWith('/rows')) return { columns: ['id'], rows: [], total: 0, page: 1, page_size: 100, truncated: false }
    if (path.endsWith('/query')) return options?.body && 'sql' in options.body && String(options.body.sql).startsWith('UPDATE') ? previewResult() : readResult
    if (path.endsWith('/commit')) return { transaction_status: 'committed', row_count: 1 }
    if (path.endsWith('/rollback')) return { transaction_status: 'rolled_back' }
    throw new Error(`Unexpected route ${path}`)
  })
})
afterEach(() => { cleanup(); client.clear(); vi.clearAllMocks() })
function mount() { render(<QueryClientProvider client={client}><DatabasePage /></QueryClientProvider>) }
async function openEditor() { fireEvent.click(await screen.findByRole('tab', { name: 'SQL editor' })); return screen.findByRole('textbox', { name: 'SQL query' }) }
async function stageWrite() {
  const editor = await openEditor()
  fireEvent.change(editor, { target: { value: "UPDATE users SET first_name='Changed' WHERE id='row-1'" } })
  fireEvent.click(screen.getByRole('button', { name: 'Preview SQL Ctrl+Enter' }))
  await screen.findByRole('region', { name: 'SQL change preview' })
}

it('does not request database data for an operator', () => {
  account('operator'); mount()
  expect(screen.getByText('Database access is unavailable for this account.')).toBeDefined()
  expect(api).not.toHaveBeenCalled()
})
it('runs SELECT directly for admin without a mode picker or write dialog', async () => {
  account('admin'); mount(); await openEditor()
  expect(screen.queryByLabelText('Execution mode')).toBeNull()
  expect(screen.queryByText('Ctrl+Enter to run. Writes open a preview first.')).toBeNull()
  expect(screen.getByText('Ctrl+Enter').tagName).toBe('KBD')
  fireEvent.click(screen.getByRole('button', { name: 'Preview SQL Ctrl+Enter' }))
  expect(await screen.findByLabelText('Database null value')).toBeDefined()
  expect(screen.getByLabelText('Empty string')).toBeDefined()
  expect(screen.queryByRole('alertdialog')).toBeNull()
  expect(api).toHaveBeenCalledWith('/api/admin/database/query', expect.objectContaining({ body: { sql: expect.stringContaining('SELECT') } }))
})
it('shows before/after without committing until the separate button is clicked', async () => {
  mount(); await stageWrite()
  expect(screen.getByText('Original')).toBeDefined()
  expect(screen.getByText('Changed')).toBeDefined()
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false)
  expect((screen.getByRole('textbox', { name: 'SQL query' }) as HTMLTextAreaElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Commit changes' }))
  await screen.findByText(/Committed\./)
  expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/query'))).toHaveLength(1)
  expect(api).toHaveBeenCalledWith('/api/admin/database/preview/preview-one/commit', { method: 'POST' })
})
it('rolls back the pending preview without rerunning SQL', async () => {
  mount(); await stageWrite()
  fireEvent.click(screen.getByRole('button', { name: 'Roll back' }))
  await waitFor(() => expect(screen.queryByRole('region', { name: 'SQL change preview' })).toBeNull())
  expect(api).toHaveBeenCalledWith('/api/admin/database/preview/preview-one/rollback', { method: 'POST' })
  expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/query'))).toHaveLength(1)
})
it('does not replay a commit with an unknown result', async () => {
  const original = vi.mocked(api).getMockImplementation()!
  vi.mocked(api).mockImplementation((path, options) => path.endsWith('/commit') ? Promise.reject(new NetworkError('response lost')) : original(path, options))
  mount(); await stageWrite(); fireEvent.click(screen.getByRole('button', { name: 'Commit changes' }))
  await screen.findByText('Commit result is unknown')
  expect((screen.getByRole('button', { name: 'Commit changes' }) as HTMLButtonElement).disabled).toBe(true)
  expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/commit'))).toHaveLength(1)
})
it('lets an expired preview close without another write request', async () => {
  const original = vi.mocked(api).getMockImplementation()!
  vi.mocked(api).mockImplementation((path, options) => path.endsWith('/query') ? Promise.resolve({ ...previewResult(), expires_at: new Date(0).toISOString() }) : original(path, options))
  mount(); await stageWrite()
  await screen.findByText('Preview expired. No changes were saved.')
  fireEvent.click(screen.getByRole('button', { name: 'Close preview' }))
  expect(screen.queryByRole('region', { name: 'SQL change preview' })).toBeNull()
  expect(vi.mocked(api).mock.calls.some(([path]) => path.endsWith('/commit'))).toBe(false)
})


it('preserves an unknown commit outcome after the preview timer expires', async () => {
  const original = vi.mocked(api).getMockImplementation()!
  vi.mocked(api).mockImplementation((path, options) => path.endsWith('/commit') ? Promise.reject(new NetworkError('response lost')) : original(path, options))
  mount(); await stageWrite(); fireEvent.click(screen.getByRole('button', { name: 'Commit changes' }))
  await screen.findByText('Commit result is unknown')
  const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 91_000)
  try {
    await screen.findByRole('button', { name: 'Close preview' }, { timeout: 2500 })
    expect(screen.queryByText('Preview expired. No changes were saved.')).toBeNull()
    expect(screen.getByText('Commit result is unknown. Check the table.')).toBeDefined()
    expect((screen.getByRole('button', { name: 'Commit changes' }) as HTMLButtonElement).disabled).toBe(true)
    expect(vi.mocked(api).mock.calls.filter(([path]) => path.endsWith('/commit'))).toHaveLength(1)
  } finally { clock.mockRestore() }
})


it('runs the current Monaco model value when its shortcut fires before React state catches up', async () => {
  mount(); await openEditor()
  await act(async () => editorCommand.run?.('SELECT 42 AS current_model;'))
  await waitFor(() => expect(api).toHaveBeenCalledWith('/api/admin/database/query', expect.objectContaining({ body: { sql: 'SELECT 42 AS current_model;' } })))
})
