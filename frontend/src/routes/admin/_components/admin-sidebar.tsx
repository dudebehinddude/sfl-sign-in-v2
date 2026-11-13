import { Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { HomeIcon, LogOutIcon, UserRoundIcon } from 'lucide-react'
import { toast } from 'sonner'

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar'
import { visibleNav, type AdminNavItem } from '@/features/auth/nav'
import { useLogout } from '@/features/auth/session'
import { errorMessage } from '@/lib/api/client'
import type { SessionUser } from '@/lib/api/types'

const GROUPS: AdminNavItem['group'][] = ['Lab', 'Integrations', 'System']

export function AdminSidebar({ user }: { user: SessionUser }) {
  const { state, isMobile, setOpenMobile } = useSidebar()
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const items = visibleNav(user)
  const logout = useLogout()
  const navigate = useNavigate()

  const isActive = (to: string) =>
    to === '/admin' ? pathname === '/admin' || pathname === '/admin/' : pathname.startsWith(to)

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 flex-row items-center justify-between gap-2 px-3 group-data-[collapsible=icon]:px-2">
        <Link to="/" className="flex min-w-0 flex-1 items-center gap-2 group-data-[collapsible=icon]:hidden" onClick={() => { if (isMobile) setOpenMobile(false) }}>
          <HomeIcon className="size-4 shrink-0" />
          <span className="truncate font-heading text-base font-semibold">Super Fab Lab</span>
        </Link>
        <SidebarTrigger aria-label={isMobile ? 'Close navigation' : state === 'expanded' ? 'Collapse navigation' : 'Expand navigation'} />
      </SidebarHeader>
      <SidebarContent>
        {GROUPS.map((group) => {
          const groupItems = items.filter((item) => item.group === group)
          if (!groupItems.length) return null
          return (
            <SidebarGroup key={group}>
              <SidebarGroupLabel>{group}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {groupItems.map((item) => (
                    <SidebarMenuItem key={item.to}>
                      <SidebarMenuButton
                        isActive={isActive(item.to)}
                        tooltip={item.label}
                        onClick={() => { if (isMobile) setOpenMobile(false) }}
                        render={<Link to={item.to} />}
                      >
                        <item.icon />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )
        })}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton render={<Link to="/me" />} tooltip="My profile" isActive={pathname === '/me'} onClick={() => { if (isMobile) setOpenMobile(false) }}>
              <UserRoundIcon />
              <span className="flex flex-col leading-tight">
                <span>{user.display_name}</span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="Log out"
              onClick={() =>
                logout.mutate(undefined, {
                  onError: (error) =>
                    toast.error(
                      `Logged out on this screen, but the server did not confirm: ${errorMessage(error)}`,
                    ),
                  onSettled: () => navigate({ to: '/' }),
                })
              }
            >
              <LogOutIcon />
              <span>Log out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
