import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DownloadIcon, FileIcon, ImageOffIcon, RefreshCwIcon, Trash2Icon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Typography } from '@/components/typography'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useStaff } from '@/features/admin/use-staff'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import {
  canPreviewObject,
  deleteObject,
  downloadObject,
  formatStorageSize,
  STORAGE_UPLOAD_BYTES,
  storageConflict,
  storageQuery,
  storagePreviewUrl,
  type StorageObject,
} from './api'

export function StorageBrowser() {
  const { user, keys, isSuperadmin } = useStaff()
  const client = useQueryClient()
  const [prefix, setPrefix] = useState('')
  const [draft, setDraft] = useState('')
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const [limit, setLimit] = useState(100)
  const [previewKey, setPreviewKey] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState(false)
  const [selected, setSelected] = useState<StorageObject | null>(null)
  const query = useQuery({
    ...storageQuery(user?.id ?? 'anonymous', prefix, cursors.at(-1) ?? null, limit),
    enabled: isSuperadmin,
  })
  const invalidate = () => {
    void client.invalidateQueries({ queryKey: keys.topic('storage') })
    void client.invalidateQueries({ queryKey: keys.topic('audit') })
  }
  const browse = (value: string) => {
    setPrefix(value)
    setDraft(value)
    setCursors([null])
  }
  const remove = useMutation({
    mutationFn: deleteObject,
    onSuccess: () => {
      invalidate()
      setSelected(null)
      toast.success('Object deleted')
    },
  })
  const download = useMutation({
    mutationFn: downloadObject,
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.topic('audit') }),
  })
  const uploadLimit = query.data?.upload_max_bytes ?? STORAGE_UPLOAD_BYTES
  const busy = remove.isPending
  const conflict = storageConflict(remove.error)
  const submitPrefix = (event: FormEvent) => {
    event.preventDefault()
    browse(draft)
  }

  return (
    <>
      <PageHeader
        title="Storage"
        actions={
          <Button variant="outline" onClick={() => query.refetch()} disabled={query.isFetching}>
            <RefreshCwIcon />
            Refresh
          </Button>
        }
      />
      <div className="max-w-2xl">
        <form onSubmit={submitPrefix} className="flex min-w-0 flex-col gap-2">
          <Field className="gap-1.5">
            <FieldLabel htmlFor="storage-prefix">Path prefix</FieldLabel>
            <div className="flex min-w-0 gap-2">
              <Input
                id="storage-prefix"
                placeholder="All objects"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={1024}
              />
              <Button type="submit">Browse</Button>
            </div>
          </Field>
          <nav aria-label="Storage locations" className="flex flex-wrap gap-1">
            {[
              ['All objects', ''],
              ['Avatars', 'avatars/'],
              ['Training icons', 'training-icons/'],
            ].map(([label, value]) => (
              <Button
                key={label}
                size="sm"
                variant={prefix === value ? 'secondary' : 'ghost'}
                onClick={() => browse(value)}
              >
                {label}
              </Button>
            ))}
          </nav>
        </form>
      </div>
      {download.isError ? <FieldError>{errorMessage(download.error)}</FieldError> : null}
      {query.isPending ? (
        <LoadingRows />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <>
          {!query.data.items.length ? (
            <EmptyState title="No objects at this prefix" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">Preview</TableHead>
                  <TableHead>Object</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Modified</TableHead>
                  <TableHead>Used by</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.items.map((object) => (
                  <TableRow key={object.key}>
                    <TableCell>
                      <ObjectThumbnail
                        object={object}
                        onOpen={() => {
                          setPreviewError(false)
                          setPreviewKey(object.key)
                        }}
                      />
                    </TableCell>
                    <TableCell className="max-w-100 break-all whitespace-normal font-medium">
                      {object.key}
                    </TableCell>
                    <TableCell className="tabular-nums">{formatStorageSize(object.size)}</TableCell>
                    <TableCell>{formatDateTime(object.last_modified)}</TableCell>
                    <TableCell className="max-w-48 whitespace-normal">
                      {object.users.length ? (
                        <ul>
                          {object.users.map((person) => (
                            <li key={person.id}>
                              <a className="underline underline-offset-4" href={person.href}>
                                {person.display_name}
                              </a>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            download.reset()
                            download.mutate(object.key)
                          }}
                          disabled={download.isPending || object.size > uploadLimit}
                          title={
                            object.size > uploadLimit
                              ? 'Object exceeds the 5 MB download limit'
                              : undefined
                          }
                        >
                          {download.isPending && download.variables === object.key ? (
                            <Spinner />
                          ) : (
                            <DownloadIcon />
                          )}
                          Download
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy || object.users.length > 0}
                          onClick={() => {
                            remove.reset()
                            setSelected(object)
                          }}
                          title={
                            object.users.length
                              ? 'Change the linked person’s photo before deleting it'
                              : undefined
                          }
                          aria-label={`Delete ${object.key}`}
                        >
                          <Trash2Icon />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <nav
            aria-label="Object pagination"
            className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground"
          >
            <span>
              {query.data.items.length} {query.data.items.length === 1 ? 'object' : 'objects'} on
              this page
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-xs">
                Rows
                <NativeSelect
                  value={limit}
                  aria-label="Objects per page"
                  onChange={(event) => {
                    setLimit(Number(event.target.value))
                    setCursors([null])
                  }}
                >
                  {[100, 250, 500, 1000].map((size) => (
                    <NativeSelectOption key={size} value={size}>
                      {size}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </label>
              <Button
                variant="outline"
                size="sm"
                disabled={cursors.length <= 1 || query.isFetching}
                onClick={() => setCursors((value) => value.slice(0, -1))}
              >
                Previous
              </Button>
              <span>Page {cursors.length}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={!query.data.next_cursor || query.isFetching}
                onClick={() => {
                  if (query.data.next_cursor)
                    setCursors((value) => [...value, query.data.next_cursor])
                }}
              >
                Next
              </Button>
            </div>
          </nav>
        </>
      )}
      <Dialog
        open={previewKey !== null}
        onOpenChange={(open) => {
          if (!open) setPreviewKey(null)
        }}
      >
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Image preview</DialogTitle>
            <DialogDescription className="break-all">{previewKey}</DialogDescription>
          </DialogHeader>
          {previewKey ? (
            previewError ? (
              <FieldError>Preview unavailable. You can still download the file.</FieldError>
            ) : (
              <img
                src={storagePreviewUrl(previewKey)}
                alt={`Enlarged preview of ${previewKey}`}
                onError={() => setPreviewError(true)}
                className="mx-auto max-h-[65dvh] max-w-full rounded border bg-white object-contain"
              />
            )
          ) : null}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={download.isPending}
              onClick={() => {
                if (previewKey) download.mutate(previewKey)
              }}
            >
              <DownloadIcon />
              Download
            </Button>
            <Button onClick={() => setPreviewKey(null)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setSelected(null)
        }}
      >
        <DialogContent
          showCloseButton={!remove.isPending}
          className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg"
        >
          <DialogHeader>
            <DialogTitle>Delete object?</DialogTitle>
            <DialogDescription className="break-all">{selected?.key}</DialogDescription>
          </DialogHeader>
          <Typography variant="body">This permanently deletes the file.</Typography>
          {remove.isError ? (
            <div className="flex flex-col gap-2">
              <FieldError>{conflict?.message ?? errorMessage(remove.error)}</FieldError>
              {conflict?.users.map((person) => (
                <a
                  className="text-sm underline underline-offset-4"
                  key={person.id}
                  href={person.href}
                >
                  {person.display_name}
                </a>
              ))}
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="outline" disabled={remove.isPending} onClick={() => setSelected(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending || conflict !== null}
              onClick={() => {
                if (selected) remove.mutate(selected.key)
              }}
            >
              {remove.isPending ? <Spinner /> : null}Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function ObjectThumbnail({ object, onOpen }: { object: StorageObject; onOpen: () => void }) {
  const [failed, setFailed] = useState(false)
  if (!canPreviewObject(object))
    return <FileIcon aria-label="File" className="size-6 text-muted-foreground" />
  if (failed)
    return (
      <span className="inline-flex max-w-24 items-center gap-1 text-xs text-muted-foreground">
        <ImageOffIcon className="size-4 shrink-0" />
        Preview unavailable
      </span>
    )
  return (
    <Tooltip>
      <TooltipTrigger
        type="button"
        aria-label={`Preview ${object.key}`}
        onClick={onOpen}
        className="inline-flex size-12 items-center justify-center overflow-hidden rounded border bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <img
          src={storagePreviewUrl(object.key, 128)}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          className="size-full object-contain"
        />
      </TooltipTrigger>
      <TooltipContent
        side="right"
        className="max-w-[min(20rem,80vw)] bg-background p-2 text-foreground shadow-lg ring-1 ring-border"
      >
        <img
          src={storagePreviewUrl(object.key)}
          alt={`Preview of ${object.key}`}
          onError={() => setFailed(true)}
          className="max-h-64 max-w-full rounded bg-white object-contain"
        />
      </TooltipContent>
    </Tooltip>
  )
}
