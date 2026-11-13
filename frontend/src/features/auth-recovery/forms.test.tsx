import type { AnchorHTMLAttributes, ReactNode } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { RequestRecoveryForm, ResetPasswordForm } from './forms'

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    to,
    children,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string; children: ReactNode }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}))
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
const token = 'synthetic_recovery_link_token_123456789'
const password = 'new-test-password-only'
function response(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function submitRecoveryEmail() {
  fireEvent.change(screen.getByLabelText('Recovery email'), {
    target: { value: 'Visitor@charlotte.edu' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Send recovery email' }))
}
function enterPasswords(first = password, second = first) {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: first } })
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: second } })
}

it('requests recovery with only the email and keeps the generic response for every account', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      response(200, {
        message: 'If that email belongs to an active account, a recovery email has been queued',
      }),
    )
  vi.stubGlobal('fetch', fetch)
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  render(<RequestRecoveryForm />)
  submitRecoveryEmail()
  expect(await screen.findByText('Check your email')).toBeVisible()
  expect(
    screen.getByText(
      /If that email belongs to an active account, a recovery email has been queued/,
    ),
  ).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/api/auth/password-reset/request')
  expect(options.method).toBe('POST')
  expect(JSON.parse(options.body)).toEqual({ email: 'Visitor@charlotte.edu' })
  expect(screen.queryByLabelText('Recovery email')).toBeNull()
  expect(screen.getByRole('link', { name: 'Back to log in' })).toHaveAttribute('href', '/login')
  expect(storage).not.toHaveBeenCalled()
})
it.each([
  [
    503,
    'Email recovery is unavailable',
    'Email delivery is not configured; contact a superadmin for account recovery',
  ],
  [429, 'Too many recovery requests', 'Too many recovery requests; try again in an hour'],
])(
  'preserves recovery failure %s without claiming an email was queued',
  async (status, title, detail) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(status, { detail })))
    render(<RequestRecoveryForm />)
    submitRecoveryEmail()
    expect(await screen.findByText(title)).toBeVisible()
    expect(screen.getByText(detail)).toBeVisible()
    expect(screen.queryByText('Check your email')).toBeNull()
    expect(screen.getByRole('button', { name: 'Send recovery email' })).toBeEnabled()
  },
)
it.each([undefined, '', 'short', 'invalid<script>token_that_is_long_enough', ['token', token]])(
  'does not submit or display a missing or malformed recovery token',
  (invalid) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    render(<ResetPasswordForm token={invalid} />)
    expect(screen.getByRole('heading', { name: 'Invalid recovery link' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Request a new recovery link' })).toHaveAttribute(
      'href',
      '/recover-password',
    )
    expect(screen.queryByLabelText('New password')).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  },
)
it('blocks weak or mismatched passwords, then submits the exact token/password and clears the form on success', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      response(200, { message: 'Password updated; sign in with your new password' }),
    )
  vi.stubGlobal('fetch', fetch)
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  render(<ResetPasswordForm token={token} />)
  enterPasswords('short')
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  expect(screen.getByText('Use between 12 and 1,024 characters.')).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
  enterPasswords(password, 'different-password')
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  expect(screen.getByText('Passwords do not match.')).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
  enterPasswords()
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  expect(await screen.findByRole('heading', { name: 'Password updated' })).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/api/auth/password-reset/complete')
  expect(JSON.parse(options.body)).toEqual({ token, password })
  expect(screen.getByRole('link', { name: 'Log in with your new password' })).toHaveAttribute(
    'href',
    '/login',
  )
  expect(screen.queryByLabelText('New password')).toBeNull()
  expect(document.body.textContent).not.toContain(token)
  expect(storage).not.toHaveBeenCalled()
})
it('replaces an expired or consumed server link with a new-link action', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(response(400, { detail: 'Recovery link is invalid or expired' })),
  )
  render(<ResetPasswordForm token={token} />)
  enterPasswords()
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  expect(await screen.findByRole('heading', { name: 'Invalid recovery link' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Update password' })).toBeNull()
  expect(screen.getByRole('link', { name: 'Request a new recovery link' })).toBeVisible()
  expect(document.body.textContent).not.toContain(token)
})
it('does not report a lost response as a confirmed password update or automatically replay it', async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError('Network offline'))
  vi.stubGlobal('fetch', fetch)
  render(<ResetPasswordForm token={token} />)
  enterPasswords()
  fireEvent.click(screen.getByRole('button', { name: 'Update password' }))
  await waitFor(() =>
    expect(screen.getByText('Password update could not be confirmed')).toBeVisible(),
  )
  expect(
    screen.getByText(
      'Try logging in with your new password before requesting another recovery link.',
    ),
  ).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('heading', { name: 'Password updated' })).toBeNull()
})
