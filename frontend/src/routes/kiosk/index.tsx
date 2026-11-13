import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createFileRoute } from '@tanstack/react-router'
import { RotateCcwIcon, WifiOffIcon } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { isStale } from '@/lib/live/socket'
import { ErrorState } from '@/components/query-state'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { forgottenLeaderboardQuery, kioskStateQuery } from '@/features/kiosk/api'
import type { KeyholderPhase, Phase, RegisteringPhase } from '@/features/kiosk/machine'
import { useScannerBurst } from '@/features/kiosk/scanner-burst'
import { useKiosk } from '@/features/kiosk/use-kiosk'
import { occupancyQuery } from '@/features/occupancy/api'
import { usePublicLive } from '@/features/occupancy/use-public-live'
import { kioskKeys } from '@/lib/query-keys'
import { GlancePanel } from './_components/glance-panel'
import { KeyholderDialog } from './_components/keyholder-dialog'
import { RecentActivity } from './_components/recent-activity'
import { RegistrationDialog } from './_components/registration-dialog'
import { ScanForm } from './_components/scan-form'
import { ScanHeadline } from './_components/scan-headline'
// oxlint-disable-next-line import/no-unassigned-import -- Station layout styles are scoped by class.
import './station.css'

export const Route = createFileRoute('/kiosk/')({
  component: KioskPage,
})

function KioskPage() {
  const kioskState = useQuery(kioskStateQuery)
  if (kioskState.isPending) {
    return (
      <main className="flex min-h-svh items-center justify-center">
        <Spinner className="size-8" aria-label="Loading station" />
      </main>
    )
  }
  return <Station />
}

/** Registration and keyholder dialogs stay mounted while their own command is sending. */
function activeDialog(phase: Phase): RegisteringPhase | KeyholderPhase | null {
  if (phase.name === 'sending') return phase.from ?? null
  if (phase.name === 'registering' || phase.name === 'keyholder') return phase
  return null
}

function Station() {
  const client = useQueryClient()
  const kioskState = useQuery(kioskStateQuery)
  const occupancy = useQuery(occupancyQuery)
  const status = usePublicLive(() => client.invalidateQueries({ queryKey: kioskKeys.all }))
  const leaderboard = useQuery(forgottenLeaderboardQuery)
  const kiosk = useKiosk()
  const { phase, feedback } = kiosk.state
  const scanRef = useRef<HTMLInputElement>(null)
  const dialog = activeDialog(phase)
  const dialogOpen = dialog !== null
  const busy = phase.name === 'sending'

  useEffect(() => {
    if (!dialogOpen && phase.name !== 'sending') scanRef.current?.focus()
  }, [dialogOpen, phase.name])

  // Scanners type like a keyboard: route stray keystrokes into the scan box.
  useEffect(() => {
    if (dialogOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      scanRef.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => document.removeEventListener('keydown', onKeyDown, true)
  }, [dialogOpen])

  // A card scanned while focus is on a button must not press it. Dialogs
  // install their own scanner handling while open.
  useScannerBurst(kiosk.scan, !dialogOpen && !busy)

  const isOpen = occupancy.data?.lab.is_open ?? kioskState.data?.lab.is_open ?? null

  return (
    <div className="station-shell">
      <main className="station-main">
        <section aria-label="Card scanner" className="station-intro">
          <div className="station-scanner rounded-lg border bg-card p-3 shadow-sm">
            <ScanForm
              id="member-id"
              label="Member ID"
              placeholder="Member ID"
              inputRef={scanRef}
              autoFocus
              compact
              busy={busy && !dialogOpen}
              onScan={kiosk.scan}
            />
          </div>
          <ScanHeadline isOpen={isOpen} feedback={feedback} onDismiss={kiosk.dismissFeedback} />
        </section>
        <div className="station-messages">
          {kioskState.isError ? (
            <ErrorState error={kioskState.error} onRetry={() => kioskState.refetch()} />
          ) : null}
          {isStale(status) ? (
            <Alert>
              <WifiOffIcon />
              <AlertTitle>Reconnecting to the lab server</AlertTitle>
              <AlertDescription>
                Lab information may be out of date. Scans still go to the server.
              </AlertDescription>
            </Alert>
          ) : null}
          {phase.name === 'uncertain' ? (
            <Alert variant="destructive">
              <RotateCcwIcon />
              <AlertTitle>The scan result is uncertain</AlertTitle>
              <AlertDescription>
                {phase.message} Check current activity before scanning again.
              </AlertDescription>
              <div className="col-start-2 mt-2">
                <Button
                  className="min-h-11 whitespace-normal"
                  variant="outline"
                  onClick={kiosk.checkState}
                >
                  Refresh current state
                </Button>
              </div>
            </Alert>
          ) : null}
        </div>
        <RecentActivity activity={kioskState.data?.recent_activity} />
      </main>
      <aside aria-label="Lab information" className="station-info">
        <GlancePanel occupancy={occupancy.data} kiosk={kioskState.data} leaderboard={leaderboard.data?.items} />
      </aside>

      {dialog?.name === 'registering' ? (
        <RegistrationDialog
          key={dialog.identifier}
          identifier={dialog.identifier}
          busy={busy}
          formError={dialog.formError}
          onSubmit={kiosk.register}
          onCancel={(reason) =>
            kiosk.cancel(
              reason === 'timeout'
                ? {
                    tone: 'info',
                    title: 'Registration timed out',
                    message: 'Scan your card to start again.',
                  }
                : undefined,
            )
          }
          onScanDuringForm={kiosk.scan}
        />
      ) : null}

      {dialog?.name === 'keyholder' ? (
        <KeyholderDialog
          key={`${dialog.identifier}/${dialog.expectedShiftId}`}
          identifier={dialog.identifier}
          actions={dialog.actions}
          message={dialog.message}
          occupancy={occupancy.data}
          busy={busy}
          onAction={kiosk.keyholder}
          onCancel={() => kiosk.cancel()}
          onNewScan={kiosk.scan}
        />
      ) : null}
    </div>
  )
}
