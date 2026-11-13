import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'
import type { ComponentPropsWithoutRef, ElementType } from 'react'

const typographyVariants = cva('', {
  variants: {
    variant: {
      display:
        'font-heading text-4xl font-semibold tracking-tight text-balance sm:text-5xl xl:text-6xl',
      h1: 'font-heading text-2xl font-semibold tracking-tight text-balance',
      h2: 'font-heading text-lg font-semibold tracking-tight',
      h3: 'font-heading text-base font-semibold',
      h4: 'font-heading text-base font-medium',
      lead: 'text-lg text-muted-foreground text-pretty',
      body: 'text-sm leading-relaxed text-pretty',
      muted: 'text-sm text-muted-foreground text-pretty',
      small: 'text-xs text-muted-foreground',
      stat: 'font-heading text-3xl font-semibold tabular-nums',
    },
  },
  defaultVariants: { variant: 'body' },
})

const defaultElement: Record<NonNullable<TypographyProps['variant']>, ElementType> = {
  display: 'h1',
  h1: 'h1',
  h2: 'h2',
  h3: 'h3',
  h4: 'h4',
  lead: 'p',
  body: 'p',
  muted: 'p',
  small: 'p',
  stat: 'p',
}

type TypographyProps = VariantProps<typeof typographyVariants> & {
  as?: ElementType
} & ComponentPropsWithoutRef<'p'>

export function Typography({ variant = 'body', as, className, ...props }: TypographyProps) {
  const Component = as ?? defaultElement[variant ?? 'body']
  return <Component className={cn(typographyVariants({ variant }), className)} {...props} />
}
