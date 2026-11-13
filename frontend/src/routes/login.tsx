import { Link, createFileRoute, redirect, useRouter } from '@tanstack/react-router'
import { useState } from 'react'

import { SiteHeader } from '@/components/site-header'
import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { meQuery, useLogin } from '@/features/auth/session'
import { errorMessage, isStatus } from '@/lib/api/client'

function safeRedirect(value: unknown): string {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')
    ? value
    : '/admin'
}

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } =>
    typeof search.redirect === 'string' ? { redirect: search.redirect } : {},
  beforeLoad: async ({ context, search }) => {
    const session = await context.queryClient.ensureQueryData(meQuery).catch(() => null)
    if (session) throw redirect({ href: safeRedirect(search.redirect) })
  },
  component: LoginPage,
})

function loginErrorTitle(error: unknown) {
  if (isStatus(error, 401, 400)) return 'Those credentials did not work'
  if (isStatus(error, 429)) return 'Too many attempts'
  if (isStatus(error, 503)) return 'Staff login is not configured on this server'
  return 'Could not log in'
}

function LoginPage() {
  const to = safeRedirect(Route.useSearch().redirect)
  const router = useRouter()
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')

  return (
    <div className="min-h-svh">
      <SiteHeader />
      <main className="mx-auto flex max-w-md flex-col gap-6 px-4 py-12">
        <Card>
          <form
            className="flex flex-col gap-6"
            onSubmit={(event) => {
              event.preventDefault()
              login.mutate(
                { identifier: identifier.trim(), password },
                { onSuccess: () => router.history.push(to) },
              )
            }}
          >
            <CardHeader>
              <CardTitle>
                <Typography variant="h2" as="h1">
                  Staff log in
                </Typography>
              </CardTitle>
              <CardDescription>
                For lab staff with a dashboard account. Visitors sign in at the station with their
                card instead.
              </CardDescription>
            </CardHeader>
            <CardContent className="gap-6">
              {login.isError ? (
                <Alert variant="destructive">
                  <AlertTitle>{loginErrorTitle(login.error)}</AlertTitle>
                  <AlertDescription className="whitespace-pre-line">
                    {errorMessage(login.error)}
                  </AlertDescription>
                </Alert>
              ) : null}
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="login-identifier">Email or member ID</FieldLabel>
                  <Input
                    id="login-identifier"
                    autoComplete="username"
                    required
                    autoFocus
                    value={identifier}
                    onChange={(event) => setIdentifier(event.target.value)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="login-password">Password</FieldLabel>
                  <Input
                    id="login-password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </Field>
              </FieldGroup>
              <Link
                to="/recover-password"
                className="self-start text-sm underline underline-offset-4"
              >
                Forgot your password?
              </Link>
            </CardContent>
            <CardFooter className="justify-between gap-2">
              <Button variant="ghost" nativeButton={false} render={<Link to="/" />}>
                Cancel
              </Button>
              <Button type="submit" disabled={login.isPending}>
                {login.isPending ? <Spinner /> : null}
                Log in
              </Button>
            </CardFooter>
          </form>
        </Card>
      </main>
    </div>
  )
}
