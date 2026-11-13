import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

export function Pager({
  page,
  pageSize,
  total,
  onPage,
  pageSizes = [50, 100, 250, 500, 1000],
  onPageSizeChange,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (page: number) => void
  pageSizes?: number[]
  onPageSizeChange?: (size: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(total, page * pageSize)
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground"
    >
      <span>
        {first}–{last} of {total}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        {onPageSizeChange ? (
          <label className="flex items-center gap-2 text-xs">
            Rows
            <NativeSelect aria-label="Rows per page" value={pageSize} onChange={event => onPageSizeChange(Number(event.target.value))}>
              {pageSizes.map(size => <NativeSelectOption key={size} value={size}>{size}</NativeSelectOption>)}
            </NativeSelect>
          </label>
        ) : null}
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeftIcon />
          Previous
        </Button>
        <span>
          Page {page} of {pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
          <ChevronRightIcon />
        </Button>
      </div>
    </nav>
  )
}
