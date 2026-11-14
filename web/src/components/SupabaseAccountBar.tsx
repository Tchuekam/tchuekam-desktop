import { useEffect, useState } from "react";
import { LogIn, LogOut, UserCheck, ExternalLink } from "lucide-react";
import {
  fetchSupabaseUser,
  getAuthPortalUrl,
  signOutSupabase,
  type SupabaseUserInfo,
} from "@/lib/supabaseAuth";
import { cn } from "@/lib/utils";

export function SupabaseAccountBar() {
  const [account, setAccount] = useState<SupabaseUserInfo | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let active = true;
    const syncAccount = () => {
      fetchSupabaseUser().then((user) => {
        if (!active) return;
        setAccount(user);
        setChecked(true);
      });
    };

    syncAccount();
    const interval = window.setInterval(syncAccount, 4 * 60 * 1000);
    const onFocus = () => syncAccount();
    window.addEventListener("focus", onFocus);

    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  if (!checked) return null;

  if (!account) {
    return (
      <div className="mx-3 mb-2 rounded border border-current/15 bg-current/[0.03] px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="font-mondwest text-display text-[11px] uppercase tracking-[0.08em] text-text-secondary">
              ☤ Tchuekam Account
            </div>
            <div className="truncate text-[10px] text-text-tertiary">
              Sync workspace & tracking
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <a
              href={getAuthPortalUrl("/login")}
              className={cn(
                "inline-flex items-center gap-1 rounded border border-current/25 px-2 py-1",
                "font-mondwest text-display text-[10px] uppercase tracking-[0.08em]",
                "text-midground transition-colors hover:bg-current/10",
              )}
            >
              <LogIn className="h-3 w-3" />
              <span>Sign In</span>
            </a>
            <a
              href={getAuthPortalUrl("/register")}
              className={cn(
                "inline-flex items-center rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1",
                "font-mondwest text-display text-[10px] uppercase tracking-[0.08em]",
                "text-amber-300 transition-colors hover:bg-amber-500/20",
              )}
            >
              Join
            </a>
          </div>
        </div>
      </div>
    );
  }

  const label =
    account.user_metadata?.full_name ||
    account.user_metadata?.username ||
    account.email;

  return (
    <div className="mx-3 mb-2 rounded border border-emerald-500/25 bg-emerald-500/[0.06] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <UserCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
          <div className="min-w-0">
            <div className="truncate text-xs font-medium text-text-primary">
              {label}
            </div>
            <div className="truncate text-[10px] text-text-tertiary">
              {account.email}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <a
            href={getAuthPortalUrl("/")}
            target="_blank"
            rel="noopener noreferrer"
            title="Open Tchuekam Auth Console"
            className="rounded p-1 text-text-tertiary transition-colors hover:bg-current/10 hover:text-midground"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
          <button
            type="button"
            onClick={async () => {
              await signOutSupabase();
              setAccount(null);
            }}
            title="Sign out of Tchuekam Account"
            className="rounded p-1 text-text-tertiary transition-colors hover:bg-destructive/15 hover:text-destructive cursor-pointer"
          >
            <LogOut className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
