# Changelog

## 1.0.0 - 2026-09-19

Initial release.

- `rollcall.py`: scans user and project skill folders, rebuilds the name/description
  index, marks rows registered / NEW against `--known`, and diagnoses skills that
  will never register (missing `SKILL.md`, plugin-nested layout, `name` != folder,
  missing description, duplicate names).
- `SKILL.md`: procedure for reporting the roll call and manually loading a skill the
  harness has not registered yet.
- Plugin manifest and self-hosted marketplace for `/plugin install`.
