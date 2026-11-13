import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DownloadIcon, PlayIcon, RefreshCwIcon } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { ErrorState, LoadingRows } from '@/components/query-state'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSession } from '@/features/auth/session'
import { ApiError, NetworkError, api, isStatus } from '@/lib/api/client'
import { staffKeys } from '@/lib/query-keys'
import { downloadResult, sqlForTable, type DatabaseCatalog, type DatabaseTable, type SqlResult } from './data'
import { ResultGrid } from './result-grid'
import { TableBrowser } from './table-browser'

const SqlEditor = lazy(() => import('./sql-editor'))
const DATABASE = '/api/admin/database'
interface PreviewResult { transaction_status: 'committed' | 'rolled_back'; row_count: number }

export function DatabasePage() {
  const { query, user, can } = useSession()
  if (query.isPending) return <LoadingRows label="Checking access" />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  if (!user || !can('database.read')) return <ErrorState error={new ApiError(403, null, 'Database access is unavailable for this account.')} />
  return <DatabaseWorkbench key={user.id} principalId={user.id} canWrite={can('database.write')} />
}

function DatabaseWorkbench({ principalId, canWrite }: { principalId: string; canWrite: boolean }) {
  const client = useQueryClient()
  const [tab, setTab] = useState('tables')
  const [sqlText, setSqlText] = useState('SELECT id, first_name, last_name FROM public.users LIMIT 100;')
  const [execution, setExecution] = useState<SqlResult | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const preview = execution?.transaction_status === 'preview' ? execution : null
  const activePreview = useRef<string | undefined>(undefined)
  const [now, setNow] = useState(() => Date.now())
  const secondsLeft = preview?.expires_at ? Math.max(0, Math.ceil((Date.parse(preview.expires_at) - now) / 1000)) : 0
  const expired = Boolean(preview?.expires_at && !secondsLeft)
  useEffect(() => {
    activePreview.current = preview?.preview_id
    if (!preview) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [preview])
  useEffect(() => () => {
    if (activePreview.current) void api(`${DATABASE}/preview/${activePreview.current}/rollback`, { method: 'POST' }).catch(() => undefined)
  }, [])
  const catalog = useQuery({
    queryKey: staffKeys(principalId).topic('database', 'catalog'),
    queryFn: ({ signal }) => api<DatabaseCatalog>(`${DATABASE}/tables`, { signal }),
    retry: (count, error) => !isStatus(error, 400, 401, 403, 503) && count < 1,
  })
  const run = useMutation({
    mutationFn: (sql: string) => api<SqlResult>(`${DATABASE}/query`, { method: 'POST', body: { sql } }),
    onMutate: () => { setExecution(null); setNotice(null); finish.reset() },
    onSuccess: result => { setNow(Date.now()); setExecution(result) },
  })
  const finish = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'commit' | 'rollback' }) => api<PreviewResult>(`${DATABASE}/preview/${id}/${action}`, { method: 'POST' }),
    onSuccess: (result, input) => {
      activePreview.current = undefined
      setExecution(current => input.action === 'commit' && current ? { ...current, ...result, preview_id: undefined, expires_at: undefined } : null)
      if (input.action === 'rollback') setNotice('Rolled back.')
      void client.invalidateQueries({ queryKey: staffKeys(principalId).all })
    },
    onError: error => {
      if (isStatus(error, 404, 410)) {
        activePreview.current = undefined
        setExecution(null)
        setNotice('This preview has ended. Refresh the table before running another write.')
      }
    },
  })
  const busy = run.isPending || finish.isPending
  const uncertainCommit = finish.isError && finish.variables?.action === 'commit' &&
    (finish.error instanceof NetworkError || (finish.error instanceof ApiError && finish.error.status >= 500))
  function execute(value = sqlText) {
    if (!value.trim() || value.length > 64_000 || busy || preview) return
    run.mutate(value)
  }
  function openTable(table: DatabaseTable) {
    if (preview) return
    setSqlText(sqlForTable(table))
    setTab('query')
  }
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader title="Database" actions={<Button size="sm" variant="outline" onClick={() => client.invalidateQueries({ queryKey: staffKeys(principalId).topic('database') })}><RefreshCwIcon />Refresh tables</Button>} />
      {!canWrite ? <p className="text-sm text-muted-foreground">Read-only access.</p> : null}
      {catalog.isPending ? <LoadingRows label="Loading schema" /> : catalog.isError ? <ErrorState error={catalog.error} onRetry={() => catalog.refetch()} /> : (
        <Tabs value={tab} onValueChange={value => setTab(String(value))} className="min-w-0">
          <TabsList><TabsTrigger value="tables">Tables</TabsTrigger><TabsTrigger value="query">SQL editor</TabsTrigger></TabsList>
          <TabsContent value="tables" className="min-w-0">
            <TableBrowser principalId={principalId} tables={catalog.data.tables} onEditQuery={openTable} />
          </TabsContent>
          <TabsContent value="query" className="flex min-w-0 flex-col gap-3">
            <Suspense fallback={<LoadingRows label="Loading editor" />}>
              <SqlEditor value={sqlText} onChange={setSqlText} tables={catalog.data.tables} disabled={busy || Boolean(preview)} onRun={execute} />
            </Suspense>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button disabled={!sqlText.trim() || sqlText.length > 64_000 || busy || Boolean(preview)} onClick={() => execute()}><PlayIcon />{run.isPending ? 'Running…' : 'Preview SQL'}{' '}<Kbd className="bg-primary-foreground/15 text-primary-foreground">Ctrl+Enter</Kbd></Button>
            </div>
            {run.isError ? <ErrorState error={run.error} /> : null}
            {notice ? <p role="status" className="text-sm text-muted-foreground">{notice}</p> : null}
            {preview ? (
              <section className="flex min-w-0 flex-col gap-3 border-t pt-4" aria-label="SQL change preview">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">{preview.row_count} {preview.row_count === 1 ? 'row' : 'rows'} would change</h2>
                    <p className="text-sm text-muted-foreground">{uncertainCommit ? 'Commit result is unknown. Check the table.' : expired ? 'Preview expired. No changes were saved.' : `Not saved. This transaction expires in ${secondsLeft}s.`}</p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" disabled={busy} onClick={() => { if (expired) { activePreview.current = undefined; setExecution(null); finish.reset() } else if (preview.preview_id) finish.mutate({ id: preview.preview_id, action: 'rollback' }) }}>{expired ? 'Close preview' : 'Roll back'}</Button>
                    <Button disabled={!canWrite || busy || expired || !preview.row_count || uncertainCommit} onClick={() => preview.preview_id && finish.mutate({ id: preview.preview_id, action: 'commit' })}>Commit changes</Button>
                  </div>
                </div>
                {finish.isError ? <ErrorState error={finish.error} /> : null}
                {uncertainCommit ? <Alert variant="destructive"><AlertTitle>Commit result is unknown</AlertTitle><AlertDescription>Refresh the table and check the data before running another write.</AlertDescription></Alert> : null}
                <ChangePreview result={preview} />
              </section>
            ) : null}
            {execution && !preview ? (
              <section className="flex min-w-0 flex-col gap-3 border-t pt-4" aria-label="Last completed SQL result">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm">{execution.transaction_status === 'committed' ? 'Committed. ' : ''}{execution.row_count} {execution.row_count === 1 ? 'row' : 'rows'} in {Math.round(execution.duration_ms)} ms{execution.truncated ? ' (limited)' : ''}</p>
                  <Button variant="outline" size="sm" disabled={!execution.columns.length} onClick={() => downloadResult(execution.columns, execution.rows)}><DownloadIcon />Export CSV</Button>
                </div>
                <ResultGrid columns={execution.columns} rows={execution.rows} caption="SQL results" />
              </section>
            ) : null}
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

function ChangePreview({ result }: { result: SqlResult }) {
  const changes = result.changes ?? []
  const names = [...new Set(changes.flatMap(change => Object.keys(change.before ?? change.after ?? {})))]
  const rows = changes.flatMap((change, index) => [
    ...(change.before ? [[`${index + 1} Before`, ...names.map(name => change.before?.[name])]] : []),
    ...(change.after ? [[`${index + 1} After`, ...names.map(name => change.after?.[name])]] : []),
  ])
  if (!changes.length) return <p className="text-sm text-muted-foreground">No rows matched.</p>
  return <ResultGrid columns={['Change', ...names]} rows={rows} caption="Proposed changes" />
}
