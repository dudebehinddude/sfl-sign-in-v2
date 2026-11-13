import type { ReactNode } from 'react'

import { Typography } from '@/components/typography'

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex max-w-prose flex-col gap-1">
        <Typography variant="h1">{title}</Typography>
        {description ? <Typography variant="muted">{description}</Typography> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}
