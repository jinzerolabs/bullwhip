# Changelog

All notable changes to Bull Whip Agent are documented here.
For full details, see each release note in the project root (`RELEASE_v*.md`).

---

## [v1.0.0] — 2026-04-16

> First stable release

- License changed to AGPL-3.0 (commercial use requires separate license)
- Project cleanup: removed stale planning docs, build artifacts, old branding assets
- Documentation: added CHANGELOG.md, TROUBLESHOOTING.md
- Configuration docs unified — all files clearly point to `~/.bullwhip/.env`
- Strengthened `.gitignore` for sensitive file protection

Based on v0.9.0 with all prior features included.

## [v0.9.0](RELEASE_v0.9.0.md) — 2026-04-13

> The everywhere release

- **Local Web Dashboard** — browser-based agent management UI
- **Fast Mode (`/fast`)** — priority processing for OpenAI & Anthropic
- **iMessage via BlueBubbles** — Apple messaging integration
- **WeChat & WeCom** — Chinese messaging ecosystem support
- **Termux / Android** — native mobile support
- **Background Process Monitoring** — `watch_patterns` for real-time alerts
- **Native xAI & Xiaomi MiMo** — first-class provider support
- **Pluggable Context Engine** — custom context management via plugins
- **Unified Proxy Support** — SOCKS, HTTP, system proxy auto-detection
- **Security Hardening** — path traversal, shell injection, SSRF, RCE fixes

487 commits · 269 PRs · 167 issues · 24 contributors

## [v0.8.0](RELEASE_v0.8.0.md) — 2026-04-08

> The intelligence release

- Background task auto-notifications
- Free MiMo v2 Pro on Nous Portal
- Live model switching across all platforms
- Self-optimized GPT/Codex guidance
- Native Google AI Studio provider
- Smart inactivity timeouts
- Approval buttons, MCP OAuth 2.1

209 PRs · 82 issues

## [v0.7.0](RELEASE_v0.7.0.md) — 2026-04-03

> The resilience release

- Pluggable memory providers
- Credential pool rotation
- Camofox anti-detection browser
- Inline diff previews
- Gateway hardening (race conditions, approval routing)
- Deep security fixes

168 PRs · 46 issues

## [v0.6.0](RELEASE_v0.6.0.md) — 2026-03-30

> The multi-instance release

- Profiles for isolated agent instances
- MCP server mode
- Docker container support
- Fallback provider chains
- Feishu/Lark and WeCom platforms
- Telegram webhook mode, Slack multi-workspace OAuth

95 PRs · 16 issues

## [v0.5.0](RELEASE_v0.5.0.md) — 2026-03-28

> The hardening release

- Hugging Face provider
- `/model` command overhaul
- Telegram Private Chat Topics
- Native Modal SDK
- Plugin lifecycle hooks
- Tool-use enforcement for GPT models
- Nix flake
- Supply chain audit

## [v0.4.0](RELEASE_v0.4.0.md) — 2026-03-23

> The platform expansion release

- OpenAI-compatible API server
- 6 new messaging adapters
- 4 new inference providers
- MCP server management with OAuth 2.1
- `@` context references
- Gateway prompt caching
- Streaming enabled by default

## [v0.3.0](RELEASE_v0.3.0.md) — 2026-03-17

> The streaming, plugins, and provider release

- Unified real-time token streaming
- Plugin architecture
- Rebuilt provider system with Vercel AI Gateway
- Native Anthropic provider
- Smart approvals, Chrome CDP browser connect
- ACP IDE integration, Honcho memory, voice mode

## [v0.2.0](RELEASE_v0.2.0.md) — 2026-03-12

> First tagged release

- Multi-platform messaging gateway (Telegram, Discord, Slack, WhatsApp, Signal, Email, Home Assistant)
- MCP (Model Context Protocol) client
- Skills ecosystem (70+ bundled skills)

216 PRs · 63 contributors · 119 issues
