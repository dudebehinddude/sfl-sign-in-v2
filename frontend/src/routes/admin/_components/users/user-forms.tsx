import { useState, type FormEvent, type ReactNode } from 'react'
import { Typography } from '@/components/typography'
import { Button } from '@/components/ui/button'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { patchUser, setUserPassword, setUserRole } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { useStaffMutation } from '@/features/admin/use-staff-mutation'
import type { AccessLevel, AdminUser, Role, UserPatchInput } from '@/lib/api/types'
import { ACCESS_LEVELS, ACCESS_LEVEL_LABEL, ROLES, ROLE_LABEL } from '@/lib/levels'
import { isUniversityEmail, UNIVERSITY_EMAIL_MESSAGE } from '@/lib/university-email'

function Section({
  title,
  description,
  children,
  footer,
  onSubmit,
}: {
  title: string
  description?: string
  children: ReactNode
  footer: ReactNode
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4 border-t py-5">
      <header>
        <Typography variant="h2">{title}</Typography>
        {description ? <Typography variant="small">{description}</Typography> : null}
      </header>
      <div className="max-w-xl">{children}</div>
      <div>{footer}</div>
    </form>
  )
}
function useUserPatch(user: AdminUser) {
  return useStaffMutation({
    mutationFn: (input: UserPatchInput) => patchUser(user.id, input),
    topics: ['users', 'overview'],
    success: 'Saved',
  })
}

export function IdentityForm({ user }: { user: AdminUser }) {
  const [fields, setFields] = useState({
    first_name: user.first_name,
    last_name: user.last_name,
    email: user.email ?? '',
  })
  const save = useUserPatch(user)
  const dirty =
    fields.first_name !== user.first_name ||
    fields.last_name !== user.last_name ||
    fields.email !== (user.email ?? '')
  const emailValid = !fields.email.trim() || isUniversityEmail(fields.email)
  const valid = Boolean(fields.first_name.trim() && fields.last_name.trim()) && emailValid
  const set = (key: keyof typeof fields) => (event: { target: { value: string } }) =>
    setFields((current) => ({ ...current, [key]: event.target.value }))
  return (
    <Section
      title="Account details"
      onSubmit={(event) => {
        event.preventDefault()
        if (valid)
          save.mutate({
            first_name: fields.first_name.trim(),
            last_name: fields.last_name.trim(),
            email: fields.email.trim() || null,
          })
      }}
      footer={
        <Button type="submit" disabled={!dirty || !valid || save.isPending}>
          {save.isPending ? <Spinner /> : null}Save details
        </Button>
      }
    >
      <FieldGroup className="gap-4">
        <Field>
          <FieldLabel htmlFor="user-first">First name</FieldLabel>
          <Input
            id="user-first"
            required
            maxLength={100}
            value={fields.first_name}
            onChange={set('first_name')}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="user-last">Last name</FieldLabel>
          <Input
            id="user-last"
            required
            maxLength={100}
            value={fields.last_name}
            onChange={set('last_name')}
          />
        </Field>
        <Field data-invalid={!emailValid || undefined}>
          <FieldLabel htmlFor="user-email">University email</FieldLabel>
          <Input
            id="user-email"
            type="email"
            maxLength={254}
            value={fields.email}
            onChange={set('email')}
            aria-invalid={!emailValid || undefined}
          />
          {!emailValid ? <FieldError>{UNIVERSITY_EMAIL_MESSAGE}</FieldError> : null}
        </Field>
      </FieldGroup>
    </Section>
  )
}
export function AccessForm({ user }: { user: AdminUser }) {
  const [level, setLevel] = useState<AccessLevel>(user.space_level)
  const [priority, setPriority] = useState(String(user.keyholder_priority))
  const [active, setActive] = useState(user.active)
  const save = useUserPatch(user)
  const parsed = Number(priority)
  const valid = priority.trim() !== '' && Number.isInteger(parsed) && parsed >= -1
  const dirty =
    level !== user.space_level || parsed !== user.keyholder_priority || active !== user.active
  return (
    <Section
      title="Lab access"
      onSubmit={(event) => {
        event.preventDefault()
        if (!valid) return
        const input: UserPatchInput = {}
        if (level !== user.space_level) input.space_level = level
        if (parsed !== user.keyholder_priority) input.keyholder_priority = parsed
        if (active !== user.active) input.active = active
        save.mutate(input)
      }}
      footer={
        <Button type="submit" disabled={!dirty || !valid || save.isPending}>
          {save.isPending ? <Spinner /> : null}Save lab access
        </Button>
      }
    >
      <FieldGroup className="gap-4">
        <Field>
          <FieldLabel htmlFor="user-access">Space level</FieldLabel>
          <NativeSelect
            id="user-access"
            value={level}
            onChange={(event) => setLevel(Number(event.target.value) as AccessLevel)}
          >
            {ACCESS_LEVELS.map((option) => (
              <NativeSelectOption key={option} value={option}>
                {ACCESS_LEVEL_LABEL[option]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <Field data-invalid={!valid || undefined}>
          <FieldLabel htmlFor="user-priority">Keyholder priority</FieldLabel>
          <Input
            id="user-priority"
            type="number"
            min={-1}
            step={1}
            value={priority}
            onChange={(event) => setPriority(event.target.value)}
            aria-invalid={!valid || undefined}
          />
          {valid ? (
            <FieldDescription>
              Higher priority offers a keyholder takeover. Minimum -1.
            </FieldDescription>
          ) : (
            <FieldError>Enter a whole number of -1 or more.</FieldError>
          )}
        </Field>
        <Field orientation="horizontal">
          <Switch id="user-active" checked={active} onCheckedChange={setActive} />
          <FieldLabel htmlFor="user-active">Account active</FieldLabel>
        </Field>
      </FieldGroup>
    </Section>
  )
}
export function RoleForm({ user }: { user: AdminUser }) {
  const { isSuperadmin } = useStaff()
  const [role, setRole] = useState<Role | null>(user.role)
  const save = useStaffMutation({
    mutationFn: (value: Role | null) => setUserRole(user.id, value),
    topics: ['users', 'roles', 'overview'],
    success: 'Role saved',
  })
  const choices = ROLES.filter((value) => isSuperadmin || value !== 'superadmin')
  return (
    <Section
      title="Staff role"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate(role)
      }}
      footer={
        <Button type="submit" disabled={role === user.role || save.isPending}>
          {save.isPending ? <Spinner /> : null}Save role
        </Button>
      }
    >
      <Field>
        <FieldLabel htmlFor="user-role">Role</FieldLabel>
        <NativeSelect
          id="user-role"
          value={role ?? ''}
          onChange={(event) => setRole((event.target.value || null) as Role | null)}
        >
          <NativeSelectOption value="">No staff access</NativeSelectOption>
          {choices.map((value) => (
            <NativeSelectOption key={value} value={value}>
              {ROLE_LABEL[value]}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <FieldDescription>
          {role === 'operator'
            ? 'Read lab records, assign trainings and edit basic account details.'
            : role === 'admin'
              ? 'Manage lab records and non-superadmin roles. SQL is read-only.'
              : role === 'superadmin'
                ? 'Full application, storage and SQL control.'
                : 'Can sign in at the kiosk without staff dashboard access.'}
        </FieldDescription>
      </Field>
    </Section>
  )
}
export function PasswordForm({ user }: { user: AdminUser }) {
  const [password, setPassword] = useState('')
  const save = useStaffMutation({
    mutationFn: (value: string) => setUserPassword(user.id, value),
    topics: ['users', 'audit'],
    success: 'Password set; previous sessions signed out.',
  })
  return (
    <Section
      title="Set staff password"
      onSubmit={(event) => {
        event.preventDefault()
        if (password.length >= 12) save.mutate(password, { onSuccess: () => setPassword('') })
      }}
      footer={
        <Button type="submit" disabled={password.length < 12 || save.isPending}>
          {save.isPending ? <Spinner /> : null}Set password
        </Button>
      }
    >
      <Field>
        <FieldLabel htmlFor="user-password">New password</FieldLabel>
        <Input
          id="user-password"
          type="password"
          autoComplete="new-password"
          minLength={12}
          maxLength={1024}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <FieldDescription>At least 12 characters.</FieldDescription>
      </Field>
    </Section>
  )
}
