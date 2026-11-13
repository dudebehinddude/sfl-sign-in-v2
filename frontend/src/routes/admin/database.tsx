import { createFileRoute } from '@tanstack/react-router'
import { DatabasePage } from '@/features/database/workbench'

export const Route = createFileRoute('/admin/database')({
  component: DatabasePage,
})
