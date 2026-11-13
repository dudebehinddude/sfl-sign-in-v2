import { createFileRoute } from '@tanstack/react-router'

import { PrintingPage } from '@/features/printing/page'

export const Route = createFileRoute('/admin/printing')({ component: PrintingPage })
