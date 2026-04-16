#!/usr/bin/env python3
"""
Delegate Tool -- Subagent Architecture

Spawns child AIAgent instances with isolated context, restricted toolsets,
and their own terminal sessions. Supports single-task and batch (parallel)
modes. The parent blocks until all children complete.

Each child gets:
  - A fresh conversation (no parent history)
  - Its own task_id (own terminal session, file ops cache)
  - A restricted toolset (configurable, with blocked tools always stripped)
  - A focused system prompt built from the delegated goal + context

The parent's context only sees the delegation call and the summary result,
never the child's intermediate tool calls or reasoning.
"""

import json
import logging
logger = logging.getLogger(__name__)
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from toolsets import TOOLSETS


# Tools that children must never have access to
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",   # no recursive delegation
    "clarify",         # no user interaction
    "memory",          # no writes to shared MEMORY.md
    "send_message",    # no cross-platform side effects
    "execute_code",    # children should reason step-by-step, not write scripts
])

# Build a description fragment listing toolsets available for subagents.
# Excludes toolsets where ALL tools are blocked, composite/platform toolsets
# (bullwhip-* prefixed), and scenario toolsets.
_EXCLUDED_TOOLSET_NAMES = frozenset({"debugging", "safe", "delegation", "moa", "rl"})
_SUBAGENT_TOOLSETS = sorted(
    name for name, defn in TOOLSETS.items()
    if name not in _EXCLUDED_TOOLSET_NAMES
    and not name.startswith("bullwhip-")
    and not all(t in DELEGATE_BLOCKED_TOOLS for t in defn.get("tools", []))
)
_TOOLSET_LIST_STR = ", ".join(f"'{n}'" for n in _SUBAGENT_TOOLSETS)

_DEFAULT_MAX_CONCURRENT_CHILDREN = 3
MAX_DEPTH = 2  # parent (0) -> child (1) -> grandchild rejected (2)


def _get_max_concurrent_children() -> int:
    """Read delegation.max_concurrent_children from config, falling back to
    DELEGATION_MAX_CONCURRENT_CHILDREN env var, then the default (3).

    Uses the same ``_load_config()`` path that the rest of ``delegate_task``
    uses, keeping config priority consistent (config.yaml > env > default).
    """
    cfg = _load_config()
    val = cfg.get("max_concurrent_children")
    if val is not None:
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            logger.warning(
                "delegation.max_concurrent_children=%r is not a valid integer; "
                "using default %d", val, _DEFAULT_MAX_CONCURRENT_CHILDREN,
            )
    env_val = os.getenv("DELEGATION_MAX_CONCURRENT_CHILDREN")
    if env_val:
        try:
            return max(1, int(env_val))
        except (TypeError, ValueError):
            pass
    return _DEFAULT_MAX_CONCURRENT_CHILDREN
DEFAULT_MAX_ITERATIONS = 50
_HEARTBEAT_INTERVAL = 15  # seconds between parent activity heartbeats during delegation
_DEFAULT_WALL_CLOCK_TIMEOUT = 900  # 15 minutes per subagent (wall-clock, not iteration count)
_STALL_CHECK_INTERVAL = 60  # seconds of no API call progress before warning
_STALL_PROCESS_DEAD_TIMEOUT = 30  # seconds after process death before interrupting child
_STALL_HARD_TIMEOUT = 300  # 5 min of zero progress → interrupt (process alive but truly stuck)
_USER_PING_INTERVAL = 45  # seconds between "still working" messages to the user
DEFAULT_TOOLSETS = ["terminal", "file", "web"]


def check_delegate_requirements() -> bool:
    """Delegation has no external requirements -- always available."""
    return True


def _build_child_system_prompt(
    goal: str,
    context: Optional[str] = None,
    *,
    workspace_path: Optional[str] = None,
) -> str:
    """Build a focused system prompt for a child agent."""
    parts = [
        "You are a focused subagent working on a specific delegated task.",
        "",
        f"YOUR TASK:\n{goal}",
    ]
    if context and context.strip():
        parts.append(f"\nCONTEXT:\n{context}")
    if workspace_path and str(workspace_path).strip():
        parts.append(
            "\nWORKSPACE PATH:\n"
            f"{workspace_path}\n"
            "Use this exact path for local repository/workdir operations unless the task explicitly says otherwise."
        )
    parts.append(
        "\nComplete this task using the tools available to you. "
        "When finished, provide a clear, concise summary of:\n"
        "- What you did\n"
        "- What you found or accomplished\n"
        "- Any files you created or modified\n"
        "- Any issues encountered\n\n"
        "Important workspace rule: Never assume a repository lives at /workspace/... or any other container-style path unless the task/context explicitly gives that path. "
        "If no exact local path is provided, discover it first before issuing git/workdir-specific commands.\n\n"
        "Be thorough but concise -- your response is returned to the "
        "parent agent as a summary."
    )
    return "\n".join(parts)


def _resolve_workspace_hint(parent_agent) -> Optional[str]:
    """Best-effort local workspace hint for child prompts.

    We only inject a path when we have a concrete absolute directory. This avoids
    teaching subagents a fake container path while still helping them avoid
    guessing `/workspace/...` for local repo tasks.
    """
    candidates = [
        os.getenv("TERMINAL_CWD"),
        getattr(getattr(parent_agent, "_subdirectory_hints", None), "working_dir", None),
        getattr(parent_agent, "terminal_cwd", None),
        getattr(parent_agent, "cwd", None),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            text = os.path.abspath(os.path.expanduser(str(candidate)))
        except Exception:
            continue
        if os.path.isabs(text) and os.path.isdir(text):
            return text
    return None


def _strip_blocked_tools(toolsets: List[str]) -> List[str]:
    """Remove toolsets that contain only blocked tools."""
    blocked_toolset_names = {
        "delegation", "clarify", "memory", "code_execution",
    }
    return [t for t in toolsets if t not in blocked_toolset_names]


def _build_child_progress_callback(task_index: int, parent_agent, task_count: int = 1) -> Optional[callable]:
    """Build a callback that relays child agent tool calls to the parent display.

    Two display paths:
      CLI:     prints tree-view lines above the parent's delegation spinner
      Gateway: batches tool names and relays to parent's progress callback

    Returns None if no display mechanism is available, in which case the
    child agent runs with no progress callback (identical to current behavior).
    """
    spinner = getattr(parent_agent, '_delegate_spinner', None)
    parent_cb = getattr(parent_agent, 'tool_progress_callback', None)

    if not spinner and not parent_cb:
        return None  # No display → no callback → zero behavior change

    # Show 1-indexed prefix only in batch mode (multiple tasks)
    prefix = f"[{task_index + 1}] " if task_count > 1 else ""

    # Track start time for elapsed display
    _start_time = time.monotonic()
    _tool_count = [0]  # mutable counter for closure

    # Gateway: batch tool names, flush periodically
    _BATCH_SIZE = 3  # smaller batches for more frequent updates
    _batch: List[str] = []

    def _format_elapsed() -> str:
        elapsed = int(time.monotonic() - _start_time)
        if elapsed < 60:
            return f"{elapsed}s"
        return f"{elapsed // 60}m{elapsed % 60:02d}s"

    def _extract_action_detail(tool_name: str, preview: str = None, args: dict = None) -> str:
        """Extract a human-readable action detail from tool args.

        Shows what the subagent is actually DOING, not just which tool it called.
        e.g. 'terminal: git status' instead of just 'terminal'
        """
        if not args:
            return preview or ""
        # Map tool → primary arg that tells you what's happening
        _KEY_MAP = {
            "terminal": "command", "web_search": "query", "web_extract": "urls",
            "read_file": "path", "write_file": "path", "patch": "path",
            "search_files": "pattern", "browser_navigate": "url",
            "execute_code": "code", "delegate_task": "goal",
            "image_generate": "prompt",
        }
        key = _KEY_MAP.get(tool_name)
        if key and key in args:
            val = str(args[key])
            return val
        return preview or ""

    # Track last activity for "what is it doing now" display
    _last_activity = ["starting..."]  # mutable string for current activity description
    _last_activity_ts = [time.monotonic()]

    def _callback(event_type: str, tool_name: str = None, preview: str = None, args=None, **kwargs):
        # event_type is one of: "tool.started", "tool.completed",
        # "reasoning.available", "_thinking", "subagent_progress"

        # "_thinking" / reasoning events — relay to BOTH CLI and gateway
        if event_type in ("_thinking", "reasoning.available"):
            text = preview or tool_name or ""
            if not text.strip():
                return
            short = (text[:80] + "...") if len(text) > 80 else text
            _last_activity[0] = f"💭 {short}"
            _last_activity_ts[0] = time.monotonic()
            if spinner:
                display = (text[:55] + "...") if len(text) > 55 else text
                try:
                    spinner.print_above(f" {prefix}├─ 💭 \"{display}\"")
                except Exception as e:
                    logger.debug("Spinner print_above failed: %s", e)
            # Relay thinking to gateway so users see what the agent is considering
            if parent_cb:
                try:
                    elapsed_str = _format_elapsed()
                    parent_cb("subagent_progress",
                              f"🔀 {prefix}[{elapsed_str}] 💭 {short}")
                except Exception:
                    pass
            return

        # tool.completed — update activity tracker and show result preview
        if event_type == "tool.completed":
            _last_activity[0] = f"completed {tool_name or 'tool'}"
            _last_activity_ts[0] = time.monotonic()
            # Show a preview of the tool result so users can follow along
            result_text = preview or ""
            if result_text and len(result_text) > 200:
                result_text = result_text[:200] + "…"
            if result_text and spinner:
                try:
                    spinner.print_above(f" {prefix}│  ↳ {result_text}")
                except Exception:
                    pass
            if result_text and parent_cb:
                try:
                    parent_cb("subagent_progress",
                              f"🔀 {prefix}{tool_name} result: {result_text}")
                except Exception:
                    pass
            return

        _tool_count[0] += 1
        elapsed_str = _format_elapsed()

        # Extract meaningful action detail from args
        action_detail = _extract_action_detail(tool_name or "", preview, args if isinstance(args, dict) else None)

        # Update current activity tracker
        act_short = (action_detail[:60] + "...") if len(action_detail) > 60 else action_detail
        _last_activity[0] = f"🔧 {tool_name}: {act_short}" if act_short else f"🔧 {tool_name}"
        _last_activity_ts[0] = time.monotonic()

        # tool.started — display with actual command/action detail
        if spinner:
            # CLI: show up to 80 chars of the actual action
            short = (action_detail[:80] + "...") if len(action_detail) > 80 else action_detail
            from agent.display import get_tool_emoji
            emoji = get_tool_emoji(tool_name or "")
            line = f" {prefix}├─ {emoji} {tool_name} [{elapsed_str}]"
            if short:
                line += f"  {short}"
            try:
                spinner.print_above(line)
            except Exception as e:
                logger.debug("Spinner print_above failed: %s", e)

        if parent_cb:
            # Gateway: include action detail so users see WHAT is happening
            detail_short = (action_detail[:60] + "...") if len(action_detail) > 60 else action_detail
            display_text = f"{tool_name}: {detail_short}" if detail_short else (tool_name or "")
            _batch.append(display_text)
            if len(_batch) >= _BATCH_SIZE:
                summary = "\n".join(f"  • {item}" for item in _batch)
                try:
                    parent_cb("subagent_progress",
                              f"🔀 {prefix}Progress ({elapsed_str}, {_tool_count[0]} tools):\n{summary}")
                except Exception as e:
                    logger.debug("Parent callback failed: %s", e)
                _batch.clear()

    def _flush():
        """Flush remaining batched tool actions to gateway on completion."""
        if parent_cb and _batch:
            elapsed_str = _format_elapsed()
            summary = "\n".join(f"  • {item}" for item in _batch)
            try:
                parent_cb("subagent_progress",
                          f"🔀 {prefix}Progress ({elapsed_str}, {_tool_count[0]} tools):\n{summary}")
            except Exception as e:
                logger.debug("Parent callback flush failed: %s", e)
            _batch.clear()

    def _notify_status(status_msg: str):
        """Send a status update to gateway (completion, failure, timeout)."""
        if parent_cb:
            try:
                parent_cb("subagent_progress", f"🔀 {prefix}{status_msg}")
            except Exception as e:
                logger.debug("Status notification failed: %s", e)

    _callback._flush = _flush
    _callback._notify_status = _notify_status
    _callback._start_time = _start_time
    _callback._tool_count = _tool_count
    _callback._last_activity = _last_activity
    _callback._last_activity_ts = _last_activity_ts
    return _callback


def _build_child_agent(
    task_index: int,
    goal: str,
    context: Optional[str],
    toolsets: Optional[List[str]],
    model: Optional[str],
    max_iterations: int,
    parent_agent,
    # Credential overrides from delegation config (provider:model resolution)
    override_provider: Optional[str] = None,
    override_base_url: Optional[str] = None,
    override_api_key: Optional[str] = None,
    override_api_mode: Optional[str] = None,
    # ACP transport overrides — lets a non-ACP parent spawn ACP child agents
    override_acp_command: Optional[str] = None,
    override_acp_args: Optional[List[str]] = None,
):
    """
    Build a child AIAgent on the main thread (thread-safe construction).
    Returns the constructed child agent without running it.

    When override_* params are set (from delegation config), the child uses
    those credentials instead of inheriting from the parent.  This enables
    routing subagents to a different provider:model pair (e.g. cheap/fast
    model on OpenRouter while the parent runs on Nous Portal).
    """
    from run_agent import AIAgent

    # When no explicit toolsets given, inherit from parent's enabled toolsets
    # so disabled tools (e.g. web) don't leak to subagents.
    # Note: enabled_toolsets=None means "all tools enabled" (the default),
    # so we must derive effective toolsets from the parent's loaded tools.
    parent_enabled = getattr(parent_agent, "enabled_toolsets", None)
    if parent_enabled is not None:
        parent_toolsets = set(parent_enabled)
    elif parent_agent and hasattr(parent_agent, "valid_tool_names"):
        # enabled_toolsets is None (all tools) — derive from loaded tool names
        import model_tools
        parent_toolsets = {
            ts for name in parent_agent.valid_tool_names
            if (ts := model_tools.get_toolset_for_tool(name)) is not None
        }
    else:
        parent_toolsets = set(DEFAULT_TOOLSETS)

    if toolsets:
        # Intersect with parent — subagent must not gain tools the parent lacks
        child_toolsets = _strip_blocked_tools([t for t in toolsets if t in parent_toolsets])
    elif parent_agent and parent_enabled is not None:
        child_toolsets = _strip_blocked_tools(parent_enabled)
    elif parent_toolsets:
        child_toolsets = _strip_blocked_tools(sorted(parent_toolsets))
    else:
        child_toolsets = _strip_blocked_tools(DEFAULT_TOOLSETS)

    workspace_hint = _resolve_workspace_hint(parent_agent)
    child_prompt = _build_child_system_prompt(goal, context, workspace_path=workspace_hint)
    # Extract parent's API key so subagents inherit auth (e.g. Nous Portal).
    parent_api_key = getattr(parent_agent, "api_key", None)
    if (not parent_api_key) and hasattr(parent_agent, "_client_kwargs"):
        parent_api_key = parent_agent._client_kwargs.get("api_key")

    # Build progress callback to relay tool calls to parent display
    child_progress_cb = _build_child_progress_callback(task_index, parent_agent)

    # Each subagent gets its own iteration budget capped at max_iterations
    # (configurable via delegation.max_iterations, default 50).  This means
    # total iterations across parent + subagents can exceed the parent's
    # max_iterations.  The user controls the per-subagent cap in config.yaml.

    child_thinking_cb = None
    if child_progress_cb:
        def _child_thinking(text: str) -> None:
            if not text:
                return
            try:
                child_progress_cb("_thinking", text)
            except Exception as e:
                logger.debug("Child thinking callback relay failed: %s", e)

        child_thinking_cb = _child_thinking

    # Resolve effective credentials: config override > parent inherit
    effective_model = model or parent_agent.model
    effective_provider = override_provider or getattr(parent_agent, "provider", None)
    effective_base_url = override_base_url or parent_agent.base_url
    effective_api_key = override_api_key or parent_api_key
    effective_api_mode = override_api_mode or getattr(parent_agent, "api_mode", None)
    effective_acp_command = override_acp_command or getattr(parent_agent, "acp_command", None)
    effective_acp_args = list(override_acp_args if override_acp_args is not None else (getattr(parent_agent, "acp_args", []) or []))

    # Resolve reasoning config: delegation override > parent inherit
    parent_reasoning = getattr(parent_agent, "reasoning_config", None)
    child_reasoning = parent_reasoning
    try:
        delegation_cfg = _load_config()
        delegation_effort = str(delegation_cfg.get("reasoning_effort") or "").strip()
        if delegation_effort:
            from bullwhip_constants import parse_reasoning_effort
            parsed = parse_reasoning_effort(delegation_effort)
            if parsed is not None:
                child_reasoning = parsed
            else:
                logger.warning(
                    "Unknown delegation.reasoning_effort '%s', inheriting parent level",
                    delegation_effort,
                )
    except Exception as exc:
        logger.debug("Could not load delegation reasoning_effort: %s", exc)

    child = AIAgent(
        base_url=effective_base_url,
        api_key=effective_api_key,
        model=effective_model,
        provider=effective_provider,
        api_mode=effective_api_mode,
        acp_command=effective_acp_command,
        acp_args=effective_acp_args,
        max_iterations=max_iterations,
        max_tokens=getattr(parent_agent, "max_tokens", None),
        reasoning_config=child_reasoning,
        prefill_messages=getattr(parent_agent, "prefill_messages", None),
        enabled_toolsets=child_toolsets,
        quiet_mode=True,
        ephemeral_system_prompt=child_prompt,
        log_prefix=f"[subagent-{task_index}]",
        platform=parent_agent.platform,
        skip_context_files=True,
        skip_memory=True,
        clarify_callback=None,
        thinking_callback=child_thinking_cb,
        session_db=getattr(parent_agent, '_session_db', None),
        parent_session_id=getattr(parent_agent, 'session_id', None),
        providers_allowed=parent_agent.providers_allowed,
        providers_ignored=parent_agent.providers_ignored,
        providers_order=parent_agent.providers_order,
        provider_sort=parent_agent.provider_sort,
        tool_progress_callback=child_progress_cb,
        iteration_budget=None,  # fresh budget per subagent
    )
    child._print_fn = getattr(parent_agent, '_print_fn', None)
    # Set delegation depth so children can't spawn grandchildren
    child._delegate_depth = getattr(parent_agent, '_delegate_depth', 0) + 1

    # Share a credential pool with the child when possible so subagents can
    # rotate credentials on rate limits instead of getting pinned to one key.
    child_pool = _resolve_child_credential_pool(effective_provider, parent_agent)
    if child_pool is not None:
        child._credential_pool = child_pool

    # Register child for interrupt propagation
    if hasattr(parent_agent, '_active_children'):
        lock = getattr(parent_agent, '_active_children_lock', None)
        if lock:
            with lock:
                parent_agent._active_children.append(child)
        else:
            parent_agent._active_children.append(child)

    return child

def _get_wall_clock_timeout() -> int:
    """Read delegation.wall_clock_timeout from config or env, with default."""
    cfg = _load_config()
    val = cfg.get("wall_clock_timeout")
    if val is not None:
        try:
            return max(60, int(val))
        except (TypeError, ValueError):
            logger.warning(
                "delegation.wall_clock_timeout=%r is not valid; using default %d",
                val, _DEFAULT_WALL_CLOCK_TIMEOUT,
            )
    env_val = os.getenv("DELEGATION_WALL_CLOCK_TIMEOUT")
    if env_val:
        try:
            return max(60, int(env_val))
        except (TypeError, ValueError):
            pass
    return _DEFAULT_WALL_CLOCK_TIMEOUT


def _run_single_child(
    task_index: int,
    goal: str,
    child=None,
    parent_agent=None,
    wall_clock_timeout: Optional[int] = None,
    **_kwargs,
) -> Dict[str, Any]:
    """
    Run a pre-built child agent. Called from within a thread.
    Returns a structured result dict.

    Improvements over original:
    - Wall-clock timeout: kills child if it exceeds the deadline
    - Stall detection: monitors child activity and interrupts if stalled
    - Progress flush in finally: batched progress always delivered
    - Completion/failure notification: gateway users see status changes
    """
    child_start = time.monotonic()
    effective_timeout = wall_clock_timeout or _get_wall_clock_timeout()

    # Get the progress callback from the child agent
    child_progress_cb = getattr(child, 'tool_progress_callback', None)

    # Restore parent tool names using the value saved before child construction
    # mutated the global. This is the correct parent toolset, not the child's.
    import model_tools
    _saved_tool_names = getattr(child, "_delegate_saved_tool_names",
                                list(model_tools._last_resolved_tool_names))

    child_pool = getattr(child, '_credential_pool', None)
    leased_cred_id = None
    if child_pool is not None:
        leased_cred_id = child_pool.acquire_lease()
        if leased_cred_id is not None:
            try:
                leased_entry = child_pool.current()
                if leased_entry is not None and hasattr(child, '_swap_credential'):
                    child._swap_credential(leased_entry)
            except Exception as exc:
                logger.debug("Failed to bind child to leased credential: %s", exc)

    # Heartbeat: periodically propagate child activity to the parent so the
    # gateway inactivity timeout doesn't fire while the subagent is working.
    # Stall detection with 3-tier approach:
    #   1. Process death detection: check if ACP subprocess has exited
    #   2. Soft stall warning: no API progress for _STALL_CHECK_INTERVAL (60s)
    #   3. Hard stall interrupt: no progress for _STALL_HARD_TIMEOUT (300s)
    _heartbeat_stop = threading.Event()
    _last_child_activity_ts = [time.monotonic()]
    _last_child_api_count = [0]
    _timed_out = [False]
    _stop_reason = [""]  # "", "wall_clock_timeout", "process_dead", "hard_stall"
    _process_dead_since = [0.0]  # timestamp when we first noticed process death
    _stall_warned = [False]  # only warn once per stall episode
    _last_user_ping_ts = [time.monotonic()]  # last time we sent a "still working" msg

    def _check_acp_process_alive() -> tuple[bool, str]:
        """Check if child's ACP subprocess is still running.

        Returns (is_alive, detail_string).
        For non-ACP children, always returns (True, "").
        """
        try:
            client = getattr(child, 'client', None)
            if client is None:
                return True, ""
            # CopilotACPClient has _active_process
            active_proc = getattr(client, '_active_process', None)
            if active_proc is None:
                # No active process — could be between requests (normal)
                # or client was never ACP. Check if it's an ACP client.
                if hasattr(client, '_acp_command'):
                    # ACP client with no active process — between requests
                    return True, "between requests"
                return True, ""
            rc = active_proc.poll()
            if rc is None:
                return True, "running"
            # Process exited — grab stderr for diagnostics
            stderr_text = ""
            stderr_buf = getattr(client, '_stderr_lines', None)
            if stderr_buf:
                try:
                    stderr_text = "\n".join(stderr_buf)[-200:]
                except Exception:
                    pass
            return False, f"exited with code {rc}" + (f": {stderr_text}" if stderr_text else "")
        except Exception as e:
            logger.debug("[subagent-%d] process check failed: %s", task_index, e)
            return True, ""  # can't check → assume alive

    def _heartbeat_loop():
        while not _heartbeat_stop.wait(_HEARTBEAT_INTERVAL):
            now = time.monotonic()
            elapsed = now - child_start

            # === Wall-clock timeout check ===
            if elapsed > effective_timeout:
                logger.warning(
                    "[subagent-%d] wall-clock timeout after %.0fs (limit: %ds)",
                    task_index, elapsed, effective_timeout,
                )
                _timed_out[0] = True
                _stop_reason[0] = "wall_clock_timeout"
                if hasattr(child, '_interrupt_requested'):
                    child._interrupt_requested = True
                if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
                    try:
                        child_progress_cb._notify_status(
                            f"⏰ Subagent timed out after {int(elapsed)}s (limit: {effective_timeout}s)"
                        )
                    except Exception:
                        pass
                break

            # === ACP process death detection ===
            proc_alive, proc_detail = _check_acp_process_alive()
            if not proc_alive:
                if _process_dead_since[0] == 0.0:
                    _process_dead_since[0] = now
                    logger.warning(
                        "[subagent-%d] ACP process died: %s",
                        task_index, proc_detail,
                    )
                    if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
                        try:
                            child_progress_cb._notify_status(
                                f"⚠️ Subagent process exited ({proc_detail[:80]}), waiting for recovery..."
                            )
                        except Exception:
                            pass

                dead_duration = now - _process_dead_since[0]
                if dead_duration > _STALL_PROCESS_DEAD_TIMEOUT:
                    logger.error(
                        "[subagent-%d] ACP process has been dead for %.0fs, interrupting",
                        task_index, dead_duration,
                    )
                    _timed_out[0] = True
                    _stop_reason[0] = "process_dead"
                    if hasattr(child, '_interrupt_requested'):
                        child._interrupt_requested = True
                    if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
                        try:
                            child_progress_cb._notify_status(
                                f"💀 Subagent process died and did not recover after {int(dead_duration)}s — aborting"
                            )
                        except Exception:
                            pass
                    break
            else:
                # Process is alive — reset death tracker
                if _process_dead_since[0] != 0.0:
                    logger.info("[subagent-%d] ACP process recovered", task_index)
                    _process_dead_since[0] = 0.0

            if parent_agent is None:
                continue
            touch = getattr(parent_agent, '_touch_activity', None)
            if not touch:
                continue

            # === Pull child activity for heartbeat + stall detection ===
            desc = f"delegate_task: subagent {task_index} working"
            try:
                child_summary = child.get_activity_summary()
                child_tool = child_summary.get("current_tool")
                child_iter = child_summary.get("api_call_count", 0)
                child_max = child_summary.get("max_iterations", 0)

                # Track progress
                if child_iter != _last_child_api_count[0]:
                    _last_child_activity_ts[0] = now
                    _last_child_api_count[0] = child_iter
                    _stall_warned[0] = False  # reset warning on progress
                else:
                    stall_duration = now - _last_child_activity_ts[0]

                    # Tier 2: Soft warning (informational)
                    if stall_duration > _STALL_CHECK_INTERVAL and not _stall_warned[0]:
                        _stall_warned[0] = True
                        logger.warning(
                            "[subagent-%d] no progress for %.0fs "
                            "(iteration %d/%d, process: %s)",
                            task_index, stall_duration, child_iter, child_max,
                            proc_detail or "alive",
                        )
                        if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
                            try:
                                child_progress_cb._notify_status(
                                    f"⏳ Subagent idle for {int(stall_duration)}s "
                                    f"(iteration {child_iter}/{child_max}) — still working..."
                                )
                            except Exception:
                                pass

                    # Tier 3: Hard stall — interrupt
                    if stall_duration > _STALL_HARD_TIMEOUT:
                        logger.error(
                            "[subagent-%d] hard stall: no progress for %.0fs, interrupting",
                            task_index, stall_duration,
                        )
                        _timed_out[0] = True
                        _stop_reason[0] = "hard_stall"
                        if hasattr(child, '_interrupt_requested'):
                            child._interrupt_requested = True
                        if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
                            try:
                                child_progress_cb._notify_status(
                                    f"🧊 Subagent frozen: no activity for {int(stall_duration)}s — aborting"
                                )
                            except Exception:
                                pass
                        break

                if child_tool:
                    desc = (f"delegate_task: subagent running {child_tool} "
                            f"(iteration {child_iter}/{child_max}, {int(elapsed)}s)")
                else:
                    child_desc = child_summary.get("last_activity_desc", "")
                    if child_desc:
                        desc = (f"delegate_task: subagent {child_desc} "
                                f"(iteration {child_iter}/{child_max}, {int(elapsed)}s)")
            except Exception:
                pass
            try:
                touch(desc)
            except Exception:
                pass

            # === Periodic user-visible status push ===
            # Like Claude Code's live status line: show users exactly what
            # the subagent is doing RIGHT NOW, not just when a tool starts.
            if child_progress_cb and hasattr(child_progress_cb, '_last_activity'):
                time_since_ping = now - _last_user_ping_ts[0]
                if time_since_ping >= _USER_PING_INTERVAL:
                    _last_user_ping_ts[0] = now
                    current_activity = child_progress_cb._last_activity[0]
                    elapsed_min = int(elapsed) // 60
                    elapsed_sec = int(elapsed) % 60
                    elapsed_fmt = f"{elapsed_min}m{elapsed_sec:02d}s" if elapsed_min else f"{elapsed_sec}s"
                    if hasattr(child_progress_cb, '_notify_status'):
                        try:
                            child_progress_cb._notify_status(
                                f"⚙️ [{elapsed_fmt}] {current_activity}"
                            )
                        except Exception:
                            pass

    _heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    _heartbeat_thread.start()

    try:
        result = child.run_conversation(user_message=goal)

        duration = round(time.monotonic() - child_start, 2)

        summary = result.get("final_response") or ""
        completed = result.get("completed", False)
        interrupted = result.get("interrupted", False)
        api_calls = result.get("api_calls", 0)

        # Detect "(empty)" responses — model returned nothing useful after
        # exhausting all retries. This is distinct from a normal empty string
        # (which indicates max_iterations or other completion without output).
        _is_empty_sentinel = summary.strip() == "(empty)"

        if _timed_out[0]:
            status = "timed_out"
        elif interrupted:
            status = "interrupted"
        elif _is_empty_sentinel:
            status = "failed"
        elif summary:
            status = "completed"
        else:
            status = "failed"

        # Build tool trace from conversation messages (already in memory).
        # Include action details and result previews so the parent model
        # can understand WHAT the subagent did, not just which tools it called.
        _TRACE_ACTION_LIMIT = 200   # max chars for action/args preview
        _TRACE_RESULT_LIMIT = 500   # max chars for result preview
        tool_trace: list[Dict[str, Any]] = []
        trace_by_id: Dict[str, Dict[str, Any]] = {}
        messages = result.get("messages") or []
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") == "assistant":
                    for tc in (msg.get("tool_calls") or []):
                        fn = tc.get("function", {})
                        raw_args = fn.get("arguments", "")
                        # Extract a human-readable action preview from args
                        action_preview = ""
                        try:
                            args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                            if isinstance(args_dict, dict):
                                # Pick the most informative field
                                for key in ("command", "query", "goal", "file_path",
                                            "path", "url", "content", "code"):
                                    if key in args_dict:
                                        val = str(args_dict[key])
                                        action_preview = val[:_TRACE_ACTION_LIMIT]
                                        break
                        except (json.JSONDecodeError, TypeError):
                            pass
                        entry_t = {
                            "tool": fn.get("name", "unknown"),
                            "action": action_preview,
                        }
                        tool_trace.append(entry_t)
                        tc_id = tc.get("id")
                        if tc_id:
                            trace_by_id[tc_id] = entry_t
                elif msg.get("role") == "tool":
                    content = msg.get("content", "")
                    is_error = bool(
                        content and "error" in content[:80].lower()
                    )
                    # Include a preview of the result so the parent model
                    # knows what the tool returned
                    result_preview = (content[:_TRACE_RESULT_LIMIT] + "…") if len(content) > _TRACE_RESULT_LIMIT else content
                    result_meta = {
                        "result_preview": result_preview,
                        "result_bytes": len(content),
                        "status": "error" if is_error else "ok",
                    }
                    tc_id = msg.get("tool_call_id")
                    target = trace_by_id.get(tc_id) if tc_id else None
                    if target is not None:
                        target.update(result_meta)
                    elif tool_trace:
                        tool_trace[-1].update(result_meta)

        # Determine exit reason — use specific stop reason when available
        if _timed_out[0]:
            exit_reason = _stop_reason[0] or "wall_clock_timeout"
        elif interrupted:
            exit_reason = "interrupted"
        elif _is_empty_sentinel:
            exit_reason = "empty_response"
        elif completed:
            exit_reason = "completed"
        else:
            exit_reason = "max_iterations"

        # Extract token counts (safe for mock objects)
        _input_tokens = getattr(child, "session_prompt_tokens", 0)
        _output_tokens = getattr(child, "session_completion_tokens", 0)
        _model = getattr(child, "model", None)

        entry: Dict[str, Any] = {
            "task_index": task_index,
            "status": status,
            "summary": summary,
            "api_calls": api_calls,
            "duration_seconds": duration,
            "model": _model if isinstance(_model, str) else None,
            "exit_reason": exit_reason,
            "tokens": {
                "input": _input_tokens if isinstance(_input_tokens, (int, float)) else 0,
                "output": _output_tokens if isinstance(_output_tokens, (int, float)) else 0,
            },
            "tool_trace": tool_trace,
        }
        if status == "failed":
            if _is_empty_sentinel:
                entry["error"] = (
                    f"Subagent's model ({_model}) returned empty responses after all retries. "
                    "The model may be too small or incompatible for this task. "
                    "Consider using a more capable model for delegation "
                    "(set delegation.model in config.yaml)."
                )
            else:
                entry["error"] = result.get("error", "Subagent did not produce a response.")
        if status == "timed_out":
            _STOP_REASON_MESSAGES = {
                "wall_clock_timeout": (
                    f"Subagent exceeded wall-clock timeout of {effective_timeout}s. "
                    f"Partial result may be available in summary."
                ),
                "process_dead": (
                    "Subagent's backing process (e.g. Codex) crashed and did not recover. "
                    "The process exited unexpectedly during execution."
                ),
                "hard_stall": (
                    f"Subagent made no progress for {_STALL_HARD_TIMEOUT}s. "
                    "The process was alive but completely unresponsive (likely stuck/frozen)."
                ),
            }
            entry["error"] = _STOP_REASON_MESSAGES.get(
                _stop_reason[0],
                f"Subagent stopped: {_stop_reason[0] or 'unknown reason'}",
            )

        # Notify user of completion/failure via progress callback
        # and surface the subagent's actual answer so users see it directly
        if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
            try:
                if status == "completed":
                    child_progress_cb._notify_status(
                        f"✅ Subagent completed ({duration}s, {api_calls} API calls)"
                    )
                    # Show the subagent's actual answer to the user
                    if summary and summary.strip() and summary.strip() != "(empty)":
                        # Truncate very long summaries for display
                        display_summary = summary.strip()
                        if len(display_summary) > 2000:
                            display_summary = display_summary[:2000] + "\n…(truncated)"
                        child_progress_cb._notify_status(
                            f"📋 Subagent answer:\n{display_summary}"
                        )
                elif status == "failed":
                    child_progress_cb._notify_status(
                        f"❌ Subagent failed after {duration}s: {entry.get('error', 'unknown')[:100]}"
                    )
                elif status == "timed_out":
                    child_progress_cb._notify_status(
                        f"⏰ Subagent timed out after {duration}s"
                    )
            except Exception:
                pass

        return entry

    except Exception as exc:
        duration = round(time.monotonic() - child_start, 2)
        logger.exception("[subagent-%d] failed with exception", task_index)

        # Notify user of crash via progress callback
        if child_progress_cb and hasattr(child_progress_cb, '_notify_status'):
            try:
                child_progress_cb._notify_status(
                    f"💥 Subagent crashed after {duration}s: {str(exc)[:100]}"
                )
            except Exception:
                pass

        return {
            "task_index": task_index,
            "status": "error",
            "summary": None,
            "error": str(exc),
            "api_calls": 0,
            "duration_seconds": duration,
        }

    finally:
        # Always flush progress so gateway doesn't lose the last batch
        if child_progress_cb and hasattr(child_progress_cb, '_flush'):
            try:
                child_progress_cb._flush()
            except Exception as e:
                logger.debug("Progress callback flush failed: %s", e)

        # Stop the heartbeat thread so it doesn't keep touching parent activity
        # after the child has finished (or failed).
        _heartbeat_stop.set()
        _heartbeat_thread.join(timeout=10)
        if _heartbeat_thread.is_alive():
            logger.warning(
                "[subagent-%d] heartbeat thread did not stop within 10s; "
                "it will be cleaned up when the process exits (daemon thread)",
                task_index,
            )

        if child_pool is not None and leased_cred_id is not None:
            try:
                child_pool.release_lease(leased_cred_id)
            except Exception as exc:
                logger.debug("Failed to release credential lease: %s", exc)

        # Restore the parent's tool names so the process-global is correct
        # for any subsequent execute_code calls or other consumers.
        import model_tools

        saved_tool_names = getattr(child, "_delegate_saved_tool_names", None)
        if isinstance(saved_tool_names, list):
            model_tools._last_resolved_tool_names = list(saved_tool_names)

        # Remove child from active tracking

        # Unregister child from interrupt propagation
        if hasattr(parent_agent, '_active_children'):
            try:
                lock = getattr(parent_agent, '_active_children_lock', None)
                if lock:
                    with lock:
                        parent_agent._active_children.remove(child)
                else:
                    parent_agent._active_children.remove(child)
            except (ValueError, UnboundLocalError) as e:
                logger.debug("Could not remove child from active_children: %s", e)

        # Close tool resources (terminal sandboxes, browser daemons,
        # background processes, httpx clients) so subagent subprocesses
        # don't outlive the delegation.
        try:
            if hasattr(child, 'close'):
                child.close()
        except Exception:
            logger.debug("Failed to close child agent after delegation")

def delegate_task(
    goal: Optional[str] = None,
    context: Optional[str] = None,
    toolsets: Optional[List[str]] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    max_iterations: Optional[int] = None,
    acp_command: Optional[str] = None,
    acp_args: Optional[List[str]] = None,
    wall_clock_timeout: Optional[int] = None,
    parent_agent=None,
) -> str:
    """
    Spawn one or more child agents to handle delegated tasks.

    Supports two modes:
      - Single: provide goal (+ optional context, toolsets)
      - Batch:  provide tasks array [{goal, context, toolsets}, ...]

    Returns JSON with results array, one entry per task.
    """
    if parent_agent is None:
        return tool_error("delegate_task requires a parent agent context.")

    # Depth limit
    depth = getattr(parent_agent, '_delegate_depth', 0)
    if depth >= MAX_DEPTH:
        return json.dumps({
            "error": (
                f"Delegation depth limit reached ({MAX_DEPTH}). "
                "Subagents cannot spawn further subagents."
            )
        })

    # Load config
    cfg = _load_config()
    default_max_iter = cfg.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    effective_max_iter = max_iterations or default_max_iter

    # Resolve delegation credentials (provider:model pair).
    # When delegation.provider is configured, this resolves the full credential
    # bundle (base_url, api_key, api_mode) via the same runtime provider system
    # used by CLI/gateway startup.  When unconfigured, returns None values so
    # children inherit from the parent.
    try:
        creds = _resolve_delegation_credentials(cfg, parent_agent)
    except ValueError as exc:
        return tool_error(str(exc))

    # Normalize to task list
    max_children = _get_max_concurrent_children()
    if tasks and isinstance(tasks, list):
        if len(tasks) > max_children:
            return tool_error(
                f"Too many tasks: {len(tasks)} provided, but "
                f"max_concurrent_children is {max_children}. "
                f"Either reduce the task count, split into multiple "
                f"delegate_task calls, or increase "
                f"delegation.max_concurrent_children in config.yaml."
            )
        task_list = tasks
    elif goal and isinstance(goal, str) and goal.strip():
        task_list = [{"goal": goal, "context": context, "toolsets": toolsets}]
    else:
        return tool_error("Provide either 'goal' (single task) or 'tasks' (batch).")

    if not task_list:
        return tool_error("No tasks provided.")

    # Validate each task has a goal
    for i, task in enumerate(task_list):
        if not task.get("goal", "").strip():
            return tool_error(f"Task {i} is missing a 'goal'.")

    overall_start = time.monotonic()
    results = []

    n_tasks = len(task_list)
    # Track goal labels for progress display (truncated for readability)
    task_labels = [t["goal"][:40] for t in task_list]

    # Save parent tool names BEFORE any child construction mutates the global.
    # _build_child_agent() calls AIAgent() which calls get_tool_definitions(),
    # which overwrites model_tools._last_resolved_tool_names with child's toolset.
    import model_tools as _model_tools
    _parent_tool_names = list(_model_tools._last_resolved_tool_names)

    # Build all child agents on the main thread (thread-safe construction)
    # Wrapped in try/finally so the global is always restored even if a
    # child build raises (otherwise _last_resolved_tool_names stays corrupted).
    children = []
    try:
        for i, t in enumerate(task_list):
            child = _build_child_agent(
                task_index=i, goal=t["goal"], context=t.get("context"),
                toolsets=t.get("toolsets") or toolsets, model=creds["model"],
                max_iterations=effective_max_iter, parent_agent=parent_agent,
                override_provider=creds["provider"], override_base_url=creds["base_url"],
                override_api_key=creds["api_key"],
                override_api_mode=creds["api_mode"],
                override_acp_command=t.get("acp_command") or acp_command,
                override_acp_args=t.get("acp_args") or acp_args,
            )
            # Override with correct parent tool names (before child construction mutated global)
            child._delegate_saved_tool_names = _parent_tool_names
            children.append((i, t, child))
    finally:
        # Authoritative restore: reset global to parent's tool names after all children built
        _model_tools._last_resolved_tool_names = _parent_tool_names

    # Resolve wall-clock timeout once for all children
    effective_wall_clock = wall_clock_timeout or _get_wall_clock_timeout()

    if n_tasks == 1:
        # Single task -- run directly (no thread pool overhead)
        _i, _t, child = children[0]
        result = _run_single_child(0, _t["goal"], child, parent_agent,
                                   wall_clock_timeout=effective_wall_clock)
        results.append(result)
    else:
        # Batch -- run in parallel with per-task progress lines
        completed_count = 0
        spinner_ref = getattr(parent_agent, '_delegate_spinner', None)

        with ThreadPoolExecutor(max_workers=max_children) as executor:
            futures = {}
            for i, t, child in children:
                future = executor.submit(
                    _run_single_child,
                    task_index=i,
                    goal=t["goal"],
                    child=child,
                    parent_agent=parent_agent,
                    wall_clock_timeout=effective_wall_clock,
                )
                futures[future] = i

            # Wrap as_completed loop in try/finally to ensure all futures
            # are consumed even if display code raises an exception.
            try:
                for future in as_completed(futures):
                    try:
                        entry = future.result()
                    except Exception as exc:
                        idx = futures[future]
                        logger.exception("[subagent-%d] future raised exception", idx)
                        entry = {
                            "task_index": idx,
                            "status": "error",
                            "summary": None,
                            "error": str(exc),
                            "api_calls": 0,
                            "duration_seconds": 0,
                        }
                    results.append(entry)
                    completed_count += 1

                    # Print per-task completion line above the spinner
                    idx = entry["task_index"]
                    label = task_labels[idx] if idx < len(task_labels) else f"Task {idx}"
                    dur = entry.get("duration_seconds", 0)
                    status = entry.get("status", "?")
                    _STATUS_ICONS = {
                        "completed": "✓", "timed_out": "⏰",
                        "interrupted": "⚡", "error": "💥", "failed": "✗",
                    }
                    icon = _STATUS_ICONS.get(status, "✗")
                    remaining = n_tasks - completed_count
                    completion_line = f"{icon} [{idx+1}/{n_tasks}] {label}  ({dur}s, {status})"
                    try:
                        if spinner_ref:
                            spinner_ref.print_above(completion_line)
                        else:
                            print(f"  {completion_line}")
                    except Exception:
                        logger.debug("Failed to display completion line for task %d", idx)

                    # Update spinner text to show remaining count
                    if spinner_ref and remaining > 0:
                        try:
                            spinner_ref.update_text(f"🔀 {remaining} task{'s' if remaining != 1 else ''} remaining")
                        except Exception:
                            pass
            finally:
                # Ensure all remaining futures are consumed so orphaned children
                # don't run indefinitely in the background.
                for future in futures:
                    if not future.done():
                        future.cancel()
                    elif future not in {f for f in futures if any(
                        r.get("task_index") == futures[future] for r in results
                    )}:
                        # Future completed but wasn't consumed — collect its result
                        try:
                            entry = future.result(timeout=0)
                            results.append(entry)
                        except Exception as exc:
                            idx = futures[future]
                            results.append({
                                "task_index": idx,
                                "status": "error",
                                "summary": None,
                                "error": f"Uncollected future: {exc}",
                                "api_calls": 0,
                                "duration_seconds": 0,
                            })

        # Sort by task_index so results match input order
        results.sort(key=lambda r: r["task_index"])

    # Notify parent's memory provider of delegation outcomes
    if parent_agent and hasattr(parent_agent, '_memory_manager') and parent_agent._memory_manager:
        for entry in results:
            try:
                _task_goal = task_list[entry["task_index"]]["goal"] if entry["task_index"] < len(task_list) else ""
                parent_agent._memory_manager.on_delegation(
                    task=_task_goal,
                    result=entry.get("summary", "") or "",
                    child_session_id=getattr(children[entry["task_index"]][2], "session_id", "") if entry["task_index"] < len(children) else "",
                )
            except Exception:
                pass

    total_duration = round(time.monotonic() - overall_start, 2)

    return json.dumps({
        "results": results,
        "total_duration_seconds": total_duration,
    }, ensure_ascii=False)


def _resolve_child_credential_pool(effective_provider: Optional[str], parent_agent):
    """Resolve a credential pool for the child agent.

    Rules:
    1. Same provider as the parent -> share the parent's pool so cooldown state
       and rotation stay synchronized.
    2. Different provider -> try to load that provider's own pool.
    3. No pool available -> return None and let the child keep the inherited
       fixed credential behavior.
    """
    if not effective_provider:
        return getattr(parent_agent, "_credential_pool", None)

    parent_provider = getattr(parent_agent, "provider", None) or ""
    parent_pool = getattr(parent_agent, "_credential_pool", None)
    if parent_pool is not None and effective_provider == parent_provider:
        return parent_pool

    try:
        from agent.credential_pool import load_pool
        pool = load_pool(effective_provider)
        if pool is not None and pool.has_credentials():
            return pool
    except Exception as exc:
        logger.debug(
            "Could not load credential pool for child provider '%s': %s",
            effective_provider,
            exc,
        )
    return None


def _resolve_delegation_credentials(cfg: dict, parent_agent) -> dict:
    """Resolve credentials for subagent delegation.

    If ``delegation.base_url`` is configured, subagents use that direct
    OpenAI-compatible endpoint. Otherwise, if ``delegation.provider`` is
    configured, the full credential bundle (base_url, api_key, api_mode,
    provider) is resolved via the runtime provider system — the same path used
    by CLI/gateway startup. This lets subagents run on a completely different
    provider:model pair.

    If neither base_url nor provider is configured, returns None values so the
    child inherits everything from the parent agent.

    Raises ValueError with a user-friendly message on credential failure.
    """
    configured_model = str(cfg.get("model") or "").strip() or None
    configured_provider = str(cfg.get("provider") or "").strip() or None
    configured_base_url = str(cfg.get("base_url") or "").strip() or None
    configured_api_key = str(cfg.get("api_key") or "").strip() or None

    if configured_base_url:
        api_key = (
            configured_api_key
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        if not api_key:
            raise ValueError(
                "Delegation base_url is configured but no API key was found. "
                "Set delegation.api_key or OPENAI_API_KEY."
            )

        base_lower = configured_base_url.lower()
        provider = "custom"
        api_mode = "chat_completions"
        if "chatgpt.com/backend-api/codex" in base_lower:
            provider = "openai-codex"
            api_mode = "codex_responses"
        elif "api.anthropic.com" in base_lower:
            provider = "anthropic"
            api_mode = "anthropic_messages"

        return {
            "model": configured_model,
            "provider": provider,
            "base_url": configured_base_url,
            "api_key": api_key,
            "api_mode": api_mode,
        }

    if not configured_provider:
        # No provider override — child inherits everything from parent
        return {
            "model": configured_model,
            "provider": None,
            "base_url": None,
            "api_key": None,
            "api_mode": None,
        }

    # Provider is configured — resolve full credentials
    try:
        from bullwhip_cli.runtime_provider import resolve_runtime_provider
        runtime = resolve_runtime_provider(requested=configured_provider)
    except Exception as exc:
        raise ValueError(
            f"Cannot resolve delegation provider '{configured_provider}': {exc}. "
            f"Check that the provider is configured (API key set, valid provider name), "
            f"or set delegation.base_url/delegation.api_key for a direct endpoint. "
            f"Available providers: openrouter, nous, zai, kimi-coding, minimax."
        ) from exc

    api_key = runtime.get("api_key", "")
    if not api_key:
        raise ValueError(
            f"Delegation provider '{configured_provider}' resolved but has no API key. "
            f"Set the appropriate environment variable or run 'bullwhip auth'."
        )

    return {
        "model": configured_model,
        "provider": runtime.get("provider"),
        "base_url": runtime.get("base_url"),
        "api_key": api_key,
        "api_mode": runtime.get("api_mode"),
        "command": runtime.get("command"),
        "args": list(runtime.get("args") or []),
    }


def _load_config() -> dict:
    """Load delegation config from CLI_CONFIG or persistent config.

    Checks the runtime config (cli.py CLI_CONFIG) first, then falls back
    to the persistent config (bullwhip_cli/config.py load_config()) so that
    ``delegation.model`` / ``delegation.provider`` are picked up regardless
    of the entry point (CLI, gateway, cron).
    """
    try:
        from cli import CLI_CONFIG
        cfg = CLI_CONFIG.get("delegation", {})
        if cfg:
            return cfg
    except Exception:
        pass
    try:
        from bullwhip_cli.config import load_config
        full = load_config()
        return full.get("delegation", {})
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# OpenAI Function-Calling Schema
# ---------------------------------------------------------------------------

DELEGATE_TASK_SCHEMA = {
    "name": "delegate_task",
    "description": (
        "Spawn one or more subagents to work on tasks in isolated contexts. "
        "Each subagent gets its own conversation, terminal session, and toolset. "
        "Only the final summary is returned -- intermediate tool results "
        "never enter your context window.\n\n"
        "TWO MODES (one of 'goal' or 'tasks' is required):\n"
        "1. Single task: provide 'goal' (+ optional context, toolsets)\n"
        "2. Batch (parallel): provide 'tasks' array with up to 3 items. "
        "All run concurrently and results are returned together.\n\n"
        "WHEN TO USE delegate_task:\n"
        "- Reasoning-heavy subtasks (debugging, code review, research synthesis)\n"
        "- Tasks that would flood your context with intermediate data\n"
        "- Parallel independent workstreams (research A and B simultaneously)\n\n"
        "WHEN NOT TO USE (use these instead):\n"
        "- Mechanical multi-step work with no reasoning needed -> use execute_code\n"
        "- Single tool call -> just call the tool directly\n"
        "- Tasks needing user interaction -> subagents cannot use clarify\n\n"
        "IMPORTANT:\n"
        "- Subagents have NO memory of your conversation. Pass all relevant "
        "info (file paths, error messages, constraints) via the 'context' field.\n"
        "- Subagents CANNOT call: delegate_task, clarify, memory, send_message, "
        "execute_code.\n"
        "- Each subagent gets its own terminal session (separate working directory and state).\n"
        "- Results are always returned as an array, one entry per task.\n"
        "- Each subagent has a wall-clock timeout (default: 15 min). If it "
        "exceeds this, it is interrupted and partial results are returned.\n"
        "- Progress is reported in real-time: tool calls, elapsed time, "
        "iteration count. Users are notified on completion, failure, or timeout."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "What the subagent should accomplish. Be specific and "
                    "self-contained -- the subagent knows nothing about your "
                    "conversation history."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Background information the subagent needs: file paths, "
                    "error messages, project structure, constraints. The more "
                    "specific you are, the better the subagent performs."
                ),
            },
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Toolsets to enable for this subagent. "
                    "Default: inherits your enabled toolsets. "
                    f"Available toolsets: {_TOOLSET_LIST_STR}. "
                    "Common patterns: ['terminal', 'file'] for code work, "
                    "['web'] for research, ['browser'] for web interaction, "
                    "['terminal', 'file', 'web'] for full-stack tasks."
                ),
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "Task goal"},
                        "context": {"type": "string", "description": "Task-specific context"},
                        "toolsets": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": f"Toolsets for this specific task. Available: {_TOOLSET_LIST_STR}. Use 'web' for network access, 'terminal' for shell, 'browser' for web interaction.",
                        },
                        "acp_command": {
                            "type": "string",
                            "description": "Per-task ACP command override (e.g. 'claude'). Overrides the top-level acp_command for this task only.",
                        },
                        "acp_args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Per-task ACP args override.",
                        },
                    },
                    "required": ["goal"],
                },
                # No maxItems — the runtime limit is configurable via
                # delegation.max_concurrent_children (default 3) and
                # enforced with a clear error in delegate_task().
                "description": (
                    "Batch mode: tasks to run in parallel (limit configurable via delegation.max_concurrent_children, default 3). Each gets "
                    "its own subagent with isolated context and terminal session. "
                    "When provided, top-level goal/context/toolsets are ignored."
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    "Max tool-calling turns per subagent (default: 50). "
                    "Only set lower for simple tasks."
                ),
            },
            "acp_command": {
                "type": "string",
                "description": (
                    "Override ACP command for child agents (e.g. 'claude', 'copilot'). "
                    "When set, children use ACP subprocess transport instead of inheriting "
                    "the parent's transport. Enables spawning Claude Code (claude --acp --stdio) "
                    "or other ACP-capable agents from any parent, including Discord/Telegram/CLI."
                ),
            },
            "acp_args": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Arguments for the ACP command (default: ['--acp', '--stdio']). "
                    "Only used when acp_command is set. Example: ['--acp', '--stdio', '--model', 'claude-opus-4-6']"
                ),
            },
            "wall_clock_timeout": {
                "type": "integer",
                "description": (
                    "Max wall-clock seconds per subagent before it is interrupted "
                    "(default: 900 = 15 minutes). Configurable via "
                    "delegation.wall_clock_timeout in config.yaml or "
                    "DELEGATION_WALL_CLOCK_TIMEOUT env var. "
                    "Set higher for long-running tasks."
                ),
            },
        },
        "required": [],
    },
}


# --- Registry ---
from tools.registry import registry, tool_error

registry.register(
    name="delegate_task",
    toolset="delegation",
    schema=DELEGATE_TASK_SCHEMA,
    handler=lambda args, **kw: delegate_task(
        goal=args.get("goal"),
        context=args.get("context"),
        toolsets=args.get("toolsets"),
        tasks=args.get("tasks"),
        max_iterations=args.get("max_iterations"),
        acp_command=args.get("acp_command"),
        acp_args=args.get("acp_args"),
        wall_clock_timeout=args.get("wall_clock_timeout"),
        parent_agent=kw.get("parent_agent")),
    check_fn=check_delegate_requirements,
    emoji="🔀",
)
