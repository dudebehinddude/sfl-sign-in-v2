import { createFileRoute } from '@tanstack/react-router'
import { MetricsPage } from '@/features/metrics/dashboard'

export const Route = createFileRoute('/admin/metrics')({
  component: MetricsPage,
})
