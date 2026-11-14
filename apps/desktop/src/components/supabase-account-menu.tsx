import { useEffect, useState } from 'react'

import { titlebarButtonClass } from '@/app/shell/titlebar'
import { Codicon } from '@/components/ui/codicon'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { triggerHaptic } from '@/lib/haptics'
import { Activity, CheckCircle2, ExternalLink } from '@/lib/icons'
import { fetchSupabaseUser, getAuthPortalUrl, signOutSupabase, type SupabaseUserInfo } from '@/lib/supabase-auth'
import { cn } from '@/lib/utils'

export function SupabaseAccountMenu() {
  const [account, setAccount] = useState<SupabaseUserInfo | null>(null)
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    let active = true

    const syncAccount = () => {
      void fetchSupabaseUser().then(user => {
        if (!active) {
          return
        }

        setAccount(user)
        setChecked(true)
      })
    }

    syncAccount()

    const interval = window.setInterval(syncAccount, 4 * 60 * 1000)
    const onFocus = () => syncAccount()

    window.addEventListener('focus', onFocus)

    return () => {
      active = false
      window.clearInterval(interval)
      window.removeEventListener('focus', onFocus)
    }
  }, [])

  const displayName =
    account?.user_metadata?.full_name || account?.user_metadata?.username || account?.email || 'Tchuekam Account'

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="Tchuekam Account"
          className={cn(
            titlebarButtonClass,
            'relative grid place-items-center bg-transparent select-none [&_svg]:size-4'
          )}
          onPointerDown={event => event.stopPropagation()}
          title={account ? `Signed in as ${account.email}` : 'Sign in or create Tchuekam account'}
          type="button"
        >
          <Codicon name="account" />
          {checked && (
            <span
              className={cn(
                'pointer-events-none absolute right-1 top-1 size-1.5 rounded-full',
                account ? 'bg-emerald-500' : 'bg-amber-500'
              )}
            />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64" sideOffset={8}>
        {account ? (
          <>
            <DropdownMenuLabel>
              <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />
                <span className="truncate">{displayName}</span>
              </div>
              <div className="mt-0.5 truncate text-xs font-normal text-muted-foreground">{account.email}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                triggerHaptic('open')
                window.location.assign(getAuthPortalUrl('/'))
              }}
            >
              <ExternalLink className="size-4" />
              <span>Account Portal</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                triggerHaptic('open')
                window.location.assign(getAuthPortalUrl('/tracking'))
              }}
            >
              <Activity className="size-4" />
              <span>Activity Tracking</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                triggerHaptic('tap')
                void signOutSupabase().then(() => setAccount(null))
              }}
            >
              <Codicon name="sign-out" size="1rem" />
              <span>Sign Out</span>
            </DropdownMenuItem>
          </>
        ) : (
          <>
            <DropdownMenuLabel>
              <div className="text-sm font-medium text-foreground">Tchuekam Account</div>
              <div className="mt-1 text-xs font-normal leading-4 text-muted-foreground">
                Sign in or register to sync your session and workspace activity.
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                triggerHaptic('open')
                window.location.assign(getAuthPortalUrl('/login'))
              }}
            >
              <Codicon name="sign-in" size="1rem" />
              <span>Sign In</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                triggerHaptic('open')
                window.location.assign(getAuthPortalUrl('/register'))
              }}
            >
              <Codicon name="account" size="1rem" />
              <span>Create Account</span>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
