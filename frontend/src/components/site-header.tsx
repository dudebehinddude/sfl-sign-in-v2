import { Link, useNavigate } from '@tanstack/react-router'
import { LogOutIcon, UserRoundIcon } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLogout, useSession } from '@/features/auth/session'
import { errorMessage } from '@/lib/api/client'
import { canOpenAdmin } from '@/features/auth/nav'

export function SiteHeader() {
  return (
    <header className="border-b">
      <div className="mx-auto flex min-h-14 max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 sm:flex-nowrap sm:py-0">
        <Link
          to="/"
          className="flex-1 font-heading text-lg font-semibold tracking-tight sm:flex-none"
        >
          Super Fab Lab
        </Link>
        <nav
          aria-label="Main"
          className="order-last flex basis-full items-center justify-center gap-1 sm:order-none sm:flex-1 sm:basis-auto sm:justify-start"
        >
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link to="/occupancy" />}>
            In the lab
          </Button>
          <Button variant="ghost" size="sm" nativeButton={false} render={<Link to="/kiosk" />}>
            Station
          </Button>
        </nav>
        <AccountMenu />
      </div>
    </header>
  )
}

function AccountMenu() {
  const { user, query } = useSession()
  const logout = useLogout()
  const navigate = useNavigate()

  if (query.isPending) return null
  if (!user) {
    return (
      <Button variant="outline" size="sm" nativeButton={false} render={<Link to="/login" />}>
        Staff log in
      </Button>
    )
  }

  const signOut = () =>
    logout.mutate(undefined, {
      onError: (error) =>
        toast.error(
          `Logged out on this screen, but the server did not confirm: ${errorMessage(error)}`,
        ),
      onSettled: () => navigate({ to: '/' }),
    })

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="outline" size="sm" className="max-w-36 sm:max-w-52" />}
      >
        <UserRoundIcon />
        <span className="truncate">{user.display_name}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuGroup>
          <DropdownMenuLabel>{user.email ?? user.display_name}</DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem render={<Link to="/me" />}>My profile</DropdownMenuItem>
          {canOpenAdmin(user) ? (
            <DropdownMenuItem render={<Link to="/admin" />}>Staff dashboard</DropdownMenuItem>
          ) : null}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={signOut}>
          <LogOutIcon />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
