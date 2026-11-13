import { useState, type ReactNode } from 'react'
import { TriangleAlertIcon } from 'lucide-react'

import { Typography } from '@/components/typography'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Field, FieldLabel } from '@/components/ui/field'
import { Spinner } from '@/components/ui/spinner'
import { keyholderScanIntent, keyholderVariant } from '@/features/kiosk/keyholder-intent'
import { useScannerBurst } from '@/features/kiosk/scanner-burst'
import type { KeyholderAction, Occupancy } from '@/lib/api/types'
import { ScanForm } from './scan-form'

type ActionExtra = { target_identifier?: string; sign_out_current_keyholder?: boolean }
interface KeyholderDialogProps {
  identifier: string
  actions: KeyholderAction[]
  message: string
  occupancy: Occupancy | undefined
  busy: boolean
  onAction: (action: KeyholderAction, extra?: ActionExtra) => void
  onCancel: () => void
  onNewScan: (identifier: string) => void
  clock?: () => number
}

export function KeyholderDialog(props: KeyholderDialogProps) {
  const { identifier, actions, busy, onAction, onNewScan } = props
  const variant = keyholderVariant(actions)
  const [signOutAfterHandoff, setSignOutAfterHandoff] = useState(true)
  const [scanError, setScanError] = useState<string | null>(null)
  const handleScan = (scanned: string) => {
    const intent = keyholderScanIntent(variant, actions, identifier, scanned)
    switch (intent.type) {
      case 'confirm':
        return onAction(intent.action)
      case 'handoff':
        setScanError(null)
        return onAction('handoff', {
          target_identifier: intent.target,
          sign_out_current_keyholder: signOutAfterHandoff,
        })
      case 'own-card':
        return setScanError('The next keyholder needs to scan their own card.')
      case 'new-scan':
        return onNewScan(intent.identifier)
    }
  }
  useScannerBurst(handleScan, !busy, props.clock)
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) props.onCancel()
      }}
    >
      <DialogContent
        className="flex max-h-[calc(100dvh-1rem)] max-w-[calc(100vw-1rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-lg [&>button]:top-2 [&>button]:right-2 [&>button]:size-11"
        showCloseButton={!busy}
      >
        {variant === 'departure' ? (
          <Departure
            {...props}
            onScan={handleScan}
            scanError={scanError}
            signOutAfterHandoff={signOutAfterHandoff}
            onSignOutAfterHandoff={setSignOutAfterHandoff}
          />
        ) : variant === 'takeover' ? (
          <Takeover {...props} onScan={handleScan} />
        ) : (
          <OpenLab {...props} onScan={handleScan} />
        )}
      </DialogContent>
    </Dialog>
  )
}

type VariantProps = KeyholderDialogProps & { onScan: (identifier: string) => void }

function Body({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto overscroll-contain px-4 py-3">
      {children}
    </div>
  )
}

function OpenLab(props: VariantProps) {
  return (
    <>
      <DialogHeader className="shrink-0 gap-1 border-b p-4 pr-14">
        <DialogTitle>
          <Typography variant="h1" as="span">
            Open the lab?
          </Typography>
        </DialogTitle>
        <DialogDescription>
          {props.message || 'Opening the lab makes you the keyholder.'}
        </DialogDescription>
      </DialogHeader>
      <Body>
        <ScanForm
          id="keyholder-confirm"
          label="Scan your card again to confirm"
          placeholder="Scan card again"
          autoFocus
          busy={props.busy}
          onScan={props.onScan}
        />
      </Body>
      <DialogFooter className="shrink-0 flex-row border-t p-3">
        <Button
          variant="outline"
          className="min-h-11 flex-1 sm:flex-none"
          onClick={props.onCancel}
          disabled={props.busy}
        >
          Cancel
        </Button>
        <Button
          className="min-h-11 flex-1 sm:flex-none"
          onClick={() => props.onAction('open')}
          disabled={props.busy}
        >
          {props.busy ? <Spinner /> : null}Open the lab
        </Button>
      </DialogFooter>
    </>
  )
}

function Takeover(props: VariantProps) {
  const current = props.occupancy?.lab.keyholder?.display_name ?? 'the current keyholder'
  return (
    <>
      <DialogHeader className="shrink-0 gap-1 border-b p-4 pr-14">
        <DialogTitle>
          <Typography variant="h1" as="span">
            Take over as keyholder?
          </Typography>
        </DialogTitle>
        <DialogDescription>
          {props.message || `Take over from ${current}.`} Let them know before taking over.
        </DialogDescription>
      </DialogHeader>
      <Body>
        <ScanForm
          id="keyholder-takeover"
          label="Scan your card again to take over"
          placeholder="Scan card again"
          autoFocus
          busy={props.busy}
          onScan={props.onScan}
        />
      </Body>
      <DialogFooter className="shrink-0 flex-row border-t p-3">
        {props.actions.includes('continue') ? (
          <Button
            variant="outline"
            className="min-h-11 flex-1 sm:flex-none"
            onClick={() => props.onAction('continue')}
            disabled={props.busy}
          >
            Just sign in
          </Button>
        ) : (
          <Button
            variant="outline"
            className="min-h-11 flex-1 sm:flex-none"
            onClick={props.onCancel}
            disabled={props.busy}
          >
            Cancel
          </Button>
        )}
        <Button
          className="min-h-11 flex-1 sm:flex-none"
          onClick={() => props.onAction('override')}
          disabled={props.busy}
        >
          {props.busy ? <Spinner /> : null}Take over
        </Button>
      </DialogFooter>
    </>
  )
}

function Departure(
  props: VariantProps & {
    scanError: string | null
    signOutAfterHandoff: boolean
    onSignOutAfterHandoff: (value: boolean) => void
  },
) {
  const [confirmClose, setConfirmClose] = useState(false)
  const keyholderId = props.occupancy?.lab.keyholder?.id
  const others = (props.occupancy?.occupants ?? []).filter((person) => person.id !== keyholderId)
  const canHandoff = props.actions.includes('handoff')
  const canClose = props.actions.includes('close')
  return (
    <>
      <DialogHeader className="shrink-0 gap-1 border-b p-4 pr-14">
        <DialogTitle>
          <Typography variant="h1" as="span">
            Keyholder options
          </Typography>
        </DialogTitle>
        <DialogDescription>
          {props.message || 'Hand off to keep the lab open, or close it.'}
        </DialogDescription>
      </DialogHeader>
      <Body>
        {canHandoff ? (
          <div className="flex min-w-0 flex-col gap-2">
            <ScanForm
              id="keyholder-handoff"
              label="Next keyholder's card"
              placeholder="Scan the next person's card"
              autoFocus
              busy={props.busy}
              description={props.scanError ?? undefined}
              onScan={props.onScan}
            />
            <Field orientation="horizontal" className="min-h-11">
              <Checkbox
                id="handoff-sign-out"
                checked={props.signOutAfterHandoff}
                disabled={props.busy}
                onCheckedChange={(checked) => props.onSignOutAfterHandoff(checked === true)}
              />
              <FieldLabel htmlFor="handoff-sign-out" className="min-h-11 items-center">
                Sign me out after the handoff
              </FieldLabel>
            </Field>
          </div>
        ) : null}
        {canClose ? (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>
              {others.length
                ? `Closing signs out ${others.length} ${others.length === 1 ? 'other person' : 'other people'} as forgotten.`
                : 'No one else is signed in.'}
            </AlertTitle>
            {canHandoff ? <AlertDescription>Handoff keeps the lab open.</AlertDescription> : null}
          </Alert>
        ) : null}
        {others.length ? (
          <details className="min-w-0 rounded-lg border px-3">
            <summary className="min-h-11 cursor-pointer content-center text-sm font-medium">
              Still in the lab ({others.length})
            </summary>
            <ul className="space-y-1 pb-3 text-sm">
              {others.map((person) => (
                <li className="break-words" key={person.id}>
                  {person.display_name}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </Body>
      <DialogFooter className="shrink-0 flex-row border-t p-3">
        <Button
          variant="outline"
          className="min-h-11 flex-1 sm:flex-none"
          onClick={props.onCancel}
          disabled={props.busy}
        >
          Stay signed in
        </Button>
        {canClose ? (
          <Button
            variant="destructive"
            className="min-h-11 flex-1 sm:flex-none"
            onClick={() => (confirmClose ? props.onAction('close') : setConfirmClose(true))}
            disabled={props.busy}
          >
            {props.busy ? <Spinner /> : null}
            {confirmClose ? 'Confirm close' : 'Close the lab'}
          </Button>
        ) : null}
      </DialogFooter>
    </>
  )
}
