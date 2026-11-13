import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { TrainingBadgeList, TrainingIcon } from './training-badge'
import { TooltipProvider } from './ui/tooltip'

afterEach(cleanup)
it('preserves the server sticker sequence instead of alphabetizing training badges', () => {
  render(<TooltipProvider><TrainingBadgeList badges={[
    { training_type_id: 'policies', name: 'Policies and Procedures', icon_key: 'policies' },
    { training_type_id: 'orientation', name: 'Orientation', icon_key: 'orientation' },
    { training_type_id: 'fdm', name: 'FDM Printing', icon_key: '3d-printer' },
  ]} /></TooltipProvider>)
  expect(screen.getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Completed Policies and Procedures.', 'Completed Orientation.', 'Completed FDM Printing.'])
})
it('loads bucket keys only through same-origin app media and recovers when the source changes', () => {
  const first = `training-icons/${'a'.repeat(32)}.png`
  const second = `training-icons/${'b'.repeat(32)}.png`
  const view = render(<TooltipProvider><TrainingIcon name="Custom" iconKey={first} /></TooltipProvider>)
  const image = view.container.querySelector('img')!
  expect(image.getAttribute('src')).toBe(`/media/${first}`)
  fireEvent.error(image)
  expect(view.container.querySelector('img')).toBeNull()
  view.rerender(<TooltipProvider><TrainingIcon name="Custom" iconKey={second} /></TooltipProvider>)
  expect(view.container.querySelector('img')?.getAttribute('src')).toBe(`/media/${second}`)
  view.rerender(<TooltipProvider><TrainingIcon name="Custom" iconKey="https://example.com/remote.png" /></TooltipProvider>)
  expect(view.container.querySelector('img')).toBeNull()
})
