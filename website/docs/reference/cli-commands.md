---
sidebar_position: 1
title: "CLI Commands Reference"
description: "Authoritative reference for Bull Whip terminal commands and command families"
---

# CLI Commands Reference

This page covers the **terminal commands** you run from your shell.

For in-chat slash commands, see [Slash Commands Reference](./slash-commands.md).

## Global entrypoint

```bash
bullwhip [global-options] <command> [subcommand/options]
```

### Global options

| Option | Description |
|--------|-------------|
| `--version`, `-V` | Show version and exit. |
| `--profile <name>`, `-p <name>` | Select which Bull Whip profile to use for this invocation. Overrides the sticky default set by `bullwhip profile use`. |
| `--resume <session>`, `-r <session>` | Resume a previous session by ID or title. |
| `--continue [name]`, `-c [name]` | Resume the most recent session, or the most recent session matching a title. |
| `--worktree`, `-w` | Start in an isolated git worktree for parallel-agent workflows. |
| `--yolo` | Bypass dangerous-command approval prompts. |
| `--pass-session-id` | Include the session ID in the agent's system prompt. |

## Top-level commands

| Command | Purpose |
|---------|---------|
| `bullwhip chat` | Interactive or one-shot chat with the agent. |
| `bullwhip model` | Interactively choose the default provider and model. |
| `bullwhip gateway` | Run or manage the messaging gateway service. |
| `bullwhip setup` | Interactive setup wizard for all or part of the configuration. |
| `bullwhip whatsapp` | Configure and pair the WhatsApp bridge. |
| `bullwhip auth` | Manage credentials — add, list, remove, reset, set strategy. Handles OAuth flows for Codex/Nous/Anthropic. |
| `bullwhip login` / `logout` | **Deprecated** — use `bullwhip auth` instead. |
| `bullwhip status` | Show agent, auth, and platform status. |
| `bullwhip cron` | Inspect and tick the cron scheduler. |
| `bullwhip webhook` | Manage dynamic webhook subscriptions for event-driven activation. |
| `bullwhip doctor` | Diagnose config and dependency issues. |
| `bullwhip dump` | Copy-pasteable setup summary for support/debugging. |
| `bullwhip debug` | Debug tools — upload logs and system info for support. |
| `bullwhip backup` | Back up Bull Whip home directory to a zip file. |
| `bullwhip import` | Restore a Bull Whip backup from a zip file. |
| `bullwhip logs` | View, tail, and filter agent/gateway/error log files. |
| `bullwhip config` | Show, edit, migrate, and query configuration files. |
| `bullwhip pairing` | Approve or revoke messaging pairing codes. |
| `bullwhip skills` | Browse, install, publish, audit, and configure skills. |
| `bullwhip honcho` | Manage Honcho cross-session memory integration. |
| `bullwhip memory` | Configure external memory provider. |
| `bullwhip acp` | Run Bull Whip as an ACP server for editor integration. |
| `bullwhip mcp` | Manage MCP server configurations and run Bull Whip as an MCP server. |
| `bullwhip plugins` | Manage Bull Whip Agent plugins (install, enable, disable, remove). |
| `bullwhip tools` | Configure enabled tools per platform. |
| `bullwhip sessions` | Browse, export, prune, rename, and delete sessions. |
| `bullwhip insights` | Show token/cost/activity analytics. |
| `bullwhip claw` | OpenClaw migration helpers. |
| `bullwhip dashboard` | Launch the web dashboard for managing config, API keys, and sessions. |
| `bullwhip debug` | Debug tools — upload logs and system info for support. |
| `bullwhip backup` | Back up Bull Whip home directory to a zip file. |
| `bullwhip import` | Restore a Bull Whip backup from a zip file. |
| `bullwhip profile` | Manage profiles — multiple isolated Bull Whip instances. |
| `bullwhip completion` | Print shell completion scripts (bash/zsh). |
| `bullwhip version` | Show version information. |
| `bullwhip update` | Pull latest code and reinstall dependencies. |
| `bullwhip uninstall` | Remove Bull Whip from the system. |

## `bullwhip chat`

```bash
bullwhip chat [options]
```

Common options:

| Option | Description |
|--------|-------------|
| `-q`, `--query "..."` | One-shot, non-interactive prompt. |
| `-m`, `--model <model>` | Override the model for this run. |
| `-t`, `--toolsets <csv>` | Enable a comma-separated set of toolsets. |
| `--provider <provider>` | Force a provider: `auto`, `openrouter`, `nous`, `openai-codex`, `copilot-acp`, `copilot`, `anthropic`, `gemini`, `huggingface`, `zai`, `kimi-coding`, `minimax`, `minimax-cn`, `kilocode`, `xiaomi`, `arcee`. |
| `-s`, `--skills <name>` | Preload one or more skills for the session (can be repeated or comma-separated). |
| `-v`, `--verbose` | Verbose output. |
| `-Q`, `--quiet` | Programmatic mode: suppress banner/spinner/tool previews. |
| `--image <path>` | Attach a local image to a single query. |
| `--resume <session>` / `--continue [name]` | Resume a session directly from `chat`. |
| `--worktree` | Create an isolated git worktree for this run. |
| `--checkpoints` | Enable filesystem checkpoints before destructive file changes. |
| `--yolo` | Skip approval prompts. |
| `--pass-session-id` | Pass the session ID into the system prompt. |
| `--source <tag>` | Session source tag for filtering (default: `cli`). Use `tool` for third-party integrations that should not appear in user session lists. |
| `--max-turns <N>` | Maximum tool-calling iterations per conversation turn (default: 90, or `agent.max_turns` in config). |

Examples:

```bash
bullwhip
bullwhip chat -q "Summarize the latest PRs"
bullwhip chat --provider openrouter --model anthropic/claude-sonnet-4.6
bullwhip chat --toolsets web,terminal,skills
bullwhip chat --quiet -q "Return only JSON"
bullwhip chat --worktree -q "Review this repo and open a PR"
```

## `bullwhip model`

Interactive provider + model selector.

```bash
bullwhip model
```

Use this when you want to:
- switch default providers
- log into OAuth-backed providers during model selection
- pick from provider-specific model lists
- configure a custom/self-hosted endpoint
- save the new default into config

### `/model` slash command (mid-session)

Switch models without leaving a session:

```
/model                              # Show current model and available options
/model claude-sonnet-4              # Switch model (auto-detects provider)
/model zai:glm-5                    # Switch provider and model
/model custom:qwen-2.5              # Use model on your custom endpoint
/model custom                       # Auto-detect model from custom endpoint
/model custom:local:qwen-2.5        # Use a named custom provider
/model openrouter:anthropic/claude-sonnet-4  # Switch back to cloud
```

Provider and base URL changes are persisted to `config.yaml` automatically. When switching away from a custom endpoint, the stale base URL is cleared to prevent it leaking into other providers.

## `bullwhip gateway`

```bash
bullwhip gateway <subcommand>
```

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `run` | Run the gateway in the foreground. Recommended for WSL, Docker, and Termux. |
| `start` | Start the installed systemd/launchd background service. |
| `stop` | Stop the service (or foreground process). |
| `restart` | Restart the service. |
| `status` | Show service status. |
| `install` | Install as a systemd (Linux) or launchd (macOS) background service. |
| `uninstall` | Remove the installed service. |
| `setup` | Interactive messaging-platform setup. |

:::tip WSL users
Use `bullwhip gateway run` instead of `bullwhip gateway start` — WSL's systemd support is unreliable. Wrap it in tmux for persistence: `tmux new -s bullwhip 'bullwhip gateway run'`. See [WSL FAQ](/docs/reference/faq#wsl-gateway-keeps-disconnecting-or-bullwhip-gateway-start-fails) for details.
:::

## `bullwhip setup`

```bash
bullwhip setup [model|tts|terminal|gateway|tools|agent] [--non-interactive] [--reset]
```

Use the full wizard or jump into one section:

| Section | Description |
|---------|-------------|
| `model` | Provider and model setup. |
| `terminal` | Terminal backend and sandbox setup. |
| `gateway` | Messaging platform setup. |
| `tools` | Enable/disable tools per platform. |
| `agent` | Agent behavior settings. |

Options:

| Option | Description |
|--------|-------------|
| `--non-interactive` | Use defaults / environment values without prompts. |
| `--reset` | Reset configuration to defaults before setup. |

## `bullwhip whatsapp`

```bash
bullwhip whatsapp
```

Runs the WhatsApp pairing/setup flow, including mode selection and QR-code pairing.

## `bullwhip login` / `bullwhip logout` *(Deprecated)*

:::caution
`bullwhip login` has been removed. Use `bullwhip auth` to manage OAuth credentials, `bullwhip model` to select a provider, or `bullwhip setup` for full interactive setup.
:::

## `bullwhip auth`

Manage credential pools for same-provider key rotation. See [Credential Pools](/docs/user-guide/features/credential-pools) for full documentation.

```bash
bullwhip auth                                              # Interactive wizard
bullwhip auth list                                         # Show all pools
bullwhip auth list openrouter                              # Show specific provider
bullwhip auth add openrouter --api-key sk-or-v1-xxx        # Add API key
bullwhip auth add anthropic --type oauth                   # Add OAuth credential
bullwhip auth remove openrouter 2                          # Remove by index
bullwhip auth reset openrouter                             # Clear cooldowns
```

Subcommands: `add`, `list`, `remove`, `reset`. When called with no subcommand, launches the interactive management wizard.

## `bullwhip status`

```bash
bullwhip status [--all] [--deep]
```

| Option | Description |
|--------|-------------|
| `--all` | Show all details in a shareable redacted format. |
| `--deep` | Run deeper checks that may take longer. |

## `bullwhip cron`

```bash
bullwhip cron <list|create|edit|pause|resume|run|remove|status|tick>
```

| Subcommand | Description |
|------------|-------------|
| `list` | Show scheduled jobs. |
| `create` / `add` | Create a scheduled job from a prompt, optionally attaching one or more skills via repeated `--skill`. |
| `edit` | Update a job's schedule, prompt, name, delivery, repeat count, or attached skills. Supports `--clear-skills`, `--add-skill`, and `--remove-skill`. |
| `pause` | Pause a job without deleting it. |
| `resume` | Resume a paused job and compute its next future run. |
| `run` | Trigger a job on the next scheduler tick. |
| `remove` | Delete a scheduled job. |
| `status` | Check whether the cron scheduler is running. |
| `tick` | Run due jobs once and exit. |

## `bullwhip webhook`

```bash
bullwhip webhook <subscribe|list|remove|test>
```

Manage dynamic webhook subscriptions for event-driven agent activation. Requires the webhook platform to be enabled in config — if not configured, prints setup instructions.

| Subcommand | Description |
|------------|-------------|
| `subscribe` / `add` | Create a webhook route. Returns the URL and HMAC secret to configure on your service. |
| `list` / `ls` | Show all agent-created subscriptions. |
| `remove` / `rm` | Delete a dynamic subscription. Static routes from config.yaml are not affected. |
| `test` | Send a test POST to verify a subscription is working. |

### `bullwhip webhook subscribe`

```bash
bullwhip webhook subscribe <name> [options]
```

| Option | Description |
|--------|-------------|
| `--prompt` | Prompt template with `{dot.notation}` payload references. |
| `--events` | Comma-separated event types to accept (e.g. `issues,pull_request`). Empty = all. |
| `--description` | Human-readable description. |
| `--skills` | Comma-separated skill names to load for the agent run. |
| `--deliver` | Delivery target: `log` (default), `telegram`, `discord`, `slack`, `github_comment`. |
| `--deliver-chat-id` | Target chat/channel ID for cross-platform delivery. |
| `--secret` | Custom HMAC secret. Auto-generated if omitted. |

Subscriptions persist to `~/.bullwhip/webhook_subscriptions.json` and are hot-reloaded by the webhook adapter without a gateway restart.

## `bullwhip doctor`

```bash
bullwhip doctor [--fix]
```

| Option | Description |
|--------|-------------|
| `--fix` | Attempt automatic repairs where possible. |

## `bullwhip dump`

```bash
bullwhip dump [--show-keys]
```

Outputs a compact, plain-text summary of your entire Bull Whip setup. Designed to be copy-pasted into Discord, GitHub issues, or Telegram when asking for support — no ANSI colors, no special formatting, just data.

| Option | Description |
|--------|-------------|
| `--show-keys` | Show redacted API key prefixes (first and last 4 characters) instead of just `set`/`not set`. |

### What it includes

| Section | Details |
|---------|---------|
| **Header** | Bull Whip version, release date, git commit hash |
| **Environment** | OS, Python version, OpenAI SDK version |
| **Identity** | Active profile name, BULLWHIP_HOME path |
| **Model** | Configured default model and provider |
| **Terminal** | Backend type (local, docker, ssh, etc.) |
| **API keys** | Presence check for all 22 provider/tool API keys |
| **Features** | Enabled toolsets, MCP server count, memory provider |
| **Services** | Gateway status, configured messaging platforms |
| **Workload** | Cron job counts, installed skill count |
| **Config overrides** | Any config values that differ from defaults |

### Example output

```
--- bullwhip dump ---
version:          0.8.0 (2026.4.8) [af4abd2f]
os:               Linux 6.14.0-37-generic x86_64
python:           3.11.14
openai_sdk:       2.24.0
profile:          default
bullwhip_home:      ~/.bullwhip
model:            anthropic/claude-opus-4.6
provider:         openrouter
terminal:         local

api_keys:
  openrouter           set
  openai               not set
  anthropic            set
  nous                 not set
  firecrawl            set
  ...

features:
  toolsets:           all
  mcp_servers:        0
  memory_provider:    built-in
  gateway:            running (systemd)
  platforms:          telegram, discord
  cron_jobs:          3 active / 5 total
  skills:             42

config_overrides:
  agent.max_turns: 250
  compression.threshold: 0.85
  display.streaming: True
--- end dump ---
```

### When to use

- Reporting a bug on GitHub — paste the dump into your issue
- Asking for help in Discord — share it in a code block
- Comparing your setup to someone else's
- Quick sanity check when something isn't working

:::tip
`bullwhip dump` is specifically designed for sharing. For interactive diagnostics, use `bullwhip doctor`. For a visual overview, use `bullwhip status`.
:::

## `bullwhip debug`

```bash
bullwhip debug share [options]
```

Upload a debug report (system info + recent logs) to a paste service and get a shareable URL. Useful for quick support requests — includes everything a helper needs to diagnose your issue.

| Option | Description |
|--------|-------------|
| `--lines <N>` | Number of log lines to include per log file (default: 200). |
| `--expire <days>` | Paste expiry in days (default: 7). |
| `--local` | Print the report locally instead of uploading. |

The report includes system info (OS, Python version, Bull Whip version), recent agent and gateway logs (512 KB limit per file), and redacted API key status. Keys are always redacted — no secrets are uploaded.

Paste services tried in order: paste.rs, dpaste.com.

### Examples

```bash
bullwhip debug share              # Upload debug report, print URL
bullwhip debug share --lines 500  # Include more log lines
bullwhip debug share --expire 30  # Keep paste for 30 days
bullwhip debug share --local      # Print report to terminal (no upload)
```

## `bullwhip backup`

```bash
bullwhip backup [options]
```

Create a zip archive of your Bull Whip configuration, skills, sessions, and data. The backup excludes the bullwhip-agent codebase itself.

| Option | Description |
|--------|-------------|
| `-o`, `--output <path>` | Output path for the zip file (default: `~/bullwhip-backup-<timestamp>.zip`). |
| `-q`, `--quick` | Quick snapshot: only critical state files (config.yaml, state.db, .env, auth, cron jobs). Much faster than a full backup. |
| `-l`, `--label <name>` | Label for the snapshot (only used with `--quick`). |

The backup uses SQLite's `backup()` API for safe copying, so it works correctly even when Bull Whip is running (WAL-mode safe).

### Examples

```bash
bullwhip backup                           # Full backup to ~/bullwhip-backup-*.zip
bullwhip backup -o /tmp/bullwhip.zip        # Full backup to specific path
bullwhip backup --quick                   # Quick state-only snapshot
bullwhip backup --quick --label "pre-upgrade"  # Quick snapshot with label
```

## `bullwhip import`

```bash
bullwhip import <zipfile> [options]
```

Restore a previously created Bull Whip backup into your Bull Whip home directory.

| Option | Description |
|--------|-------------|
| `-f`, `--force` | Overwrite existing files without confirmation. |

## `bullwhip logs`

```bash
bullwhip logs [log_name] [options]
```

View, tail, and filter Bull Whip log files. All logs are stored in `~/.bullwhip/logs/` (or `<profile>/logs/` for non-default profiles).

### Log files

| Name | File | What it captures |
|------|------|-----------------|
| `agent` (default) | `agent.log` | All agent activity — API calls, tool dispatch, session lifecycle (INFO and above) |
| `errors` | `errors.log` | Warnings and errors only — a filtered subset of agent.log |
| `gateway` | `gateway.log` | Messaging gateway activity — platform connections, message dispatch, webhook events |

### Options

| Option | Description |
|--------|-------------|
| `log_name` | Which log to view: `agent` (default), `errors`, `gateway`, or `list` to show available files with sizes. |
| `-n`, `--lines <N>` | Number of lines to show (default: 50). |
| `-f`, `--follow` | Follow the log in real time, like `tail -f`. Press Ctrl+C to stop. |
| `--level <LEVEL>` | Minimum log level to show: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `--session <ID>` | Filter lines containing a session ID substring. |
| `--since <TIME>` | Show lines from a relative time ago: `30m`, `1h`, `2d`, etc. Supports `s` (seconds), `m` (minutes), `h` (hours), `d` (days). |
| `--component <NAME>` | Filter by component: `gateway`, `agent`, `tools`, `cli`, `cron`. |

### Examples

```bash
# View the last 50 lines of agent.log (default)
bullwhip logs

# Follow agent.log in real time
bullwhip logs -f

# View the last 100 lines of gateway.log
bullwhip logs gateway -n 100

# Show only warnings and errors from the last hour
bullwhip logs --level WARNING --since 1h

# Filter by a specific session
bullwhip logs --session abc123

# Follow errors.log, starting from 30 minutes ago
bullwhip logs errors --since 30m -f

# List all log files with their sizes
bullwhip logs list
```

### Filtering

Filters can be combined. When multiple filters are active, a log line must pass **all** of them to be shown:

```bash
# WARNING+ lines from the last 2 hours containing session "tg-12345"
bullwhip logs --level WARNING --since 2h --session tg-12345
```

Lines without a parseable timestamp are included when `--since` is active (they may be continuation lines from a multi-line log entry). Lines without a detectable level are included when `--level` is active.

### Log rotation

Bull Whip uses Python's `RotatingFileHandler`. Old logs are rotated automatically — look for `agent.log.1`, `agent.log.2`, etc. The `bullwhip logs list` subcommand shows all log files including rotated ones.

## `bullwhip config`

```bash
bullwhip config <subcommand>
```

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `show` | Show current config values. |
| `edit` | Open `config.yaml` in your editor. |
| `set <key> <value>` | Set a config value. |
| `path` | Print the config file path. |
| `env-path` | Print the `.env` file path. |
| `check` | Check for missing or stale config. |
| `migrate` | Add newly introduced options interactively. |

## `bullwhip pairing`

```bash
bullwhip pairing <list|approve|revoke|clear-pending>
```

| Subcommand | Description |
|------------|-------------|
| `list` | Show pending and approved users. |
| `approve <platform> <code>` | Approve a pairing code. |
| `revoke <platform> <user-id>` | Revoke a user's access. |
| `clear-pending` | Clear pending pairing codes. |

## `bullwhip skills`

```bash
bullwhip skills <subcommand>
```

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `browse` | Paginated browser for skill registries. |
| `search` | Search skill registries. |
| `install` | Install a skill. |
| `inspect` | Preview a skill without installing it. |
| `list` | List installed skills. |
| `check` | Check installed hub skills for upstream updates. |
| `update` | Reinstall hub skills with upstream changes when available. |
| `audit` | Re-scan installed hub skills. |
| `uninstall` | Remove a hub-installed skill. |
| `publish` | Publish a skill to a registry. |
| `snapshot` | Export/import skill configurations. |
| `tap` | Manage custom skill sources. |
| `config` | Interactive enable/disable configuration for skills by platform. |

Common examples:

```bash
bullwhip skills browse
bullwhip skills browse --source official
bullwhip skills search react --source skills-sh
bullwhip skills search https://mintlify.com/docs --source well-known
bullwhip skills inspect official/security/1password
bullwhip skills inspect skills-sh/vercel-labs/json-render/json-render-react
bullwhip skills install official/migration/openclaw-migration
bullwhip skills install skills-sh/anthropics/skills/pdf --force
bullwhip skills check
bullwhip skills update
bullwhip skills config
```

Notes:
- `--force` can override non-dangerous policy blocks for third-party/community skills.
- `--force` does not override a `dangerous` scan verdict.
- `--source skills-sh` searches the public `skills.sh` directory.
- `--source well-known` lets you point Bull Whip at a site exposing `/.well-known/skills/index.json`.

## `bullwhip honcho`

```bash
bullwhip honcho [--target-profile NAME] <subcommand>
```

Manage Honcho cross-session memory integration. This command is provided by the Honcho memory provider plugin and is only available when `memory.provider` is set to `honcho` in your config.

The `--target-profile` flag lets you manage another profile's Honcho config without switching to it.

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `setup` | Redirects to `bullwhip memory setup` (unified setup path). |
| `status [--all]` | Show current Honcho config and connection status. `--all` shows a cross-profile overview. |
| `peers` | Show peer identities across all profiles. |
| `sessions` | List known Honcho session mappings. |
| `map [name]` | Map the current directory to a Honcho session name. Omit `name` to list current mappings. |
| `peer` | Show or update peer names and dialectic reasoning level. Options: `--user NAME`, `--ai NAME`, `--reasoning LEVEL`. |
| `mode [mode]` | Show or set recall mode: `hybrid`, `context`, or `tools`. Omit to show current. |
| `tokens` | Show or set token budgets for context and dialectic. Options: `--context N`, `--dialectic N`. |
| `identity [file] [--show]` | Seed or show the AI peer identity representation. |
| `enable` | Enable Honcho for the active profile. |
| `disable` | Disable Honcho for the active profile. |
| `sync` | Sync Honcho config to all existing profiles (creates missing host blocks). |
| `migrate` | Step-by-step migration guide from openclaw-honcho to Bull Whip Honcho. |

## `bullwhip memory`

```bash
bullwhip memory <subcommand>
```

Set up and manage external memory provider plugins. Available providers: honcho, openviking, mem0, hindsight, holographic, retaindb, byterover, supermemory. Only one external provider can be active at a time. Built-in memory (MEMORY.md/USER.md) is always active.

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `setup` | Interactive provider selection and configuration. |
| `status` | Show current memory provider config. |
| `off` | Disable external provider (built-in only). |

## `bullwhip acp`

```bash
bullwhip acp
```

Starts Bull Whip as an ACP (Agent Client Protocol) stdio server for editor integration.

Related entrypoints:

```bash
bullwhip-acp
python -m acp_adapter
```

Install support first:

```bash
pip install -e '.[acp]'
```

See [ACP Editor Integration](../user-guide/features/acp.md) and [ACP Internals](../developer-guide/acp-internals.md).

## `bullwhip mcp`

```bash
bullwhip mcp <subcommand>
```

Manage MCP (Model Context Protocol) server configurations and run Bull Whip as an MCP server.

| Subcommand | Description |
|------------|-------------|
| `serve [-v\|--verbose]` | Run Bull Whip as an MCP server — expose conversations to other agents. |
| `add <name> [--url URL] [--command CMD] [--args ...] [--auth oauth\|header]` | Add an MCP server with automatic tool discovery. |
| `remove <name>` (alias: `rm`) | Remove an MCP server from config. |
| `list` (alias: `ls`) | List configured MCP servers. |
| `test <name>` | Test connection to an MCP server. |
| `configure <name>` (alias: `config`) | Toggle tool selection for a server. |

See [MCP Config Reference](./mcp-config-reference.md), [Use MCP with Bull Whip](../guides/use-mcp-with-bullwhip.md), and [MCP Server Mode](../user-guide/features/mcp.md#running-bullwhip-as-an-mcp-server).

## `bullwhip plugins`

```bash
bullwhip plugins [subcommand]
```

Unified plugin management — general plugins, memory providers, and context engines in one place. Running `bullwhip plugins` with no subcommand opens a composite interactive screen with two sections:

- **General Plugins** — multi-select checkboxes to enable/disable installed plugins
- **Provider Plugins** — single-select configuration for Memory Provider and Context Engine. Press ENTER on a category to open a radio picker.

| Subcommand | Description |
|------------|-------------|
| *(none)* | Composite interactive UI — general plugin toggles + provider plugin configuration. |
| `install <identifier> [--force]` | Install a plugin from a Git URL or `owner/repo`. |
| `update <name>` | Pull latest changes for an installed plugin. |
| `remove <name>` (aliases: `rm`, `uninstall`) | Remove an installed plugin. |
| `enable <name>` | Enable a disabled plugin. |
| `disable <name>` | Disable a plugin without removing it. |
| `list` (alias: `ls`) | List installed plugins with enabled/disabled status. |

Provider plugin selections are saved to `config.yaml`:
- `memory.provider` — active memory provider (empty = built-in only)
- `context.engine` — active context engine (`"compressor"` = built-in default)

General plugin disabled list is stored in `config.yaml` under `plugins.disabled`.

See [Plugins](../user-guide/features/plugins.md) and [Build a Bull Whip Plugin](../guides/build-a-bullwhip-plugin.md).

## `bullwhip tools`

```bash
bullwhip tools [--summary]
```

| Option | Description |
|--------|-------------|
| `--summary` | Print the current enabled-tools summary and exit. |

Without `--summary`, this launches the interactive per-platform tool configuration UI.

## `bullwhip sessions`

```bash
bullwhip sessions <subcommand>
```

Subcommands:

| Subcommand | Description |
|------------|-------------|
| `list` | List recent sessions. |
| `browse` | Interactive session picker with search and resume. |
| `export <output> [--session-id ID]` | Export sessions to JSONL. |
| `delete <session-id>` | Delete one session. |
| `prune` | Delete old sessions. |
| `stats` | Show session-store statistics. |
| `rename <session-id> <title>` | Set or change a session title. |

## `bullwhip insights`

```bash
bullwhip insights [--days N] [--source platform]
```

| Option | Description |
|--------|-------------|
| `--days <n>` | Analyze the last `n` days (default: 30). |
| `--source <platform>` | Filter by source such as `cli`, `telegram`, or `discord`. |

## `bullwhip claw`

```bash
bullwhip claw migrate [options]
```

Migrate your OpenClaw setup to Bull Whip. Reads from `~/.openclaw` (or a custom path) and writes to `~/.bullwhip`. Automatically detects legacy directory names (`~/.clawdbot`, `~/.moltbot`) and config filenames (`clawdbot.json`, `moltbot.json`).

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview what would be migrated without writing anything. |
| `--preset <name>` | Migration preset: `full` (default, includes secrets) or `user-data` (excludes API keys). |
| `--overwrite` | Overwrite existing Bull Whip files on conflicts (default: skip). |
| `--migrate-secrets` | Include API keys in migration (enabled by default with `--preset full`). |
| `--source <path>` | Custom OpenClaw directory (default: `~/.openclaw`). |
| `--workspace-target <path>` | Target directory for workspace instructions (AGENTS.md). |
| `--skill-conflict <mode>` | Handle skill name collisions: `skip` (default), `overwrite`, or `rename`. |
| `--yes` | Skip the confirmation prompt. |

### What gets migrated

The migration covers 30+ categories across persona, memory, skills, model providers, messaging platforms, agent behavior, session policies, MCP servers, TTS, and more. Items are either **directly imported** into Bull Whip equivalents or **archived** for manual review.

**Directly imported:** SOUL.md, MEMORY.md, USER.md, AGENTS.md, skills (4 source directories), default model, custom providers, MCP servers, messaging platform tokens and allowlists (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Mattermost), agent defaults (reasoning effort, compression, human delay, timezone, sandbox), session reset policies, approval rules, TTS config, browser settings, tool settings, exec timeout, command allowlist, gateway config, and API keys from 3 sources.

**Archived for manual review:** Cron jobs, plugins, hooks/webhooks, memory backend (QMD), skills registry config, UI/identity, logging, multi-agent setup, channel bindings, IDENTITY.md, TOOLS.md, HEARTBEAT.md, BOOTSTRAP.md.

**API key resolution** checks three sources in priority order: config values → `~/.openclaw/.env` → `auth-profiles.json`. All token fields handle plain strings, env templates (`${VAR}`), and SecretRef objects.

For the complete config key mapping, SecretRef handling details, and post-migration checklist, see the **[full migration guide](../guides/migrate-from-openclaw.md)**.

### Examples

```bash
# Preview what would be migrated
bullwhip claw migrate --dry-run

# Full migration including API keys
bullwhip claw migrate --preset full

# Migrate user data only (no secrets), overwrite conflicts
bullwhip claw migrate --preset user-data --overwrite

# Migrate from a custom OpenClaw path
bullwhip claw migrate --source /home/user/old-openclaw
```

## `bullwhip dashboard`

```bash
bullwhip dashboard [options]
```

Launch the web dashboard — a browser-based UI for managing configuration, API keys, and monitoring sessions. Requires `pip install bullwhip-agent[web]` (FastAPI + Uvicorn). See [Web Dashboard](/docs/user-guide/features/web-dashboard) for full documentation.

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | `9119` | Port to run the web server on |
| `--host` | `127.0.0.1` | Bind address |
| `--no-open` | — | Don't auto-open the browser |

```bash
# Default — opens browser to http://127.0.0.1:9119
bullwhip dashboard

# Custom port, no browser
bullwhip dashboard --port 8080 --no-open
```

## `bullwhip profile`

```bash
bullwhip profile <subcommand>
```

Manage profiles — multiple isolated Bull Whip instances, each with its own config, sessions, skills, and home directory.

| Subcommand | Description |
|------------|-------------|
| `list` | List all profiles. |
| `use <name>` | Set a sticky default profile. |
| `create <name> [--clone] [--clone-all] [--clone-from <source>] [--no-alias]` | Create a new profile. `--clone` copies config, `.env`, and `SOUL.md` from the active profile. `--clone-all` copies all state. `--clone-from` specifies a source profile. |
| `delete <name> [-y]` | Delete a profile. |
| `show <name>` | Show profile details (home directory, config, etc.). |
| `alias <name> [--remove] [--name NAME]` | Manage wrapper scripts for quick profile access. |
| `rename <old> <new>` | Rename a profile. |
| `export <name> [-o FILE]` | Export a profile to a `.tar.gz` archive. |
| `import <archive> [--name NAME]` | Import a profile from a `.tar.gz` archive. |

Examples:

```bash
bullwhip profile list
bullwhip profile create work --clone
bullwhip profile use work
bullwhip profile alias work --name h-work
bullwhip profile export work -o work-backup.tar.gz
bullwhip profile import work-backup.tar.gz --name restored
bullwhip -p work chat -q "Hello from work profile"
```

## `bullwhip completion`

```bash
bullwhip completion [bash|zsh]
```

Print a shell completion script to stdout. Source the output in your shell profile for tab-completion of Bull Whip commands, subcommands, and profile names.

Examples:

```bash
# Bash
bullwhip completion bash >> ~/.bashrc

# Zsh
bullwhip completion zsh >> ~/.zshrc
```

## Maintenance commands

| Command | Description |
|---------|-------------|
| `bullwhip version` | Print version information. |
| `bullwhip update` | Pull latest changes and reinstall dependencies. |
| `bullwhip uninstall [--full] [--yes]` | Remove Bull Whip, optionally deleting all config/data. |

## See also

- [Slash Commands Reference](./slash-commands.md)
- [CLI Interface](../user-guide/cli.md)
- [Sessions](../user-guide/sessions.md)
- [Skills System](../user-guide/features/skills.md)
- [Skins & Themes](../user-guide/features/skins.md)
