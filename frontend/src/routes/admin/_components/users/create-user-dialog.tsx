import { useNavigate } from '@tanstack/react-router'
import { PlusIcon } from 'lucide-react'
import { useState } from 'react'

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
import { createUser } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import { normalizeIdentifier } from '@/features/kiosk/machine'
import { isUniversityEmail, UNIVERSITY_EMAIL_MESSAGE } from '@/lib/university-email'
import { errorMessage } from '@/lib/api/client'
import type { AccessLevel } from '@/lib/api/types'
import { ACCESS_LEVELS, ACCESS_LEVEL_LABEL } from '@/lib/levels'

const EMPTY = {
  first_name: '',
  last_name: '',
  email: '',
  identifier: '',
  space_level: 0 as AccessLevel,
  keyholder_priority: '-1',
}

export function CreateUserDialog() {
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>
        <PlusIcon data-icon="inline-start" />
        Add person
      </DialogTrigger>
      <DialogContent className="max-h-[calc(100svh-2rem)] overflow-y-auto sm:max-w-lg">
        {open ? <CreateUserForm onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  )
}

function CreateUserForm({ onDone }: { onDone: () => void }) {
  const { isAdmin } = useStaff()
  const navigate = useNavigate()
  const [fields, setFields] = useState(EMPTY)
  const [touched, setTouched] = useState(false)
  const identifier = normalizeIdentifier(fields.identifier)
  const priority = Number(fields.keyholder_priority)
  const priorityValid =
    fields.keyholder_priority.trim() !== '' && Number.isInteger(priority) && priority >= -1
  const emailValid = !fields.email.trim() || isUniversityEmail(fields.email)

  const create = useStaffMutation({
    mutationFn: createUser,
    topics: ['users', 'overview'],
    success: (user) => `Added ${user.display_name}`,
  })

  const set = (key: keyof typeof EMPTY) => (event: { target: { value: string } }) =>
    setFields((current) => ({ ...current, [key]: event.target.value }))

  return (
    <form
      className="flex flex-col gap-6"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        setTouched(true)
        if (
          !identifier ||
          !fields.first_name.trim() ||
          !fields.last_name.trim() ||
          !priorityValid ||
          !emailValid
        )
          return
        create.mutate(
          {
            first_name: fields.first_name.trim(),
            last_name: fields.last_name.trim(),
            email: fields.email.trim() || null,
            identifier,
            space_level: isAdmin ? (Number(fields.space_level) as AccessLevel) : 0,
            keyholder_priority: isAdmin ? priority : -1,
          },
          {
            onSuccess: (user) => {
              onDone()
              void navigate({ to: '/admin/users/$userId', params: { userId: user.id } })
            },
          },
        )
      }}
    >
      <DialogHeader>
        <DialogTitle>Add a person</DialogTitle>
        <DialogDescription>Register without creating a visit.</DialogDescription>
      </DialogHeader>
      <FieldGroup className="gap-4">
        <div className="flex flex-col gap-4">
          <Field data-invalid={(touched && !fields.first_name.trim()) || undefined}>
            <FieldLabel htmlFor="new-first">First name</FieldLabel>
            <Input
              id="new-first"
              required
              maxLength={100}
              value={fields.first_name}
              onChange={set('first_name')}
            />
          </Field>
          <Field data-invalid={(touched && !fields.last_name.trim()) || undefined}>
            <FieldLabel htmlFor="new-last">Last name</FieldLabel>
            <Input
              id="new-last"
              required
              maxLength={100}
              value={fields.last_name}
              onChange={set('last_name')}
            />
          </Field>
        </div>
        <Field data-invalid={(touched && !identifier) || undefined}>
          <FieldLabel htmlFor="new-identifier">Student or card ID</FieldLabel>
          <Input
            id="new-identifier"
            required
            autoComplete="off"
            inputMode="text"
            value={fields.identifier}
            onChange={set('identifier')}
            aria-invalid={(touched && !identifier) || undefined}
          />
          {touched && !identifier ? (
            <FieldError>
              Enter the nine-digit student ID or a lab ID of 3 to 64 letters, digits, : _ or -.
            </FieldError>
          ) : (
            <FieldDescription>The ID cannot be changed after it is saved.</FieldDescription>
          )}
        </Field>
        <Field>
          <FieldLabel htmlFor="new-email">University email (optional)</FieldLabel>
          <Input
            id="new-email"
            type="email"
            maxLength={254}
            value={fields.email}
            onChange={set('email')}
            aria-invalid={!emailValid || undefined}
          />
          {!emailValid ? <FieldError>{UNIVERSITY_EMAIL_MESSAGE}</FieldError> : null}
        </Field>
        {isAdmin ? (
          <div className="flex flex-col gap-4">
            <Field>
              <FieldLabel htmlFor="new-access">Lab access</FieldLabel>
              <NativeSelect
                id="new-access"
                value={fields.space_level}
                onChange={set('space_level')}
              >
                {ACCESS_LEVELS.map((level) => (
                  <NativeSelectOption key={level} value={level}>
                    {ACCESS_LEVEL_LABEL[level]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
            <Field data-invalid={!priorityValid || undefined}>
              <FieldLabel htmlFor="new-priority">Keyholder priority</FieldLabel>
              <Input
                id="new-priority"
                type="number"
                min={-1}
                step={1}
                value={fields.keyholder_priority}
                onChange={set('keyholder_priority')}
              />
              <FieldDescription>-1 means never prompted to take over.</FieldDescription>
            </Field>
          </div>
        ) : null}
        {create.isError ? <FieldError>{errorMessage(create.error)}</FieldError> : null}
      </FieldGroup>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? <Spinner /> : null}
          Add person
        </Button>
      </DialogFooter>
    </form>
  )
}
