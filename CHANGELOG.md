# Changelog

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
