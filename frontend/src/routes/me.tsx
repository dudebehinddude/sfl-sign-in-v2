import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute, redirect } from '@tanstack/react-router'
import { useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { Pager } from '@/components/pager'
import { EmptyState, ErrorState, LoadingRows } from '@/components/query-state'
import { SiteHeader } from '@/components/site-header'
import { TrainingBadgeList } from '@/components/training-badge'
import { Typography } from '@/components/typography'
import { UserAvatar } from '@/components/user-avatar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { changeOwnPassword, patchProfile, profileQuery, uploadAvatar } from '@/features/admin/api'
import { useStaff } from '@/features/admin/use-staff'
import { meQuery } from '@/features/auth/session'
import { isUniversityEmail, UNIVERSITY_EMAIL_MESSAGE } from '@/lib/university-email'
import { errorMessage } from '@/lib/api/client'
import type { Profile } from '@/lib/api/types'
import { formatDateTime, formatDuration, formatNumber } from '@/lib/format'
import { authKeys } from '@/lib/query-keys'

export const Route = createFileRoute('/me')({
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData(meQuery)
    if (!session) throw redirect({ to: '/login', search: { redirect: location.href } })
  },
  component: MePage,
})

function MePage() {
  const { keys } = useStaff()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const profile = useQuery(profileQuery(keys, { page, page_size: pageSize }))

  return (
    <div className="flex min-h-svh flex-col">
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-none flex-col gap-5 p-6">
        {profile.isPending ? (
          <LoadingRows rows={6} />
        ) : profile.isError ? (
          <ErrorState error={profile.error} onRetry={() => profile.refetch()} />
        ) : (
          <>
            <ProfileSummary profile={profile.data} />
            <div className="flex flex-col">
              <EditProfile key={profile.data.user.updated_at} profile={profile.data} />
              <ChangePassword />
            </div>
            <VisitHistory
              profile={profile.data}
              page={page}
              onPage={setPage}
              pageSize={pageSize}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </>
        )}
      </main>
    </div>
  )
}

function useProfileRefresh() {
  const client = useQueryClient()
  const { keys } = useStaff()
  return () => {
    client.invalidateQueries({ queryKey: keys.topic('profile') })
    client.invalidateQueries({ queryKey: authKeys.me() })
  }
}

function ProfileSummary({ profile }: { profile: Profile }) {
  const { user } = profile
  const refresh = useProfileRefresh()
  const fileRef = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: uploadAvatar,
    onSuccess: () => {
      toast.success('Photo updated')
      refresh()
    },
    onError: (error) => toast.error(errorMessage(error)),
  })

  return (
    <header className="flex flex-wrap items-center justify-between gap-6">
      <div className="flex items-center gap-4">
        <UserAvatar name={user.display_name} url={user.avatar_url} size="lg" />
        <div className="flex flex-col gap-2">
          <Typography variant="h1">{user.display_name}</Typography>
          <TrainingBadgeList badges={user.badges} />
        </div>
      </div>
      <div className="flex flex-col items-start gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png"
          className="sr-only"
          aria-label="Upload a profile photo"
          onChange={(event) => {
            const file = event.target.files?.[0]
            event.target.value = ''
            if (file) upload.mutate(file)
          }}
        />
        <Button
          variant="outline"
          disabled={upload.isPending}
          onClick={() => fileRef.current?.click()}
        >
          {upload.isPending ? <Spinner /> : null}
          {user.avatar_url ? 'Change photo' : 'Add a photo'}
        </Button>
        <Typography variant="small" className="text-muted-foreground">
          JPEG or PNG, up to 2 MB.
        </Typography>
      </div>
      <dl className="grid w-full grid-cols-2 gap-4 sm:w-auto">
        <div>
          <dt className="text-sm text-muted-foreground">Hours in the lab</dt>
          <dd className="font-heading text-2xl font-semibold tabular-nums">
            {formatNumber(profile.total_hours)}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-muted-foreground">Completed visits</dt>
          <dd className="font-heading text-2xl font-semibold tabular-nums">
            {profile.completed_visits}
          </dd>
        </div>
        <Typography variant="small" className="col-span-2 text-muted-foreground">
          Forgotten sign-outs are excluded.
        </Typography>
      </dl>
    </header>
  )
}

function ProfileSection({
  title,
  description,
  children,
  footer,
  onSubmit,
}: {
  title: string
  description: string
  children: ReactNode
  footer: ReactNode
  onSubmit: () => void
}) {
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <section className="flex flex-col gap-4 border-t py-5">
        <header>
          <Typography variant="h2">{title}</Typography>
          <Typography variant="small">{description}</Typography>
        </header>
        <div className="max-w-xl">{children}</div>
        <div>{footer}</div>
      </section>
    </form>
  )
}

function EditProfile({ profile }: { profile: Profile }) {
  const { user } = profile
  const refresh = useProfileRefresh()
  const [fields, setFields] = useState({
    first_name: user.first_name,
    last_name: user.last_name,
    email: user.email ?? '',
  })
  const save = useMutation({
    mutationFn: patchProfile,
    onSuccess: () => {
      toast.success('Profile saved')
      refresh()
    },
  })
  const emailValid = !fields.email.trim() || isUniversityEmail(fields.email)
  const valid = Boolean(fields.first_name.trim() && fields.last_name.trim()) && emailValid
  const dirty =
    fields.first_name !== user.first_name ||
    fields.last_name !== user.last_name ||
    fields.email !== (user.email ?? '')
  const set = (key: keyof typeof fields) => (event: { target: { value: string } }) =>
    setFields((current) => ({ ...current, [key]: event.target.value }))

  return (
    <ProfileSection
      title="Your details"
      description="Name and university email."
      onSubmit={() => {
        if (!valid) return
        const input: { first_name?: string; last_name?: string; email?: string } = {}
        if (fields.first_name !== user.first_name) input.first_name = fields.first_name.trim()
        if (fields.last_name !== user.last_name) input.last_name = fields.last_name.trim()
        if (fields.email !== (user.email ?? '') && fields.email.trim())
          input.email = fields.email.trim()
        save.mutate(input)
      }}
      footer={
        <Button type="submit" disabled={!dirty || !valid || save.isPending}>
          {save.isPending ? <Spinner /> : null}
          Save
        </Button>
      }
    >
      <FieldGroup className="gap-4">
        <div className="flex flex-col gap-4">
          <Field>
            <FieldLabel htmlFor="me-first">First name</FieldLabel>
            <Input
              id="me-first"
              maxLength={100}
              value={fields.first_name}
              onChange={set('first_name')}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="me-last">Last name</FieldLabel>
            <Input
              id="me-last"
              maxLength={100}
              value={fields.last_name}
              onChange={set('last_name')}
            />
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="me-email">Email</FieldLabel>
          <Input
            id="me-email"
            type="email"
            maxLength={254}
            value={fields.email}
            onChange={set('email')}
          />
          {!emailValid ? <FieldError>{UNIVERSITY_EMAIL_MESSAGE}</FieldError> : null}
        </Field>
        {save.isError ? <FieldError>{errorMessage(save.error)}</FieldError> : null}
      </FieldGroup>
    </ProfileSection>
  )
}

function ChangePassword() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const save = useMutation({
    mutationFn: changeOwnPassword,
    onSuccess: () => {
      toast.success('Password changed. Your other sessions were signed out.')
      setCurrent('')
      setNext('')
    },
  })
  const valid = current.length > 0 && next.length >= 12

  return (
    <ProfileSection
      title="Password"
      description="Changing it signs you out everywhere else."
      onSubmit={() => {
        if (valid) save.mutate({ current_password: current, new_password: next })
      }}
      footer={
        <Button type="submit" disabled={!valid || save.isPending}>
          {save.isPending ? <Spinner /> : null}
          Change password
        </Button>
      }
    >
      <FieldGroup className="gap-4">
        <Field>
          <FieldLabel htmlFor="me-current-password">Current password</FieldLabel>
          <Input
            id="me-current-password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="me-new-password">New password</FieldLabel>
          <Input
            id="me-new-password"
            type="password"
            autoComplete="new-password"
            minLength={12}
            maxLength={1024}
            value={next}
            onChange={(event) => setNext(event.target.value)}
          />
          <FieldDescription>At least 12 characters.</FieldDescription>
        </Field>
        {save.isError ? <FieldError>{errorMessage(save.error)}</FieldError> : null}
      </FieldGroup>
    </ProfileSection>
  )
}

function VisitHistory({
  profile,
  page,
  onPage,
  pageSize,
  onPageSizeChange,
}: {
  profile: Profile
  page: number
  onPage: (page: number) => void
  pageSize: number
  onPageSizeChange: (size: number) => void
}) {
  const { visits } = profile
  return (
    <section aria-labelledby="visit-history" className="flex flex-col gap-3">
      <Typography variant="h2" id="visit-history">
        Your visits
      </Typography>
      {visits.items.length === 0 ? (
        <EmptyState title="No visits yet" description="Scan your card at the station to sign in." />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Signed in</TableHead>
                <TableHead>Signed out</TableHead>
                <TableHead>Length</TableHead>
                <TableHead>How it ended</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visits.items.map((visit) => (
                <TableRow key={visit.id}>
                  <TableCell>{formatDateTime(visit.enter_time)}</TableCell>
                  <TableCell>
                    {visit.exit_time ? (
                      formatDateTime(visit.exit_time)
                    ) : (
                      <Badge variant="secondary">In the lab</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {visit.exit_time && !visit.forgot_to_sign_out
                      ? formatDuration(visit.enter_time, visit.exit_time)
                      : ''}
                  </TableCell>
                  <TableCell>
                    {visit.forgot_to_sign_out ? (
                      <Badge variant="destructive">Forgot to sign out</Badge>
                    ) : visit.exit_time ? (
                      'Signed out'
                    ) : (
                      ''
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pager
            page={page}
            pageSize={pageSize}
            total={visits.total}
            onPage={onPage}
            onPageSizeChange={onPageSizeChange}
          />
        </>
      )}
    </section>
  )
}
