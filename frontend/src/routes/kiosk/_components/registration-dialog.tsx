import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'

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
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useScannerBurst } from '@/features/kiosk/scanner-burst'
import { isUniversityEmail, UNIVERSITY_EMAIL_MESSAGE } from '@/lib/university-email'

export const REGISTRATION_IDLE_MS = 90_000

interface RegistrationDialogProps {
  identifier: string
  busy: boolean
  formError?: string
  onSubmit: (fields: { first_name: string; last_name: string; email: string }) => void
  onCancel: (reason: 'cancelled' | 'timeout') => void
  onScanDuringForm: (identifier: string) => void
  clock?: () => number
}

function maskIdentifier(identifier: string) {
  return identifier.length > 4 ? `ending in ${identifier.slice(-4)}` : identifier
}

export function RegistrationDialog({
  identifier,
  busy,
  formError,
  onSubmit,
  onCancel,
  onScanDuringForm,
  clock,
}: RegistrationDialogProps) {
  const [fields, setFields] = useState({ first_name: '', last_name: '', email: '' })
  const [emailError, setEmailError] = useState<string | null>(null)
  const onCancelRef = useRef(onCancel)
  const idleTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    onCancelRef.current = onCancel
  })

  // A new card replaces the draft; the scanner's Enter cannot submit it.
  useScannerBurst(onScanDuringForm, !busy, clock)
  const armIdleTimer = useCallback(() => {
    clearTimeout(idleTimer.current)
    idleTimer.current = setTimeout(() => onCancelRef.current('timeout'), REGISTRATION_IDLE_MS)
  }, [])
  useEffect(() => {
    if (busy) return
    armIdleTimer()
    return () => clearTimeout(idleTimer.current)
  }, [busy, armIdleTimer])

  const update = (key: keyof typeof fields) => (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value
    setFields((current) => ({ ...current, [key]: value }))
    if (key === 'email' && emailError)
      setEmailError(isUniversityEmail(value) ? null : UNIVERSITY_EMAIL_MESSAGE)
    armIdleTimer()
  }
  const nameHasDigits = /\d/.test(fields.first_name) || /\d/.test(fields.last_name)

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) onCancel('cancelled')
      }}
    >
      <DialogContent
        className="flex max-h-[calc(100dvh-1rem)] max-w-[calc(100vw-1rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg [&>button]:top-2 [&>button]:right-2 [&>button]:size-11"
        showCloseButton={!busy}
      >
        <form
          className="flex min-h-0 flex-col"
          onSubmit={(event) => {
            event.preventDefault()
            if (busy) return
            const validEmail = isUniversityEmail(fields.email)
            setEmailError(validEmail ? null : UNIVERSITY_EMAIL_MESSAGE)
            if (
              nameHasDigits ||
              !validEmail ||
              !fields.first_name.trim() ||
              !fields.last_name.trim()
            )
              return
            onSubmit({
              first_name: fields.first_name.trim(),
              last_name: fields.last_name.trim(),
              email: fields.email.trim(),
            })
          }}
        >
          <DialogHeader className="shrink-0 gap-1 border-b p-4 pr-14">
            <DialogTitle>
              <Typography variant="h1" as="span">
                First visit
              </Typography>
            </DialogTitle>
            <DialogDescription>
              Card {maskIdentifier(identifier)}. Enter your name and university email.
            </DialogDescription>
          </DialogHeader>
          <div className="min-h-0 overflow-y-auto overscroll-contain px-4 py-3">
            <FieldGroup className="gap-3">
              <Field className="gap-1.5" data-invalid={nameHasDigits || undefined}>
                <FieldLabel htmlFor="reg-first">First name</FieldLabel>
                <Input
                  id="reg-first"
                  autoFocus
                  required
                  maxLength={100}
                  autoComplete="off"
                  value={fields.first_name}
                  onChange={update('first_name')}
                  aria-invalid={nameHasDigits || undefined}
                  disabled={busy}
                  className="h-11 text-base"
                />
              </Field>
              <Field className="gap-1.5" data-invalid={nameHasDigits || undefined}>
                <FieldLabel htmlFor="reg-last">Last name</FieldLabel>
                <Input
                  id="reg-last"
                  required
                  maxLength={100}
                  autoComplete="off"
                  value={fields.last_name}
                  onChange={update('last_name')}
                  aria-invalid={nameHasDigits || undefined}
                  disabled={busy}
                  className="h-11 text-base"
                />
                {nameHasDigits ? <FieldError>Names cannot contain numbers.</FieldError> : null}
              </Field>
              <Field className="gap-1.5" data-invalid={!!emailError || undefined}>
                <FieldLabel htmlFor="reg-email">University email</FieldLabel>
                <Input
                  id="reg-email"
                  type="email"
                  required
                  maxLength={254}
                  autoComplete="off"
                  autoCapitalize="none"
                  placeholder="jsmith@charlotte.edu"
                  value={fields.email}
                  onChange={update('email')}
                  onBlur={() =>
                    setEmailError(
                      fields.email && !isUniversityEmail(fields.email)
                        ? UNIVERSITY_EMAIL_MESSAGE
                        : null,
                    )
                  }
                  aria-invalid={!!emailError || undefined}
                  aria-describedby={emailError ? 'reg-email-error' : undefined}
                  disabled={busy}
                  className="h-11 text-base"
                />
                {emailError ? <FieldError id="reg-email-error">{emailError}</FieldError> : null}
              </Field>
              {formError ? (
                <FieldError className="whitespace-pre-line">{formError}</FieldError>
              ) : null}
              <Typography variant="small">
                A new card replaces this form. It closes after 90 seconds of inactivity.
              </Typography>
            </FieldGroup>
          </div>
          <DialogFooter className="shrink-0 flex-row border-t p-3">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => onCancel('cancelled')}
              className="min-h-11 flex-1 sm:flex-none"
            >
              Cancel
            </Button>
            <Button type="submit" disabled={busy} className="min-h-11 flex-1 sm:flex-none">
              {busy ? <Spinner /> : null}
              {busy ? 'Signing in…' : 'Enter the lab'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
