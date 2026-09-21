<div align="center">

# 📋 skill-rollcall

**Take a roll call of your agent's skills — who's here, who's new, who's never going to show up, and why. Claude Code, Codex, Cursor, Gemini CLI, Copilot, OpenCode and every other Agent Skills host.**

[![CI](https://github.com/Londopy/skill-rollcall/actions/workflows/ci.yml/badge.svg)](https://github.com/Londopy/skill-rollcall/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](skills/skill-rollcall/scripts/rollcall.py)
[![Agent Skills](https://img.shields.io/badge/Agent_Skills-spec-111)](https://agentskills.io)
[![Works with](https://img.shields.io/badge/works_with-Claude_Code_%7C_Codex_%7C_Cursor_%7C_Gemini_CLI_%7C_Copilot_%7C_OpenCode-D97757)](#install)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)](#install)

<img src="docs/demo.png" alt="skill-rollcall output: loadable skills, warnings, errors, harness diff and a fix plan" width="900">

<sub>Part of the rollcall family — tools that make what your coding agent does silently legible: **skill-rollcall** · [mcp-rollcall](https://github.com/Londopy/mcp-rollcall) · [settings-effective](https://github.com/Londopy/settings-effective) · [git-attribution](https://github.com/Londopy/git-attribution) · all four: [agent-skills](https://github.com/Londopy/agent-skills)</sub>

</div>

---

You installed a skill and the picker doesn't show it. Or it shows, but never fires on its own. Or you just pulled a 300-skill repo and want to know what you actually got before your agent runs any of it. Every host — Claude Code, Codex, Cursor, Gemini CLI, Copilot, OpenCode — registers skills silently and skips broken ones silently, and each one reads a *different* set of folders, so you're left guessing between "restart", "clear the session", and "go read the filesystem".

`skill-rollcall` rebuilds the skill index from disk **for the host you're in, with the reasons attached**, diffs it against what the agent currently sees, and can repair, lint or audit what it finds. It runs as a skill (`/skill-rollcall` in Claude Code, `$skill-rollcall` in Codex, or just say "reload skills") and as a plain CLI.

## What it does

| Mode | Question it answers |
|---|---|
| default | Which skill folders are loadable, and which will **never register** — no `SKILL.md`, unclosed frontmatter, no `name`, a repo dragged in whole? |
| `--agent codex` / `--agent all` | Which skills does **that** host see? Where do they overlap, and which are copies? Auto-detected when a host marks its shell. |
| `--known a,b,c` | Which are **registered** vs **new** since the session started, and which does the agent still list that are gone from disk? |
| `--lint` | Why doesn't it **trigger**? Missing description, no "use when…" cue, too short, near-duplicate of a sibling, Claude-only frontmatter other hosts ignore. Plus how many tokens all your descriptions cost every session. |
| `--fix` | Show the folder moves that would repair it. `--fix --apply` does them. Never touches a plugin cache. |
| `--audit` | Anything in these skills I should read before running them? Zero-width characters, `curl \| sh`, permission- or approval-bypass flags, injection phrasing, unfamiliar hosts, encoded blobs. |
| `--skills-dir ./skills --strict` | Is my skills **repo** clean before I publish — for every host? Non-zero exit for CI. |

Everything is read-only except `--fix --apply`, which shows you the plan first.

## Install

One layout — `skills/skill-rollcall/SKILL.md` + `scripts/rollcall.py` — is the [Agent Skills](https://agentskills.io) standard, so the same folder works everywhere. Pick whichever fits how you manage skills.

**`skills` CLI** — any of 79 agents (global; `--copy` because symlinks need Developer Mode on Windows):

```bash
npx skills add Londopy/skill-rollcall -g --copy                  # picks the agents it finds
npx skills add Londopy/skill-rollcall -g --copy -a codex -a cursor
npx skills add Londopy/skill-rollcall -g --copy --all            # every agent, no prompts
```

**Claude Code plugin** (in an interactive `claude` session):

```
/plugin marketplace add Londopy/skill-rollcall
/plugin install skill-rollcall@skill-rollcall
```

**Codex:** `$skill-installer` with this repo's URL, or the copy below into `~/.agents/skills/`.

**By hand** — copy the folder into the host's skills directory:

```bash
git clone https://github.com/Londopy/skill-rollcall
cp -r skill-rollcall/skills/skill-rollcall ~/.claude/skills/          # Claude Code
cp -r skill-rollcall/skills/skill-rollcall ~/.agents/skills/          # Codex, Cline, Zed, Warp (universal)
cp -r skill-rollcall/skills/skill-rollcall ~/.cursor/skills/          # Cursor
cp -r skill-rollcall/skills/skill-rollcall ~/.gemini/skills/          # Gemini CLI
cp -r skill-rollcall/skills/skill-rollcall ~/.copilot/skills/         # GitHub Copilot
cp -r skill-rollcall/skills/skill-rollcall ~/.config/opencode/skills/ # OpenCode
cp -r skill-rollcall/skills/skill-rollcall .agents/skills/            # one project, every host that walks .agents/
```

Most hosts watch their skills folders, so it shows up without a restart. Confirm with `/skill-rollcall` (Claude Code) or `$skill-rollcall` (Codex) — that's what it's for.

## Usage

### From your agent

Say what you'd naturally say — "reload skills", "do you see `/foo`?", "why isn't my skill triggering?", "audit the skills I just installed", "how much context are my skills eating?", "which of these can Cursor see?" — or invoke the skill by name. The agent runs the right mode, answers your actual question first, then summarizes the rest. If a skill is on disk but not registered yet, the agent can load it by reading its `SKILL.md` directly, which is all any host's skill tool does anyway.

### As a CLI

Stdlib-only Python, nothing in it depends on any particular agent:

```bash
python ~/.claude/skills/skill-rollcall/scripts/rollcall.py --lint          # from a Claude Code install
python ~/.agents/skills/skill-rollcall/scripts/rollcall.py --agent codex   # from a Codex install
```

| Flag | Effect |
|---|---|
| `--agent X` | Host whose folders to scan: `claude`, `codex`, `cursor`, `gemini`, `copilot`, `opencode`, `amp`, `goose`, `kiro`, `windsurf`, `universal`, a comma list, or `all`. Default: detect from the environment, else `all` |
| `--known a,b,c` | Names the host already lists → marks rows registered / NEW, reports stale entries |
| `--lint` | Description-quality warnings, host-portability warnings and per-session context cost |
| `--audit` | Content scan; `high` / `review` / `info` severities |
| `--fix` / `--fix --apply` | Plan / perform un-nesting and folder renames |
| `--strict` | Exit 1 on any error or `high` audit finding |
| `--skills-dir DIR` | Scan a plain `<name>/SKILL.md` folder, e.g. a repo's `skills/` |
| `--add-dir DIR` | Include `DIR`'s project skill folders (`.claude/skills`, `.agents/skills`, …) |
| `--project DIR` | Start the project walk-up here (default: cwd; walks to the git root like every host) |
| `--no-plugins` | Skip Claude Code's `~/.claude/plugins` |
| `--problems-only` | Findings only, no table |
| `--full` / `--json` | Untruncated descriptions / machine-readable |

### Where each host looks

| Host | User scope | Project scope (walked up to the git root) | Also |
|---|---|---|---|
| Claude Code | `~/.claude/skills` | `.claude/skills` | plugin cache, skills-directory plugins (`plugin:skill`) |
| Codex | `~/.agents/skills`, `~/.codex/skills` | `.agents/skills` | `[[skills.config]] enabled = false` in `config.toml` → warning |
| Cursor | `~/.cursor/skills` | `.agents/skills` | |
| Gemini CLI | `~/.gemini/skills` | `.agents/skills` | |
| GitHub Copilot | `~/.copilot/skills` | `.agents/skills` | |
| OpenCode | `~/.config/opencode/skills` | `.agents/skills` | |
| Amp | `~/.config/agents/skills` | `.agents/skills` | |
| Goose / Kiro / Windsurf | `~/.config/goose/skills` / `~/.kiro/skills` / `~/.codeium/windsurf/skills` | `.goose/` / `.kiro/` / `.windsurf/skills` | |
| Cline, Zed, Warp (universal) | `~/.agents/skills` | `.agents/skills` | |

Rows from the shared `.agents/skills` convention are labelled `agents`. The same skill installed for two hosts is a copy, not a duplicate — the duplicate and overlap warnings only fire when one host would see both. Host detection reads `CLAUDECODE`, `CODEX_SANDBOX`, `CURSOR_AGENT` and `GEMINI_CLI`; anything else reports `host: all` and you narrow with `--agent`.

## What it catches

| Finding | Severity | Why it matters | Fix |
|---|---|---|---|
| No `SKILL.md` | error | Folder is ignored | Add one |
| `SKILL.md` at `skills/<x>/SKILL.md` | error | A repo dragged in whole; every host looks one level deep | `--fix --apply` moves the inner folders up |
| Frontmatter missing / unclosed / no `name` | error | Unparseable → not registered | Start with `---`, close with `---`, add `name:` |
| No `description` | warning | Registers, **never auto-triggers** | Write one; it's what the agent matches on |
| `name` ≠ folder, or outside the spec (`A-Z`, `_`, `--`, >64) | warning | Strict hosts skip it; the slash/`$` name is `name` | `--fix --apply` renames the folder; fix the name |
| Description > 1024 chars | warning | Hosts truncate or shorten it | Front-load the trigger words |
| Duplicate name one host sees twice | warning | One silently wins | Rename or remove one |
| Disabled in Codex `config.toml` | warning | Installed but switched off | Flip `enabled` or delete the entry |
| `--lint`: short / no cue / overlap / heavy / Claude-only `context:` | warning | The structural reasons a skill under-triggers, over-triggers or misbehaves elsewhere | Reword the description; drop host-specific keys |
| `--audit`: hidden Unicode, `curl \| sh`, invoking a permission- or approval-bypass flag | high | Classic ways a skill hides or escalates | Read the file before running the skill |
| `--audit`: naming `bypassPermissions` or `approval_policy = "never"` | review | Normal in a settings or permissions tool; suspicious elsewhere | Read in context |
| `--audit`: injection phrasing, encoded blobs | review | Normal inside a security skill's signature table; suspicious elsewhere | Read in context |
| `--audit`: unfamiliar host | info | Where the skill phones | Decide if you expect it |

The same layout the tool flags as an error — `skills/<name>/SKILL.md` — is the correct layout for a **repo**, which is what this is. Drop the whole repo into a skills folder and the tool tells you to move the inner folder up (Claude Code also accepts it with a `.claude-plugin/plugin.json`). It diagnoses its own most likely mis-install.

## Related, not overlapping

Claude Code's `/skill-doctor` (2.1.252+) tells you what each skill **costs** and how often it's **used**, so you can decide what to turn off. It doesn't say why a skill failed to register or trigger. Use both: `/skill-doctor` for pruning, `skill-rollcall` for "why isn't it there". `npx skills ls` lists what the `skills` CLI installed, not what the host loaded. The context-cost line here is a rough stand-in when neither is available.

## What it cannot do

- **It can't make the host rescan.** Hosts watch their skills folders themselves — except Claude Code's `--bare` mode, and Codex says to restart when a change doesn't appear. This tool tells you whether that's happened and works around it when it hasn't.
- **Host detection is best effort.** It reads environment markers. A host that sets none is reported as `all`; pass `--agent`.
- **`--lint` is structural, not semantic.** It catches the description shapes that reliably under-trigger. It doesn't predict whether a given phrase will fire a given skill.
- **`--audit` is a pattern scan, not a verdict.** Clean means nothing obvious turned up, not that the skill is safe. Read anything it flags `high`.
- **Plugin bundles** — Claude Code `hooks/`, `agents/`, `.mcp.json` changes need `/reload-plugins`; Codex and Cursor plugin marketplaces are not read, only skill folders.
- **The Claude desktop app's `/` picker is a separate cache.** In a session opened before you installed a skill, the app may say "`/skill-rollcall` isn't a command here" even though the agent already has it. Send the request as a normal message instead — that goes to the agent, not the picker.

## Development

```bash
python -m unittest discover -s tests -v          # 66 tests, stdlib only
python skills/skill-rollcall/scripts/rollcall.py --skills-dir skills --agent all --lint --audit --strict
python docs/make_demo.py                         # re-render docs/demo.png (needs Pillow)
```

CI runs the tests on Windows, macOS and Linux across Python 3.10 and 3.13 (the 3.10 leg exercises the stdlib TOML fallback; 3.13 checks it against `tomllib`), then runs the tool on its own skill for every host in strict mode — so the auditor audits itself on every push.

## Layout

```
skill-rollcall/
├── .claude-plugin/
│   ├── plugin.json          # Claude Code plugin manifest
│   └── marketplace.json     # the repo is its own single-plugin marketplace
├── skills/skill-rollcall/
│   ├── SKILL.md             # what the agent reads (Agent Skills spec frontmatter)
│   ├── agents/openai.yaml   # Codex / ChatGPT UI metadata (optional, ignored elsewhere)
│   └── scripts/rollcall.py  # the tool (stdlib only, Python 3.10+)
├── tests/                   # test_rollcall.py + test_agents.py
├── docs/                    # demo image + generator
└── .github/workflows/ci.yml
```

## License

[MIT](LICENSE) © 2026 Londopy
