<div align="center">

# 📋 skill-rollcall

**Take a roll call of your Claude Code skills — who's here, who's new, who's not going to show up.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen)](skills/skill-rollcall/scripts/rollcall.py)
[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757?logo=anthropic&logoColor=white)](https://code.claude.com/docs/en/plugins)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey)](#install)
[![Read-only](https://img.shields.io/badge/side_effects-none-success)](#what-it-cannot-do)

</div>

---

Claude Code reads every skill's `SKILL.md` frontmatter at session start and watches the skills folders after that. Most of the time that just works. When it doesn't — you installed a skill and the `/` picker doesn't show it, a description edit isn't taking, a folder is sitting there silently ignored — you're left guessing whether to restart, `/clear`, or go read the file system yourself.

`skill-rollcall` rebuilds the same index from disk, tells you which skills are registered, which are new, and which are **never going to register** and why, and lets Claude load a new skill manually without restarting the session.

```
$ /skill-rollcall

scanned C:\Users\you\.claude\skills
49 loadable, 2 with problems

  ast-grep        Guide for writing ast-grep rules to perform structural code search and analysis…
  grill-me        Interview the user relentlessly about a plan or design until reaching shared…
  reload-skills   Refresh Claude's view of installed skills without restarting the session…  [NEW - not yet registered]
  strict-api      Use when the user says 'no hallucinations', 'verify APIs', 'reality check'…

problems (these will not register):
  zz-broken       no frontmatter (file must start with ---); frontmatter has no name; no description - will never auto-trigger
  zz-nested       SKILL.md is nested at skills\zz-nested\SKILL.md - plugin layout; move the inner folder up one level

new since harness index: reload-skills
```

## What it catches

| Problem | Why it matters | The fix it suggests |
|---|---|---|
| No `SKILL.md` in the folder | Folder is ignored entirely | Add one |
| `SKILL.md` nested at `skills/<name>/SKILL.md` | You copied a **plugin** into the skills folder; Claude Code only looks one level deep | Move the inner folder up |
| Frontmatter missing or never closed | Can't be parsed → not registered | Start the file with `---`, end the block with `---` |
| No `name:` | Nothing to register it as | Add one |
| `name:` ≠ folder name | Slash command uses `name`; confusing at best, shadowed at worst | Rename the folder |
| No `description:` | Registers, but **will never auto-trigger** | Write one — this is what Claude matches on |
| Duplicate `name` across user + project scope | One silently wins | Rename or remove one |

## Install

Pick whichever fits how you manage skills. All three produce the same result.

**With the `skills` CLI** (global, copied so it works without symlink permissions on Windows):

```bash
npx skills add Londopy/skill-rollcall -g --copy
```

**As a Claude Code plugin** (in an interactive `claude` session):

```
/plugin marketplace add Londopy/skill-rollcall
/plugin install skill-rollcall@skill-rollcall
```

**By hand:**

```bash
git clone https://github.com/Londopy/skill-rollcall
cp -r skill-rollcall/skills/skill-rollcall ~/.claude/skills/
```

Then say "reload skills" in any session, or type `/skill-rollcall`. Claude Code picks up new skill folders on its own within a turn or so; you shouldn't need to restart.

## Usage

### From Claude

It's a skill, so it triggers on intent. Any of these should fire it:

- "reload skills" / "refresh skills" / "rescan skills"
- "I just installed a skill, do you see it?"
- "why isn't `/foo` showing up?"
- "why isn't my skill triggering?"

Or force it with `/skill-rollcall`. Claude runs the script, groups the result into **registered / new / problems**, and — if you ask — loads a new skill by reading its `SKILL.md` directly, which is functionally what the `Skill` tool does anyway.

### As a plain CLI

The script is a standalone, stdlib-only Python tool. Nothing in it depends on Claude:

```bash
python ~/.claude/skills/skill-rollcall/scripts/rollcall.py
```

| Flag | Effect |
|---|---|
| `--full` | Full descriptions instead of truncating at 120 chars |
| `--json` | Machine-readable output, one object per skill folder |
| `--known a,b,c` | Names the harness already lists; marks each row `registered` / `NEW` and reports what's on disk but not in the list (and vice versa) |
| `--project DIR` | Also scan `DIR/.claude/skills` (defaults to the current directory) |

Handy as a shell alias for a quick health check after pulling a skills repo.

## What it cannot do

Honesty section. A skill is instructions loaded into Claude's context; it has no hook into the harness itself.

- **It cannot force Claude Code to rescan.** Only the harness does that, and it does it on its own — this tool tells you whether it has happened yet and works around it when it hasn't.
- **Description edits may need a fresh session.** The `description:` line is cached at startup. The *body* of a `SKILL.md` is re-read every time the skill is invoked, so body edits are always live. If you're fixing triggering and it still won't fire, `/clear`.
- **It is read-only.** It never writes, moves, or deletes anything. The fixes are suggestions for you.

## Layout

```
skill-rollcall/
├── .claude-plugin/
│   ├── plugin.json          # plugin manifest
│   └── marketplace.json     # the repo is its own single-plugin marketplace
├── skills/
│   └── skill-rollcall/
│       ├── SKILL.md         # what Claude reads
│       └── scripts/
│           └── rollcall.py  # the indexer (stdlib only, Python 3.10+)
├── CHANGELOG.md
├── LICENSE
└── README.md
```

The nested `skills/<name>/` layout is the plugin convention. It's also exactly the layout the tool flags as a problem if you drop the *whole repo* into `~/.claude/skills` — which is the point: copy the inner folder, or let `npx skills` / `/plugin install` do it for you.

## License

[MIT](LICENSE) © 2026 Londopy
