import { UserIcon } from 'lucide-react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'

interface UserAvatarProps {
  name: string
  url: string | null | undefined
  size?: 'sm' | 'default' | 'lg'
  className?: string
}

export function UserAvatar({ name, url, size = 'default', className }: UserAvatarProps) {
  return (
    <Avatar size={size} className={className}>
      {url ? <AvatarImage src={url} alt="" /> : null}
      <AvatarFallback aria-label={`${name} has no photo`}>
        <UserIcon aria-hidden className="size-1/2" />
      </AvatarFallback>
    </Avatar>
  )
}
