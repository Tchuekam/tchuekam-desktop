---
sidebar_position: 4
---

# Running Many Gateways at Once

Operate multiple [profiles](./profiles.md) — each with its own bot tokens,
sessions, and memory — as managed services on a single machine. This page
covers the operational concerns: starting them all together, viewing logs
across profiles, preventing the host from sleeping, and recovering from common
launchd/systemd quirks.

If you only run one Tchuekam agent, you don't need this page — see
[Profiles](./profiles.md) for the basics.

## When to use this

You want this setup when you have two or more Tchuekam agents that should all
be online at the same time. Common reasons:

- A personal assistant on one Telegram bot and a coding agent on another
- One agent per family member or one per Slack workspace
- Sandbox + production instances of the same configuration
- A research agent + a writing agent + a cron-driven bot — each with isolated
  memory and skills

Every profile already gets its own per-platform LaunchAgent
(`ai.tchuekam.gateway-<name>.plist`) or systemd user service
(`tchuekam-gateway-<name>.service`). This guide adds the patterns for managing
them collectively.

## Quick start

```bash
# Create profiles (once)
tchuekam profile create coder
tchuekam profile create personal-bot
tchuekam profile create research

# Configure each
coder setup
personal-bot setup
research setup

# Install each gateway as a managed service
coder gateway install
personal-bot gateway install
research gateway install

# Start them all
coder gateway start
personal-bot gateway start
research gateway start
```

That's it — three independent agents, each on its own process, restarting
automatically on crash and on user login.

## Start, stop, or restart all gateways at once

The CLI ships with single-profile lifecycle commands. To act across every
profile, wrap them in a shell loop. Put the snippet below in
`~/.local/bin/tchuekam-gateways` and `chmod +x` it:

```sh
#!/bin/sh
set -eu

# Add or remove profile names here as you create / delete profiles.
profiles="default coder personal-bot research"

usage() {
  echo "Usage: tchuekam-gateways {start|stop|restart|status|list}"
}

run_for_profile() {
  profile="$1"
  action="$2"
  if [ "$profile" = "default" ]; then
    tchuekam gateway "$action"
  else
    tchuekam -p "$profile" gateway "$action"
  fi
}

action="${1:-}"
case "$action" in
  start|stop|restart|status)
    for profile in $profiles; do
      echo "==> $action $profile"
      run_for_profile "$profile" "$action"
    done
    ;;
  list)
    tchuekam gateway list
    ;;
  *)
    usage
    exit 2
    ;;
esac
```

Then:

```bash
tchuekam-gateways start      # start every configured profile
tchuekam-gateways stop       # stop every configured profile
tchuekam-gateways restart    # restart all
tchuekam-gateways status     # status across all
tchuekam-gateways list       # delegates to `tchuekam gateway list`
```

:::tip
The `default` profile is targeted with `tchuekam gateway <action>` (no `-p`),
not `tchuekam -p default gateway <action>`. The wrapper above handles both forms.
:::

## Manage one profile

The shortcut commands every profile installs:

```bash
coder gateway run        # foreground (Ctrl-C to stop)
coder gateway start      # start the managed service
coder gateway stop       # stop the managed service
coder gateway restart    # restart
coder gateway status     # status
coder gateway install    # create the LaunchAgent / systemd unit
coder gateway uninstall  # remove the service file
```

These are equivalent to `tchuekam -p coder gateway <action>` — useful if a
profile alias is not on `PATH` or if you target profiles dynamically from a
script.

## Service files

Each profile installs its own service with a unique name, so installations
never clash:

| Platform | Path                                                              |
| -------- | ----------------------------------------------------------------- |
| macOS    | `~/Library/LaunchAgents/ai.tchuekam.gateway-<profile>.plist`        |
| Linux    | `~/.config/systemd/user/tchuekam-gateway-<profile>.service`         |

The default profile keeps the historical names: `ai.tchuekam.gateway.plist` /
`tchuekam-gateway.service`.

## Viewing logs

Each profile writes to its own log files:

```bash
# Default profile
tail -f ~/.tchuekam/logs/gateway.log
tail -f ~/.tchuekam/logs/gateway.error.log

# Named profile
tail -f ~/.tchuekam/profiles/<name>/logs/gateway.log
tail -f ~/.tchuekam/profiles/<name>/logs/gateway.error.log
```

Stream every profile's log simultaneously:

```bash
tail -f ~/.tchuekam/logs/gateway.log ~/.tchuekam/profiles/*/logs/gateway.log
```

The CLI also has a structured log viewer:

```bash
tchuekam logs --tail              # follow default profile
tchuekam -p coder logs --tail     # follow one profile
tchuekam logs --help              # filters, levels, JSON output
```

## Identify what's actually running

```bash
tchuekam profile list             # profiles + model + gateway state
tchuekam-gateways status          # full status across every profile
launchctl list | grep tchuekam    # macOS — PIDs and labels
systemctl --user list-units 'tchuekam-gateway-*'   # Linux — units
```

## Editing configuration

Every profile keeps its config inside its own directory:

```
~/.tchuekam/profiles/<name>/
├── .env              # API keys, bot tokens (chmod 600)
├── config.yaml       # model, provider, toolsets, gateway settings
└── SOUL.md           # personality / system prompt
```

The default profile uses `~/.tchuekam/` directly with the same three files.

Edit them with any editor or via the CLI:

```bash
tchuekam config set model.model anthropic/claude-sonnet-4    # default profile
coder config set model.model openai/gpt-5                  # named profile
```

After editing `.env` or `config.yaml`, restart the affected gateway:

```bash
coder gateway restart
# or, for everything:
tchuekam-gateways restart
```

## Keeping the host awake

The gateway process can run all day, but the operating system will still try
to sleep when idle. Two patterns:

### macOS — `caffeinate`

`caffeinate` is built into macOS and prevents sleep while it runs. No install.

```bash
caffeinate -dis                    # block display, idle, and system sleep
caffeinate -dis -t 28800           # same, auto-exit after 8 hours
caffeinate -i -w $(cat ~/.tchuekam/gateway.pid) &   # awake while default gateway runs

# Persistent: run in background and forget
nohup caffeinate -dis >/dev/null 2>&1 &
disown

# Inspect / stop
pmset -g assertions | grep -iE 'caffeinate|prevent|user is active'
pkill caffeinate
```

| Flag   | Effect                                            |
| ------ | ------------------------------------------------- |
| `-d`   | block display sleep                               |
| `-i`   | block idle system sleep (default)                 |
| `-m`   | block disk sleep                                  |
| `-s`   | block system sleep (AC-powered Macs only)         |
| `-u`   | simulate user activity (prevents screen lock)     |
| `-t N` | auto-exit after `N` seconds                       |
| `-w P` | exit when PID `P` exits                           |

:::warning Lid-close still sleeps the Mac
`caffeinate` cannot override the hardware-driven lid-close sleep on MacBooks.
For lid-closed operation, change your Energy Saver / Battery preferences or
use a third-party tool.
:::

### Linux — `systemd-inhibit` or `loginctl`

```bash
# Inhibit suspend while a command runs
systemd-inhibit --what=idle:sleep --who=tchuekam --why="gateways running" \
  sleep infinity &

# Allow user services to keep running after logout (recommended)
sudo loginctl enable-linger "$USER"
```

After enabling lingering, your systemd user units (including
`tchuekam-gateway-<profile>.service`) continue running across SSH disconnects
and reboots.

## Token-conflict safety

Each profile must use unique bot tokens for each platform. If two profiles
share a Telegram, Discord, Slack, WhatsApp, or Signal token, the second
gateway refuses to start with an error naming the conflicting profile.

To audit:

```bash
grep -H 'TELEGRAM_BOT_TOKEN\|DISCORD_BOT_TOKEN' \
     ~/.tchuekam/.env ~/.tchuekam/profiles/*/.env
```

## Updating the code

`tchuekam update` pulls the latest code once and syncs new bundled skills into
every profile:

```bash
tchuekam update
tchuekam-gateways restart
```

User-modified skills are never overwritten.

## Troubleshooting

### "Could not find service in domain for user gui: 501"

You ran `tchuekam gateway start` after a previous `tchuekam gateway stop`. The
CLI's `stop` does a full `launchctl unload`, which removes the service from
launchd's registry. The CLI catches this specific error on `start` and
automatically re-loads the plist (`↻ launchd job was unloaded; reloading
service definition`). The service starts normally. Nothing to fix.

### Stale PID after a crash

If a profile's gateway shows `not running` but a process is still alive:

```bash
ps -ef | grep "tchuekam_cli.*-p <profile>"
cat ~/.tchuekam/profiles/<profile>/gateway.pid
kill -TERM <pid>          # graceful
kill -KILL <pid>          # if that fails after a few seconds
<profile> gateway start
```

### Forcing a hard reset of one service

```bash
# macOS
launchctl unload ~/Library/LaunchAgents/ai.tchuekam.gateway-<profile>.plist
launchctl load   ~/Library/LaunchAgents/ai.tchuekam.gateway-<profile>.plist

# Linux
systemctl --user restart tchuekam-gateway-<profile>.service
```

### Health check

```bash
tchuekam doctor                  # default profile
tchuekam -p <profile> doctor     # one profile
```
