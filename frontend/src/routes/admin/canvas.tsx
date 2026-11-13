import { createFileRoute } from '@tanstack/react-router'

import { CanvasPage } from '@/features/canvas/page'

export const Route = createFileRoute('/admin/canvas')({ component: CanvasPage })
