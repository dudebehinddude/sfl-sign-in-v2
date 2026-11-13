import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { revokeTraining } from '@/features/admin/api'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import type { Training } from '@/lib/api/types'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'

export function TrainingRecords({
  rows,
  canWrite,
  showPerson = true,
}: {
  rows: Training[]
  canWrite: boolean
  showPerson?: boolean
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Training</TableHead>
          {showPerson ? <TableHead>Person</TableHead> : null}
          <TableHead>Source</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Completed</TableHead>
          <TableHead>Expires</TableHead>
          <TableHead>Canvas result</TableHead>
          {canWrite ? <TableHead>Actions</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.id}>
            <TableCell>
              <Link
                to="/admin/training-types"
                search={{ training: row.training_type_id }}
                className="font-medium underline-offset-4 hover:underline"
              >
                {row.training_type_name}
              </Link>
            </TableCell>
            {showPerson ? (
              <TableCell>
                {row.user_href ? (
                  <a href={row.user_href} className="underline-offset-4 hover:underline">
                    {row.user_name}
                  </a>
                ) : (
                  row.user_name
                )}
              </TableCell>
            ) : null}
            <TableCell>{row.source === 'canvas' ? 'Canvas' : 'Manual'}</TableCell>
            <TableCell>
              <Badge variant={row.has_training ? 'secondary' : 'outline'}>
                {row.has_training ? 'Trained' : 'Not trained'}
              </Badge>
              {row.revoked_at ? (
                <span className="ml-2 text-xs text-muted-foreground">Revoked</span>
              ) : null}
            </TableCell>
            <TableCell>{formatDateTime(row.completed_at ?? row.awarded_at)}</TableCell>
            <TableCell>{row.expires_at ? formatDateTime(row.expires_at) : '—'}</TableCell>
            <TableCell>
              {row.source === 'canvas' ? (
                <details>
                  <summary className="cursor-pointer">
                    {row.score === null ? (row.grade ?? 'No score') : `Score ${row.score}`}
                  </summary>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 py-2 text-xs">
                    <dt>Grade</dt>
                    <dd>{row.grade ?? '—'}</dd>
                    <dt>Passed</dt>
                    <dd>{row.passed === null ? 'Unknown' : row.passed ? 'Yes' : 'No'}</dd>
                    <dt>Attempt</dt>
                    <dd>{row.attempt ?? '—'}</dd>
                    <dt>Fetched</dt>
                    <dd>{formatDateTime(row.fetched_at)}</dd>
                  </dl>
                </details>
              ) : (
                '—'
              )}
            </TableCell>
            {canWrite ? (
              <TableCell>
                {row.has_training && !row.revoked_at ? <RevokeTraining row={row} /> : null}
              </TableCell>
            ) : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
function RevokeTraining({ row }: { row: Training }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const revoke = useStaffMutation({
    mutationFn: () => revokeTraining(row.id, reason.trim()),
    topics: ['trainings', 'users', 'overview'],
    success: 'Training revoked',
  })
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>Revoke</DialogTrigger>
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (reason.trim().length >= 3)
              revoke.mutate(undefined, { onSuccess: () => setOpen(false) })
          }}
        >
          <DialogHeader>
            <DialogTitle>Revoke {row.training_type_name}?</DialogTitle>
            <DialogDescription>{row.user_name}</DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor={`revoke-${row.id}`}>Reason</FieldLabel>
            <Textarea
              id={`revoke-${row.id}`}
              required
              minLength={3}
              maxLength={500}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </Field>
          {revoke.isError ? <FieldError>{errorMessage(revoke.error)}</FieldError> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={reason.trim().length < 3 || revoke.isPending}
            >
              Revoke training
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
