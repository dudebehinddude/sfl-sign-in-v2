import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button, buttonVariants } from '@/components/ui/button'
import { CardContent, CardFooter } from '@/components/ui/card'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { NetworkError, errorMessage, isStatus } from '@/lib/api/client'
import { completePasswordReset, requestPasswordReset } from './api'
import { RecoveryLayout } from './layout'
import { recoveryToken } from './validation'

export function RequestRecoveryForm() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<unknown>(null)
  return (
    <RecoveryLayout
      title="Recover your password"
      description="Use the recovery email on your staff account."
    >
      {sent ? (
        <>
          <CardContent>
            <Alert role="status">
              <AlertTitle>Check your email</AlertTitle>
              <AlertDescription>
                If that email belongs to an active account, a recovery email has been queued. Open
                the latest recovery link from your inbox.
              </AlertDescription>
            </Alert>
          </CardContent>
          <CardFooter className="flex flex-wrap justify-between gap-2">
            <Button type="button" variant="outline" onClick={() => setSent(false)}>
              Use a different email
            </Button>
            <Link to="/login" className={buttonVariants()}>
              Back to log in
            </Link>
          </CardFooter>
        </>
      ) : (
        <form
          className="flex flex-col gap-6"
          aria-labelledby="recovery-title"
          onSubmit={async (event) => {
            event.preventDefault()
            if (busy || !email.trim()) return
            setBusy(true)
            setError(null)
            try {
              await requestPasswordReset({ email: email.trim() })
              setEmail('')
              setSent(true)
            } catch (failure) {
              setError(failure)
            } finally {
              setBusy(false)
            }
          }}
        >
          <CardContent className="flex flex-col gap-5">
            {error ? (
              <Alert variant="destructive" role="alert">
                <AlertTitle>
                  {isStatus(error, 503)
                    ? 'Email recovery is unavailable'
                    : isStatus(error, 429)
                      ? 'Too many recovery requests'
                      : 'Could not request recovery'}
                </AlertTitle>
                <AlertDescription className="whitespace-pre-line">
                  {errorMessage(error)}
                </AlertDescription>
              </Alert>
            ) : null}
            <Field>
              <FieldLabel htmlFor="recovery-email">Recovery email</FieldLabel>
              <Input
                id="recovery-email"
                type="email"
                autoComplete="email"
                autoFocus
                required
                maxLength={254}
                disabled={busy}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <FieldDescription>
                Check your inbox and spam folder after sending.
              </FieldDescription>
            </Field>
          </CardContent>
          <CardFooter className="justify-between gap-2">
            <Link to="/login" className={buttonVariants({ variant: 'ghost' })}>
              Back to log in
            </Link>
            <Button type="submit" disabled={busy}>
              {busy ? <Spinner /> : null}Send recovery email
            </Button>
          </CardFooter>
        </form>
      )}
    </RecoveryLayout>
  )
}

function InvalidRecoveryLink() {
  return (
    <RecoveryLayout
      title="Invalid recovery link"
      description="This link is missing, invalid, expired, or has already been used."
    >
      <CardContent>
        <Alert variant="destructive" role="alert">
          <AlertTitle>Request a new link</AlertTitle>
          <AlertDescription>
            Open the newest recovery email to choose your password.
          </AlertDescription>
        </Alert>
      </CardContent>
      <CardFooter className="flex flex-wrap justify-between gap-2">
        <Link to="/recover-password" className={buttonVariants()}>
          Request a new recovery link
        </Link>
        <Link to="/login" className={buttonVariants({ variant: 'ghost' })}>
          Back to log in
        </Link>
      </CardFooter>
    </RecoveryLayout>
  )
}

export function ResetPasswordForm({ token: suppliedToken }: { token: unknown }) {
  const token = recoveryToken(suppliedToken)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [attempted, setAttempted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [complete, setComplete] = useState(false)
  const [error, setError] = useState<unknown>(null)
  if (!token || isStatus(error, 400)) return <InvalidRecoveryLink />
  const passwordError = attempted && (password.length < 12 || password.length > 1024)
  const mismatch = (attempted || confirmation.length > 0) && password !== confirmation
  if (complete)
    return (
      <RecoveryLayout
        title="Password updated"
        description="Your previous sessions have been signed out."
      >
        <CardContent>
          <Alert role="status">
            <AlertTitle>You can log in now</AlertTitle>
            <AlertDescription>
              Use your new password to log in to the staff dashboard.
            </AlertDescription>
          </Alert>
        </CardContent>
        <CardFooter>
          <Link to="/login" className={buttonVariants()}>
            Log in with your new password
          </Link>
        </CardFooter>
      </RecoveryLayout>
    )
  return (
    <RecoveryLayout
      title="Choose a new password"
      description="Enter the same new password in both fields."
    >
      <form
        className="flex flex-col gap-6"
        aria-labelledby="recovery-title"
        noValidate
        onSubmit={async (event) => {
          event.preventDefault()
          setAttempted(true)
          if (busy || password.length < 12 || password.length > 1024 || password !== confirmation)
            return
          setBusy(true)
          setError(null)
          try {
            await completePasswordReset({ token, password })
            setPassword('')
            setConfirmation('')
            setComplete(true)
          } catch (failure) {
            setError(failure)
          } finally {
            setBusy(false)
          }
        }}
      >
        <CardContent className="flex flex-col gap-5">
          {error ? (
            <Alert variant="destructive" role="alert">
              <AlertTitle>
                {error instanceof NetworkError
                  ? 'Password update could not be confirmed'
                  : 'Could not update your password'}
              </AlertTitle>
              <AlertDescription className="whitespace-pre-line">
                {error instanceof NetworkError
                  ? 'Try logging in with your new password before requesting another recovery link.'
                  : errorMessage(error)}
              </AlertDescription>
            </Alert>
          ) : null}
          <FieldGroup>
            <Field data-invalid={passwordError || undefined}>
              <FieldLabel htmlFor="reset-password">New password</FieldLabel>
              <Input
                id="reset-password"
                type="password"
                autoComplete="new-password"
                autoFocus
                required
                minLength={12}
                maxLength={1024}
                value={password}
                disabled={busy}
                aria-invalid={passwordError || undefined}
                aria-describedby={passwordError ? 'reset-password-error' : 'reset-password-help'}
                onChange={(event) => setPassword(event.target.value)}
              />
              {passwordError ? (
                <FieldError id="reset-password-error">
                  Use between 12 and 1,024 characters.
                </FieldError>
              ) : (
                <FieldDescription id="reset-password-help">
                  Use at least 12 characters.
                </FieldDescription>
              )}
            </Field>
            <Field data-invalid={mismatch || undefined}>
              <FieldLabel htmlFor="reset-confirmation">Confirm new password</FieldLabel>
              <Input
                id="reset-confirmation"
                type="password"
                autoComplete="new-password"
                required
                maxLength={1024}
                value={confirmation}
                disabled={busy}
                aria-invalid={mismatch || undefined}
                aria-describedby={mismatch ? 'reset-confirmation-error' : undefined}
                onChange={(event) => setConfirmation(event.target.value)}
              />
              {mismatch ? (
                <FieldError id="reset-confirmation-error">Passwords do not match.</FieldError>
              ) : null}
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-between gap-2">
          <Link to="/login" className={buttonVariants({ variant: 'ghost' })}>
            Back to log in
          </Link>
          <Button type="submit" disabled={busy}>
            {busy ? <Spinner /> : null}Update password
          </Button>
        </CardFooter>
      </form>
    </RecoveryLayout>
  )
}
