# Delegation

## Principle
Never block on direct work in project repos. Delegate to agents, monitor, report.

## Core Delegation Rules

1. **Delegate ALL work to subagents.** Never do project work directly.
2. **Time threshold: >7 seconds = must delegate.** If a task will take more than ~7s, fire a subagent immediately.
3. **Investigation is free — delegate instantly.** The cost of spawning an investigator subagent is zero. Fire immediately on ambiguity.
4. **Default go signal.** Do not ask permission to delegate. Just execute.
5. **Report with numbered task list.** When reporting status, list tasks as #1, #2, #3 etc.
6. **Use org-mode status file for tracking.** Write/update `GITIGNORED/tasks/status.org` in the project root.
7. **`CLAUDE_ORCHESTRATOR=1` enables delegation hooks.** When this env var is set, the delegation hook activates and subagents inherit the orchestrator context.

## Launch Agent via Emacs vterm

```elisp
(let ((buf (vterm (generate-new-buffer-name "agent-PROJECT"))))
  (with-current-buffer buf
    (vterm-send-string "cd ~/proj/PROJECT && cld")
    (vterm-send-return))
  (buffer-name buf))
```

## Launch Agent via screen

```bash
cld_screen PROJECT        # Start worker in screen
cld_screen_send PROJECT "task description"
cld_screen_ls             # List running agents
cld_screen_attach PROJECT # Attach to agent
```

## Send Task to Running Agent

### vterm
```elisp
(with-current-buffer "agent-PROJECT"
  (vterm-send-string "task description")
  (vterm-send-return))
```

### screen
```bash
cld_screen_send PROJECT "task description"
```

## Monitor Agent Output

```elisp
(with-current-buffer "agent-PROJECT"
  (let* ((content (buffer-substring-no-properties (point-min) (point-max)))
         (lines (seq-filter
                  (lambda (l) (not (string-empty-p (string-trim l))))
                  (split-string content "\n")))
         (last-lines (last lines 15)))
    (mapconcat #'identity last-lines "\n")))
```

## List All Active Agents

```elisp
(mapcar #'buffer-name
  (seq-filter (lambda (b)
    (with-current-buffer b (derived-mode-p 'vterm-mode)))
    (buffer-list)))
```

## Agent Model Selection

Agent definition files use one name per type (no model suffix variants like `-SONNET`, `-OPUS`, `-HAIKU`). The orchestrator chooses the model at call time based on task complexity:

- Simple/mechanical tasks (git commit, report formatting): `haiku`
- Standard development work: `sonnet` (default)
- Hard reasoning, architecture, debugging: `opus`

Do not maintain separate `-SONNET`, `-OPUS`, `-HAIKU` agent files. One definition per agent type. Project-specific agents go in `<project>/docs/to_claude/agents/`, not in dotfiles global agents.

## When to Delegate vs Do Directly

| Task | Action |
|------|--------|
| Code changes in a project | Delegate |
| Quick info lookup (grep, read) | Direct |
| Plot/figure generation | Direct (SciTeX MCP) |
| Audio feedback | Direct (scitex audio_speak) |
| Git operations in projects | Delegate |
| Test runs | Delegate |
| Status checks | Direct (read agent output) |
| Telegram replies | Direct |
| File creation at master level | Direct |
| Investigation / debugging | Delegate (cost is zero) |

## Use vterm When
- Emacs is running
- Need real-time output monitoring
- Want to manage from master agent context

## Use screen When
- Need persistent sessions across Emacs restarts
- Running headless or without Emacs
- Need process isolation

## Voice Message Handling
When Telegram voice/video messages arrive (attachment_kind: voice/video_note):
```bash
# 1. Download
mcp__plugin_telegram_telegram__download_attachment file_id=XXX

# 2. Convert to 16kHz WAV
ffmpeg -y -i INPUT -ar 16000 -ac 1 -f wav /tmp/msgN.wav

# 3. Transcribe (tiny model for speed)
~/.emacs.d/.cache/whisper.cpp/build/bin/whisper-cli \
  -m ~/.emacs.d/.cache/whisper.cpp/models/ggml-tiny.bin \
  -l ja -f /tmp/msgN.wav
```
- **tiny**: fast (~3s for 3s audio), minor accuracy trade-off (recommended default)
- **small**: better accuracy, slower
- **medium**: good accuracy, ~73s for 3s clip on CPU
- **large-v3-turbo**: best accuracy, slowest on CPU

## User Input Notes
User may use browser speech-to-text for Telegram messages.
Expect occasional typos from voice recognition (e.g., "貯" for "ちょ", "止" for "と").
Interpret charitably based on context.

## Self-Growth Capabilities

The orchestrator is self-improving. Key capabilities:

### What You Can Control
- **Context management**: Self-compact via Emacs MCP when context grows large
- **Auto mode**: Toggle auto-accept mode via vterm commands
- **MCP reconnect**: Reconnect MCP servers when disconnected
- **Skills/memory**: Update own skills and memory files to improve future sessions
- **Hooks**: Can modify hooks to change own behavior patterns

### Self-Improvement Loop
1. Experience a problem or receive correction
2. Save the learning to memory (feedback type) or skills
3. Next session loads improved rules automatically
4. Continuously better judgment over time

### Proactive Notifications
- Notify user via Telegram before context compaction
- Report task completion/failure immediately
- Warn about approaching limits or issues

### Design Philosophy: Follow Anthropic (守破離)
When unsure about UX/design/layout decisions, follow Anthropic's patterns:
- Page layout (desktop/mobile): reference claude.ai
- Branding: subtle — snake icon only in chat/AI context
- Mobile responsiveness: match Anthropic-level polish
- Master by imitation first (守), then break away (破), then transcend (離)
