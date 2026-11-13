import { useQuery } from '@tanstack/react-query'
import { useState, type ReactElement } from 'react'
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
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Spinner } from '@/components/ui/spinner'
import { awardTraining, trainingTypesQuery, usersQuery } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import { errorMessage } from '@/lib/api/client'
import { useDebounced } from '@/lib/use-debounced'

export function AssignTrainingDialog({
  trigger,
  user,
}: {
  trigger: ReactElement
  user?: { id: string; display_name: string }
}) {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger}>Assign training</DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-lg">
        {open ? <AssignForm user={user} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  )
}
function AssignForm({
  user,
  onDone,
}: {
  user?: { id: string; display_name: string }
  onDone: () => void
}) {
  const { keys } = useStaff()
  const types = useQuery(trainingTypesQuery(keys))
  const [userId, setUserId] = useState(user?.id ?? '')
  const [search, setSearch] = useState('')
  const debounced = useDebounced(search)
  const people = useQuery({
    ...usersQuery(keys, { page: 1, page_size: 100, search: debounced }),
    enabled: !user && debounced.trim().length > 1,
  })
  const [typeId, setTypeId] = useState('')
  const assign = useStaffMutation({
    mutationFn: awardTraining,
    topics: ['trainings', 'users', 'overview'],
    success: 'Training assigned',
  })
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (userId && typeId)
          assign.mutate({ user_id: userId, training_type_id: typeId }, { onSuccess: onDone })
      }}
    >
      <DialogHeader>
        <DialogTitle>Assign training</DialogTitle>
        <DialogDescription>
          {user ? user.display_name : 'Choose a person and training.'}
        </DialogDescription>
      </DialogHeader>
      <FieldGroup className="gap-4">
        {!user ? (
          <Field>
            <FieldLabel htmlFor="assign-search">Person</FieldLabel>
            <Input
              id="assign-search"
              type="search"
              value={search}
              placeholder="Name or email"
              onChange={(event) => {
                setSearch(event.target.value)
                setUserId('')
              }}
            />
            {people.isError ? <FieldError>{errorMessage(people.error)}</FieldError> : null}
            {people.data ? (
              <NativeSelect
                aria-label="Matching people"
                value={userId}
                onChange={(event) => setUserId(event.target.value)}
              >
                <NativeSelectOption value="">Choose a person</NativeSelectOption>
                {people.data.items.map((person) => (
                  <NativeSelectOption key={person.id} value={person.id}>
                    {person.display_name}
                    {person.email ? ` (${person.email})` : ''}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            ) : (
              <FieldDescription>Search by at least two characters.</FieldDescription>
            )}
          </Field>
        ) : null}
        <Field>
          <FieldLabel htmlFor="assign-type">Training</FieldLabel>
          <NativeSelect
            id="assign-type"
            required
            value={typeId}
            onChange={(event) => setTypeId(event.target.value)}
          >
            <NativeSelectOption value="">Choose training</NativeSelectOption>
            {types.data
              ?.filter((type) => type.active)
              .map((type) => (
                <NativeSelectOption key={type.id} value={type.id}>
                  {type.name}
                </NativeSelectOption>
              ))}
          </NativeSelect>
          {types.isError ? <FieldError>{errorMessage(types.error)}</FieldError> : null}
        </Field>
        {assign.isError ? <FieldError>{errorMessage(assign.error)}</FieldError> : null}
      </FieldGroup>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={assign.isPending || !userId || !typeId}>
          {assign.isPending ? <Spinner /> : null}Assign training
        </Button>
      </DialogFooter>
    </form>
  )
}
