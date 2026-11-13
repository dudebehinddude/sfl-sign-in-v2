import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileUpIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { applyUserImport, previewUserImport } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { errorMessage } from '@/lib/api/client'
import type { ImportPreview, ImportRowStatus } from '@/lib/api/types'

const MAX_BYTES = 1_000_000

const STATUS_LABEL: Record<ImportRowStatus, string> = {
  new: 'New',
  existing: 'Already registered',
  conflict: 'Conflict',
  invalid: 'Invalid',
}

const STATUS_VARIANT: Record<ImportRowStatus, 'secondary' | 'outline' | 'destructive'> = {
  new: 'secondary',
  existing: 'outline',
  conflict: 'destructive',
  invalid: 'destructive',
}

export function ImportUsersDialog() {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" />}>
        <FileUpIcon data-icon="inline-start" />
        Import CSV
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-3xl">
        {open ? <ImportForm onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  )
}

export function ImportForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient()
  const { keys } = useStaff()
  const [csv, setCsv] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)
  // The preview belongs to the exact text it was computed from.
  const [preview, setPreview] = useState<{ csv: string; result: ImportPreview } | null>(null)
  const current = preview?.csv === csv ? preview.result : null

  const check = useMutation({
    mutationFn: (text: string) => previewUserImport(text),
    onSuccess: (result, text) => setPreview({ csv: text, result }),
  })
  const apply = useMutation({
    mutationFn: ({ text, fingerprint }: { text: string; fingerprint: string }) =>
      applyUserImport(text, fingerprint),
    onSuccess: (result) => {
      toast.success(result.message)
      client.invalidateQueries({ queryKey: keys.topic('users') })
      client.invalidateQueries({ queryKey: keys.topic('overview') })
      onDone()
    },
  })

  const readFile = async (file: File | undefined) => {
    setFileError(null)
    if (!file) return
    if (file.size > MAX_BYTES) {
      setFileError('That file is larger than 1 MB. Split it into smaller files.')
      return
    }
    setCsv(await file.text())
  }

  return (
    <div className="flex flex-col gap-6">
      <DialogHeader>
        <DialogTitle>Import people from CSV</DialogTitle>
        <DialogDescription>
          Preview before importing. Existing people are not changed; no visits are created.
        </DialogDescription>
      </DialogHeader>

      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="import-file">CSV file</FieldLabel>
          <Input
            id="import-file"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => void readFile(event.target.files?.[0])}
          />
          {fileError ? <FieldError>{fileError}</FieldError> : null}
        </Field>
        <Field>
          <FieldLabel htmlFor="import-text">Or paste the CSV</FieldLabel>
          <FieldDescription>
            Required: identifier, first_name, last_name. Optional: university email.
          </FieldDescription>
          <Textarea
            id="import-text"
            rows={6}
            className="font-mono text-xs"
            spellCheck={false}
            placeholder={
              'identifier,first_name,last_name,email\n800123456,Ada,Lovelace,alovelace@charlotte.edu'
            }
            value={csv}
            onChange={(event) => setCsv(event.target.value)}
          />
          {preview && !current ? (
            <FieldDescription>The text changed. Preview it again before applying.</FieldDescription>
          ) : null}
        </Field>
        {check.isError ? <FieldError>{errorMessage(check.error)}</FieldError> : null}
      </FieldGroup>

      {current ? <PreviewResult preview={current} /> : null}

      {apply.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Nothing was imported</AlertTitle>
          <AlertDescription>
            {errorMessage(apply.error)} Preview the file again to see what changed.
          </AlertDescription>
        </Alert>
      ) : null}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!csv.trim() || check.isPending}
          onClick={() => check.mutate(csv)}
        >
          {check.isPending ? <Spinner /> : null}
          Preview
        </Button>
        <Button
          type="button"
          disabled={!current?.can_apply || apply.isPending}
          onClick={() => current && apply.mutate({ text: csv, fingerprint: current.fingerprint })}
        >
          {apply.isPending ? <Spinner /> : null}
          {current
            ? `Create ${current.summary.new} ${current.summary.new === 1 ? 'person' : 'people'}`
            : 'Apply'}
        </Button>
      </DialogFooter>
    </div>
  )
}

function PreviewResult({ preview }: { preview: ImportPreview }) {
  const { summary } = preview
  const problems = preview.rows.filter(
    (row) => row.status === 'conflict' || row.status === 'invalid',
  )
  return (
    <section aria-label="Import preview" className="flex flex-col gap-3">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Count label="Rows" value={summary.total} />
        <Count label="New" value={summary.new} />
        <Count label="Already registered" value={summary.existing} />
        <Count label="Conflicts" value={summary.conflict} />
        <Count label="Invalid" value={summary.invalid} />
      </dl>
      {preview.ignored_columns.length ? (
        <Typography variant="muted">
          Ignored columns: {preview.ignored_columns.join(', ')}
        </Typography>
      ) : null}
      {preview.can_apply ? null : (
        <Alert variant="destructive">
          <AlertTitle>This file cannot be applied yet</AlertTitle>
          <AlertDescription>
            {problems.length
              ? 'Fix the conflicting or invalid rows below, then preview again.'
              : 'There is nobody new to create.'}
          </AlertDescription>
        </Alert>
      )}
      <div className="max-h-72 overflow-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Row</TableHead>
              <TableHead>ID</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...problems, ...preview.rows.filter((row) => !problems.includes(row))].map((row) => (
              <TableRow key={row.row_number}>
                <TableCell className="tabular-nums">{row.row_number}</TableCell>
                <TableCell className="font-mono text-xs">{row.identifier}</TableCell>
                <TableCell>
                  {row.first_name} {row.last_name}
                </TableCell>
                <TableCell>{row.email ?? ''}</TableCell>
                <TableCell className="whitespace-normal">
                  <div className="flex flex-col gap-1">
                    <Badge variant={STATUS_VARIANT[row.status]}>{STATUS_LABEL[row.status]}</Badge>
                    {row.message ? (
                      <span className="text-xs text-muted-foreground">{row.message}</span>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col rounded-lg border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-heading text-2xl font-semibold tabular-nums">{value}</dd>
    </div>
  )
}
