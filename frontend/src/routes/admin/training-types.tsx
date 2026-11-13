import { useMutation, useQuery } from '@tanstack/react-query'
import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useRef, useState } from 'react'
import { PageHeader } from '@/components/page-header'
import { TrainingIcon } from '@/components/training-badge'
import { Pager } from '@/components/pager'
import { SearchInput } from '@/components/search-input'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { createTrainingType, patchTrainingType, trainingTypesQuery, uploadTrainingIcon } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import { RequirePermission } from '@/features/auth/require-permission'
import { CanvasQuizFields } from '@/features/canvas/quiz-fields'
import { errorMessage } from '@/lib/api/client'
import type { TrainingType } from '@/lib/api/types'

export const Route = createFileRoute('/admin/training-types')({
  validateSearch: (search: Record<string, unknown>): { training?: string } =>
    typeof search.training === 'string' ? { training: search.training } : {},
  component: () => (
    <RequirePermission permission="trainings.read">
      <TrainingTypesPage />
    </RequirePermission>
  ),
})
function TrainingTypesPage() {
  const { keys, can, isAdmin } = useStaff()
  const types = useQuery(trainingTypesQuery(keys))
  const selected = Route.useSearch().training
  const navigate = useNavigate({ from: '/admin/training-types' })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const filteredTypes = types.data?.filter(item => item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) ?? []
  const [pageSize, setPageSize] = useState(100)
  const canDefine = isAdmin && can('trainings.write')
  const type = types.data?.find((item) => item.id === selected)
  const close = () => {
    void navigate({ search: {} })
  }
  return (
    <>
      <PageHeader
        title="Training types"
        actions={
          canDefine ? (
            <Link
              to="/admin/training-types"
              search={{ training: 'new' }}
              className={buttonVariants()}
            >
              Add training type
            </Link>
          ) : null
        }
      />
      <SearchInput label="Search trainings" value={search} onChange={value => { setSearch(value); setPage(1) }} />
      {types.isPending ? (
        <LoadingRows />
      ) : types.isError ? (
        <ErrorState error={types.error} onRetry={() => types.refetch()} />
      ) : !filteredTypes.length ? (
        <EmptyState title="No matching training types" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Training</TableHead>
                <TableHead>Icon</TableHead>
                <TableHead>Canvas quiz</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredTypes.slice((page - 1) * pageSize, page * pageSize).map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-medium">
                    {canDefine ? (
                      <Link
                        to="/admin/training-types"
                        search={{ training: item.id }}
                        className="underline-offset-4 hover:underline"
                      >
                        {item.name}
                      </Link>
                    ) : (
                      item.name
                    )}
                  </TableCell>
                  <TableCell>
                    <TrainingIcon name={item.name} iconKey={item.icon_key} />
                  </TableCell>
                  <TableCell>{item.canvas_assignment_id ? 'Connected' : 'None'}</TableCell>
                  <TableCell>
                    <Badge variant={item.active ? 'secondary' : 'outline'}>
                      {item.active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager
            page={page}
            pageSize={pageSize}
            total={filteredTypes.length}
            onPage={setPage}
            onPageSizeChange={(size) => {
              setPageSize(size)
              setPage(1)
            }}
          />
        </>
      )}
      <Dialog
        open={Boolean(selected) && canDefine}
        onOpenChange={(open) => {
          if (!open) close()
        }}
      >
        <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-lg">
          {selected === 'new' || type ? (
            <TrainingTypeForm key={type?.id ?? 'new'} type={type} onDone={close} />
          ) : types.isPending ? (
            <LoadingRows />
          ) : (
            <ErrorState error={new Error('Training type not found.')} />
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
export function TrainingTypeForm({ type, onDone }: { type?: TrainingType; onDone: () => void }) {
  const [name, setName] = useState(type?.name ?? '')
  const [iconKey, setIconKey] = useState(type?.icon_key ?? '')
  const iconInput = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: uploadTrainingIcon,
    retry: false,
    onSuccess: result => setIconKey(result.icon_key),
  })
  const [active, setActive] = useState(type?.active ?? true)
  const [displayOrder, setDisplayOrder] = useState(String(type?.display_order ?? 100))
  const [assignmentId, setAssignmentId] = useState(type?.canvas_assignment_id ?? '')
  const [minimumScore, setMinimumScore] = useState(type?.canvas_minimum_score?.toString() ?? '')
  const scoreValid =
    !assignmentId ||
    !minimumScore.trim() ||
    (Number.isFinite(Number(minimumScore)) && Number(minimumScore) >= 0)
  const orderValid = /^\d+$/.test(displayOrder) && Number.isSafeInteger(Number(displayOrder)) && Number(displayOrder) <= 2147483647
  const valid = name.trim().length > 0 && scoreValid && orderValid && Boolean(iconKey) && !upload.isPending && !upload.isError
  const input = {
    name: name.trim(),
    icon_key: iconKey,
    display_order: Number(displayOrder),
    active,
    canvas_assignment_id: assignmentId || null,
    canvas_minimum_score: assignmentId && minimumScore.trim() ? Number(minimumScore) : null,
  }
  const save = useStaffMutation({
    mutationFn: () => (type ? patchTrainingType(type.id, input) : createTrainingType(input)),
    topics: ['training-types', 'trainings', 'overview'],
    success: 'Training type saved',
  })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (valid) save.mutate(undefined, { onSuccess: onDone })
      }}
    >
      <DialogHeader>
        <DialogTitle>{type ? 'Edit training type' : 'Add training type'}</DialogTitle>
        <DialogDescription>Badge and Canvas settings.</DialogDescription>
      </DialogHeader>
      <FieldGroup className="gap-4">
        <Field>
          <FieldLabel htmlFor="training-name">Name</FieldLabel>
          <Input
            id="training-name"
            required
            maxLength={100}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="training-icon">Icon</FieldLabel>
          <div className="flex items-center gap-3">
            {iconKey ? <TrainingIcon key={iconKey} name={name.trim() || 'Current training icon'} iconKey={iconKey} /> : null}
            <Input
              ref={iconInput}
              id="training-icon"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={upload.isPending || save.isPending}
              aria-describedby="training-icon-help"
              aria-invalid={upload.isError || undefined}
              onChange={event => {
                const file = event.target.files?.[0]
                if (file) upload.mutate(file)
              }}
            />
          </div>
          <p className="text-xs text-muted-foreground" id="training-icon-help">PNG, JPEG or WebP, up to 2 MiB.</p>
          {upload.isPending ? <p role="status" className="flex items-center gap-2 text-sm"><Spinner />Uploading icon…</p> : null}
          {upload.isSuccess ? <p role="status" className="text-sm text-muted-foreground">Icon uploaded. Save to use it for this training.</p> : null}
          {upload.isError ? <>
            <FieldError>{errorMessage(upload.error)}</FieldError>
            <Button type="button" variant="outline" className="self-start" onClick={() => {
              upload.reset()
              if (iconInput.current) iconInput.current.value = ''
            }}>{iconKey ? 'Keep current icon' : 'Clear file'}</Button>
          </> : null}
        </Field>
        <Field>
          <FieldLabel htmlFor="training-order">Display order</FieldLabel>
          <Input id="training-order" type="number" min={0} max={2147483647} step={1} required value={displayOrder} onChange={event => setDisplayOrder(event.target.value)} />
          <p className="text-xs text-muted-foreground">Lower numbers appear first, including on stickers.</p>
          {!orderValid ? <FieldError>Enter a whole number from 0 to 2147483647.</FieldError> : null}
        </Field>
        <CanvasQuizFields
          assignmentId={assignmentId}
          onAssignmentId={setAssignmentId}
          minimumScore={minimumScore}
          onMinimumScore={setMinimumScore}
        />
        {!scoreValid ? <FieldError>Enter a nonnegative score or leave blank.</FieldError> : null}
        <Field orientation="horizontal">
          <Switch id="training-active" checked={active} onCheckedChange={setActive} />
          <FieldLabel htmlFor="training-active">Active</FieldLabel>
        </Field>
        {save.isError ? <FieldError>{errorMessage(save.error)}</FieldError> : null}
      </FieldGroup>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={!valid || save.isPending}>
          {save.isPending ? <Spinner /> : null}Save
        </Button>
      </DialogFooter>
    </form>
  )
}
