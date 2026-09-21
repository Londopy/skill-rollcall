# Changelog

## 1.2.0 - 2026-09-21

- Multi-host: the roll call now covers every Agent Skills host, not just Claude Code.
  `--agent` picks Claude Code, Codex, Cursor, Gemini CLI, Copilot, OpenCode, Amp, Goose,
  Kiro, Windsurf, the universal `~/.agents/skills` convention, a comma list, or `all`;
  with no flag the host is detected from `CLAUDECODE`, `CODEX_SANDBOX`, `CURSOR_AGENT`
  or `GEMINI_CLI`, and falls back to `all`. The report header names the host and every
  root it found, and under several hosts rows are grouped by who reads them.
- Project walk-up now finds `.agents/skills` (and `.goose/`, `.kiro/`, `.windsurf/`)
  alongside `.claude/skills`; `--add-dir` includes them too.
- Duplicate and overlap warnings only fire when one host would see both skills: the
  same skill installed for Claude Code and for Codex is a copy, not a conflict.
- Codex: skills switched off with `[[skills.config]] enabled = false` in
  `~/.codex/config.toml` (or a project's `.codex/config.toml`) are reported as warnings.
  TOML is read with `tomllib` on 3.11+ and a small stdlib fallback on 3.10.
- Agent Skills spec checks: a `name` outside `^[a-z0-9]+(-[a-z0-9]+)*$` or over 64
  chars, and a description over 1024 chars, are warnings ("strict hosts skip it").
  `--lint` flags Claude-only frontmatter (`context:`) when other hosts read the skill.
- `--audit`: Codex's `--dangerously-bypass-approvals-and-sandbox` and the `--yolo` alias
  (Codex and Gemini CLI) count as `skips-permissions`; `approval_policy = "never"` is a
  `review` hit; openai.com, cursor.com, agentskills.io and skills.sh join the known hosts.
- JSON rows gain `agent`, `where`, `visible_to` and `frontmatter_keys`.
- SKILL.md rewritten for any host, with spec `license`, `compatibility` and `metadata`
  frontmatter; `agents/openai.yaml` added for Codex / ChatGPT UI metadata.
- 21 new tests (66 total), including a fallback-vs-`tomllib` equivalence check.

## 1.1.1 - 2026-09-19

- `--audit`: `skips-permissions` (high) now fires only on *invoking* bypass -
  `--dangerously-skip-permissions` or `--permission-mode bypassPermissions`. Merely
  naming the mode is the new `names-bypass` finding at `review` severity, with a line
  number, because a tool that reports on permission settings has to say the word.
  Previously any file containing `bypassPermissions` was `high`.

## 1.1.0 - 2026-09-19

- `--lint`: description quality (too short, no "use when" cue, near-duplicate of a
  sibling, heavy) and a per-session context-cost estimate.
- `--audit`: content scan for hidden Unicode, pipe-to-shell, permission-bypass flags,
  injection phrasing, encoded blobs and unfamiliar hosts, with high / review / info
  severities. Dangerous strings inside test files are downgraded to review.
- `--fix` / `--fix --apply`: un-nest manifest-less plugin layouts and rename folders
  to match `name`. Dry run by default; never touches the plugin cache.
- `--strict` exit code and `--skills-dir` for checking a skills repo in CI.
- Scopes: project walk-up to the git root, `--add-dir`, plugin cache and synced
  plugins, and skills-directory plugins (`.claude-plugin/plugin.json` + `skills/`),
  which are now correctly recognised as valid rather than flagged as nested.
- Errors (will not register) and warnings (registers, but) are reported separately.
- 44-test suite and a CI matrix (Windows / macOS / Linux, Python 3.10 / 3.13) that
  also runs the tool on its own skill in strict mode.
- Docs corrected: Claude Code hot-reloads SKILL.md edits, not just adds and removes;
  `--bare` mode is the case without a watcher; `/reload-plugins` for plugin hooks.

## 1.0.0 - 2026-09-19

Initial release.

- `rollcall.py`: scans user and project skill folders, rebuilds the name/description
  index, marks rows registered / NEW against `--known`, and diagnoses skills that
  will never register (missing `SKILL.md`, plugin-nested layout, `name` != folder,
  missing description, duplicate names).
- `SKILL.md`: procedure for reporting the roll call and manually loading a skill the
  harness has not registered yet.
- Plugin manifest and self-hosted marketplace for `/plugin install`.
