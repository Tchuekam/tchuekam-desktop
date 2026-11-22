import { useStore } from '@nanostores/react'
import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { HermesGateway } from '@/hermes'
import { AlertTriangle, KeyRound, Loader2 } from '@/lib/icons'
import { notifyError } from '@/store/notifications'
import { $gatewayPrompt, clearGatewayPrompt } from '@/store/prompts'

interface GatewayPromptCardProps {
  gateway: HermesGateway | null
  sessionId: string | null
}

export function GatewayPromptCard({ gateway, sessionId }: GatewayPromptCardProps) {
  const prompt = useStore($gatewayPrompt)
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!prompt) {
    return null
  }

  if (prompt.sessionId && sessionId && prompt.sessionId !== sessionId) {
    return null
  }

  const sendApproval = async (choice: 'once' | 'session' | 'always' | 'deny') => {
    if (!gateway) {
      notifyError(new Error('TchuekaM gateway is not connected'), 'Could not send approval response')

      return
    }

    setSubmitting(true)

    try {
      await gateway.request('approval.respond', {
        choice,
        session_id: prompt.sessionId || sessionId || ''
      })
      clearGatewayPrompt({ sessionId: prompt.sessionId })
      setValue('')
    } catch (err) {
      notifyError(err, 'Approval response failed')
    } finally {
      setSubmitting(false)
    }
  }

  const submitSecretOrSudo = async (submittedValue: string) => {
    if (prompt.kind === 'approval') {
      return
    }

    if (!gateway) {
      notifyError(new Error('TchuekaM gateway is not connected'), 'Could not submit response')

      return
    }

    setSubmitting(true)

    try {
      if (prompt.kind === 'sudo') {
        await gateway.request('sudo.respond', {
          password: submittedValue,
          request_id: prompt.requestId
        })
      } else {
        await gateway.request('secret.respond', {
          request_id: prompt.requestId,
          value: submittedValue
        })
      }

      clearGatewayPrompt({ requestId: prompt.requestId })
      setValue('')
    } catch (err) {
      notifyError(err, 'Failed to submit prompt response')
    } finally {
      setSubmitting(false)
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()

    if (!submitting && value) {
      void submitSecretOrSudo(value)
    }
  }

  if (prompt.kind === 'approval') {
    return (
      <div className="tk-glass-elevated mx-auto mb-2.5 w-full max-w-3xl rounded-xl border-amber-500/35 p-4">
        <div className="flex items-start gap-2.5">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" />
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold text-foreground">Command approval required</div>
            <p className="mt-0.5 text-xs text-muted-foreground">{prompt.description}</p>
            {prompt.command && (
              <pre className="mt-2 max-h-28 overflow-auto rounded-lg border border-(--tk-glass-border) bg-(--ui-bg-tertiary) px-3 py-2 font-mono text-[0.75rem] text-foreground">
                {prompt.command}
              </pre>
            )}
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <Button disabled={submitting} onClick={() => void sendApproval('once')} size="sm" type="button">
                Allow once
              </Button>
              <Button
                disabled={submitting}
                onClick={() => void sendApproval('session')}
                size="sm"
                type="button"
                variant="outline"
              >
                Allow session
              </Button>
              <Button
                disabled={submitting}
                onClick={() => void sendApproval('always')}
                size="sm"
                type="button"
                variant="outline"
              >
                Always allow
              </Button>
              <Button
                disabled={submitting}
                onClick={() => void sendApproval('deny')}
                size="sm"
                type="button"
                variant="ghost"
              >
                Deny
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <form
      className="mx-auto mb-2 w-full max-w-3xl rounded-xl border border-(--ui-stroke-secondary) bg-card p-3.5 shadow-sm"
      onSubmit={handleSubmit}
    >
      <div className="flex items-start gap-2.5">
        <KeyRound className="mt-0.5 size-4 shrink-0 text-(--theme-primary)" />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold text-foreground">
            {prompt.kind === 'sudo' ? 'Sudo password requested' : `Secret required: ${prompt.envVar}`}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {prompt.kind === 'sudo'
              ? 'Enter password to authorize the elevated command.'
              : prompt.prompt || `Provide a value for ${prompt.envVar}.`}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              aria-label={prompt.kind === 'sudo' ? 'Sudo password' : prompt.envVar}
              autoComplete="off"
              className="h-8 min-w-0 flex-1 rounded-md border border-input bg-background px-2.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              disabled={submitting}
              onChange={event => setValue(event.target.value)}
              placeholder={prompt.kind === 'sudo' ? 'Sudo password…' : 'Enter secret value…'}
              type="password"
              value={value}
            />
            <Button disabled={submitting || !value} size="sm" type="submit">
              {submitting ? <Loader2 className="size-3.5 animate-spin" /> : null}
              Submit
            </Button>
            <Button
              disabled={submitting}
              onClick={() => void submitSecretOrSudo('')}
              size="sm"
              type="button"
              variant="ghost"
            >
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </form>
  )
}
