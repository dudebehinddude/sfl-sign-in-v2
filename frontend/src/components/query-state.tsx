import type { ReactNode } from 'react'
import { CircleAlertIcon, InboxIcon } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage, isStatus } from '@/lib/api/client'

export function LoadingRows({ rows = 4, label = 'Loading' }: { rows?: number; label?: string }) {
  return (
    <div className="flex flex-col gap-2" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={`row-${index.toString()}`} className="h-10 w-full" />
      ))}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
  title,
}: {
  error: unknown
  onRetry?: () => void
  title?: string
}) {
  const heading =
    title ??
    (isStatus(error, 403)
      ? 'You do not have permission to view this'
      : isStatus(error, 404)
        ? 'Not available on this server'
        : 'Could not load this')
  return (
    <Alert variant="destructive">
      <CircleAlertIcon />
      <AlertTitle>{heading}</AlertTitle>
      <AlertDescription className="whitespace-pre-line">{errorMessage(error)}</AlertDescription>
      {onRetry ? (
        <div className="col-start-2 mt-2">
          <Button className="min-h-11" variant="outline" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : null}
    </Alert>
  )
}

export function EmptyState({
  title,
  description,
  icon,
  children,
}: {
  title: string
  description?: ReactNode
  icon?: ReactNode
  children?: ReactNode
}) {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">{icon ?? <InboxIcon />}</EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </EmptyHeader>
      {children ? <EmptyContent>{children}</EmptyContent> : null}
    </Empty>
  )
}
