# Troubleshooting

Quick fixes for common issues. For the full FAQ, see the
[online documentation](https://bullwhip-agent.zerolabskorea.com/docs/reference/faq).

---

## Installation

### `pip install` fails with build errors

```bash
# Ensure build tools are installed
# Ubuntu/Debian
sudo apt install build-essential python3-dev

# macOS
xcode-select --install

# Then retry
pip install -e ".[all]"
```

### Python version mismatch

Bull Whip requires **Python 3.11+**. Check your version:

```bash
python3 --version
```

If you have multiple versions, use `python3.11` or `python3.12` explicitly,
or create a venv with the correct version:

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### `bullwhip` command not found after install

```bash
# Reload your shell
source ~/.bashrc   # or: source ~/.zshrc

# Or add manually
export PATH="$HOME/.local/bin:$PATH"
```

---

## API Keys & Providers

### "No API key configured" error

Bull Whip reads API keys from `~/.bullwhip/.env` (not from the project directory).

1. Run the setup wizard (recommended):
   ```bash
   bullwhip setup
   ```
2. Or configure manually:
   ```bash
   cp .env.example ~/.bullwhip/.env
   nano ~/.bullwhip/.env          # add your API key(s)
   ```

### Model returns empty or error responses

- Verify your API key is valid and has credits/quota.
- Check model name spelling: `bullwhip model` to see available models.
- Try a different provider: `bullwhip model` and select another.

### OpenRouter rate limit errors

- Check your OpenRouter dashboard for usage limits.
- Bull Whip has built-in rate limit tracking — it will auto-retry.
- For heavy usage, consider setting up a [credential pool](https://bullwhip-agent.zerolabskorea.com/docs/user-guide/features/credential-pools).

---

## CLI

### Terminal display is garbled or misaligned

```bash
# Reset terminal
reset

# If using tmux, ensure 256-color support
export TERM=xterm-256color
```

### Slash commands not working

- Type `/` to see autocomplete suggestions.
- Ensure you're in the Bull Whip CLI, not a raw Python shell.
- Some commands are platform-specific (CLI vs gateway).

### Context too long / out of memory

- Use `/compress` to compress the conversation context.
- Use `/new` to start a fresh conversation.
- Check context usage with `/usage`.

---

## Gateway (Messaging Platforms)

### Bot doesn't respond to messages

1. Check gateway status: `bullwhip gateway status`
2. View logs: `bullwhip gateway logs`
3. Verify platform token in `~/.bullwhip/.env`
4. Ensure the bot is added to the chat/channel with correct permissions.

### Gateway won't start as a service

- **Linux:** Requires systemd. Check: `systemctl --user status bullwhip-gateway`
- **macOS:** Uses launchd. Check: `launchctl list | grep bullwhip`
- **Windows:** Service mode not supported. Run in foreground: `bullwhip gateway run`

### Telegram webhook issues

```bash
# Reset webhook
bullwhip gateway setup telegram

# Check webhook status
bullwhip doctor
```

---

## Tools

### "Command blocked by approval system"

Bull Whip blocks potentially dangerous commands by default.
- Type `y` to approve, or `n` to reject.
- Configure auto-approval in `~/.bullwhip/config.yaml` under `tools.approval`.

### Browser tool not working

```bash
# Install Playwright browsers
playwright install chromium

# Or with system dependencies (Linux)
playwright install --with-deps chromium
```

### MCP server connection fails

```bash
# Check MCP config
cat ~/.bullwhip/mcp.json

# Test connection
bullwhip tools
```

---

## Docker

### Container can't access host network

```bash
# Use host network mode
docker run --network host bullwhip-agent

# Or map specific ports
docker run -p 8000:8000 bullwhip-agent
```

### Permission denied in container

```bash
# Pass your UID
docker run -e UID=$(id -u) bullwhip-agent
```

---

## Performance

### Slow responses

- Check your internet connection and provider status.
- Try `/fast` mode for supported providers (OpenAI, Anthropic).
- Use a closer provider region if available.
- Reduce context size with `/compress`.

### High memory usage

- Long conversations accumulate context. Use `/new` to reset.
- Disable unused tools via `bullwhip tools`.
- Close background processes: check with `/bg`.

---

## Still stuck?

- Run diagnostics: `bullwhip doctor`
- Check the [full FAQ](https://bullwhip-agent.zerolabskorea.com/docs/reference/faq)
- Search [GitHub Issues](https://github.com/ZeroLabsKorea/bullwhip-agent/issues)
- Ask on [Discord](https://discord.gg/ZeroLabsKorea)
