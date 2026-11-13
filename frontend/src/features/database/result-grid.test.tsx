import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { ResultGrid } from './result-grid'

afterEach(cleanup)
it('hides id by default and allows showing it through column controls', async () => {
  render(<ResultGrid columns={['id', 'email', 'first_name']} rows={[["row-uuid", 'person@charlotte.edu', 'Person']]} caption="People" />)
  expect(screen.queryByRole('columnheader', { name: 'id' })).toBeNull()
  expect(screen.getByText('person@charlotte.edu')).toBeDefined()
  fireEvent.click(screen.getByRole('button', { name: /Columns/ }))
  fireEvent.click(await screen.findByRole('menuitemcheckbox', { name: /^id$/ }))
  expect(screen.getByRole('columnheader', { name: 'id' })).toBeDefined()
  expect(screen.getByText('row-uuid')).toBeDefined()
})
it('keeps duplicate column aliases separate and preserves whole values', () => {
  render(<ResultGrid columns={['name', 'name']} rows={[["first", 'a-long-value@charlotte.edu']]} caption="Result" />)
  expect(screen.getAllByRole('columnheader', { name: 'name' })).toHaveLength(2)
  expect(screen.getByTitle('a-long-value@charlotte.edu')).toBeDefined()
  expect(screen.getByLabelText('Scrollable query results')).toBeDefined()
})
