import { Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { CheckCircle2Icon, CircleAlertIcon, DoorClosedIcon, LogOutIcon } from 'lucide-react'

import { Typography } from '@/components/typography'
import type { Feedback, FeedbackTone } from '@/features/kiosk/machine'
import { cn } from '@/lib/utils'

const FEEDBACK_MS = 7000

const TONE_CLASS: Record<FeedbackTone, string> = {
  success: 'border-primary bg-primary/15',
  info: 'border-border bg-muted',
  warning: 'border-amber-500 bg-amber-500/15',
  error: 'border-destructive bg-destructive/15',
}

const TONE_ICON = {
  success: CheckCircle2Icon,
  info: LogOutIcon,
  warning: DoorClosedIcon,
  error: CircleAlertIcon,
} satisfies Record<FeedbackTone, unknown>

/**
 * The legacy station headline doubles as scan feedback: the welcome line is
 * replaced by the result in large type, then returns after a few seconds.
 */
export function ScanHeadline({
  isOpen,
  feedback,
  onDismiss,
}: {
  isOpen: boolean | null
  feedback: Feedback | null
  onDismiss: (id: number) => void
}) {
  const onDismissRef = useRef(onDismiss)
  useEffect(() => {
    onDismissRef.current = onDismiss
  })
  useEffect(() => {
    if (!feedback) return
    const timer = setTimeout(() => onDismissRef.current(feedback.id), FEEDBACK_MS)
    return () => clearTimeout(timer)
  }, [feedback])

  return (
    <div aria-live="assertive" aria-atomic className="min-w-0">
      {feedback ? (
        <FeedbackPanel key={feedback.id} feedback={feedback} />
      ) : (
        <div className="station-welcome">
          <h1>
            {isOpen === false ? 'The ' : 'Welcome to the '}
            <Link to="/" className="text-primary">Super Fab Lab</Link>
            {isOpen === false ? ' is Closed' : ''}
          </h1>
          <Clock />
        </div>
      )}
    </div>
  )
}

function FeedbackPanel({ feedback }: { feedback: Feedback }) {
  const Icon = TONE_ICON[feedback.tone]
  return (
    <div
      role={feedback.tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'flex min-w-0 items-start gap-3 rounded-xl border-l-4 p-3',
        TONE_CLASS[feedback.tone],
      )}
    >
      <Icon aria-hidden className="mt-0.5 size-7 shrink-0" />
      <div className="flex min-w-0 flex-col gap-1">
        <Typography variant="h1" as="p" className="break-words">
          {feedback.title}
        </Typography>
        {feedback.message ? (
          <Typography variant="body" className="break-words">
            {feedback.message}
          </Typography>
        ) : null}
      </div>
    </div>
  )
}

const clockDateFormat = new Intl.DateTimeFormat(undefined, {
  timeZone: 'America/New_York', weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
})
const clockTimeFormat = new Intl.DateTimeFormat(undefined, {
  timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit', second: '2-digit',
})

function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return <time className="station-clock" dateTime={now.toISOString()}>
    <span>{clockDateFormat.format(now)}</span>
    <span>{clockTimeFormat.format(now)}</span>
  </time>
}
