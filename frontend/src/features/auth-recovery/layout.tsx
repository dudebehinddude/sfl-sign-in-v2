import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import { Typography } from '@/components/typography'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export function RecoveryLayout({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="min-h-svh">
      <header className="border-b">
        <div className="mx-auto flex min-h-14 max-w-6xl items-center px-4">
          <Link to="/" className="font-heading text-lg font-semibold">
            Super Fab Lab
          </Link>
        </div>
      </header>
      <main className="mx-auto flex max-w-md flex-col gap-6 px-4 py-12">
        <Card>
          <CardHeader>
            <CardTitle>
              <Typography id="recovery-title" variant="h2" as="h1">
                {title}
              </Typography>
            </CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          {children}
        </Card>
      </main>
    </div>
  )
}
