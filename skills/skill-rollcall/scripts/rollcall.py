#!/usr/bin/env python3
"""skill-rollcall: take a roll call of installed Claude Code skills.

Rebuilds the skill index the way Claude Code does at startup.

Scans every skills directory (user-level and project-level), parses each
SKILL.md's frontmatter, and prints a compact name/description table plus
diagnostics for anything that would stop a skill from being registered.

Usage:
    python rollcall.py                 # compact table, descriptions truncated
    python rollcall.py --full          # full descriptions
    python rollcall.py --json          # machine-readable
    python rollcall.py --project DIR   # also scan DIR/.claude/skills
    python rollcall.py --known a,b,c   # names the harness already lists;
                                           # marks each row registered / NEW

Stdlib only. Never writes anything.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

TRUNC = 120


def frontmatter(path: Path) -> tuple[dict, str | None]:
    """Return (fields, error). Minimal YAML: only top-level `key: value` lines
    are read, which is all the harness needs (name, description)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {}, f"unreadable: {e}"
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "no frontmatter (file must start with ---)"
    fields: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            return fields, None
        if line.startswith((" ", "\t")) and key:
            # continuation of a folded/multi-line value
            fields[key] = (fields[key] + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val in (">", ">-", "|", "|-"):
                val = ""
            fields[key] = val.strip("\"'")
    return fields, "frontmatter never closed (missing second ---)"


def scan(root: Path, scope: str) -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        skill_md = d / "SKILL.md"
        row = {"dir": d.name, "path": str(d), "scope": scope,
               "name": None, "description": "", "problems": []}
        if not skill_md.is_file():
            nested = list(d.glob("skills/*/SKILL.md"))
            if nested:
                row["problems"].append(
                    f"SKILL.md is nested at {nested[0].relative_to(d)} - "
                    "plugin layout; move the inner folder up one level")
            else:
                row["problems"].append("no SKILL.md")
            rows.append(row)
            continue
        fields, err = frontmatter(skill_md)
        if err:
            row["problems"].append(err)
        row["name"] = fields.get("name") or None
        row["description"] = fields.get("description", "")
        if not row["name"]:
            row["problems"].append("frontmatter has no name")
        elif row["name"] != d.name:
            row["problems"].append(
                f"name '{row['name']}' != folder '{d.name}' (slash command uses name)")
        if not row["description"]:
            row["problems"].append("no description - will never auto-trigger")
        rows.append(row)
    return rows


def main() -> int:
    # Windows consoles default to cp1252; descriptions often contain em-dashes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--known", default="",
                    help="comma-separated skill names the harness already lists")
    a = ap.parse_args()

    user_root = Path.home() / ".claude" / "skills"
    proj_root = Path(a.project) / ".claude" / "skills"
    rows = scan(user_root, "user")
    if proj_root.resolve() != user_root.resolve():
        rows += scan(proj_root, "project")

    known = {k.strip() for k in a.known.split(",") if k.strip()}
    seen: dict[str, str] = {}
    for r in rows:
        n = r["name"]
        if n:
            if n in seen:
                r["problems"].append(f"duplicate name, also in {seen[n]}")
            else:
                seen[n] = r["path"]
        r["registered"] = (n in known) if known else None

    if a.json:
        print(json.dumps(rows, indent=2))
        return 0

    ok = [r for r in rows if not r["problems"]]
    bad = [r for r in rows if r["problems"]]
    print(f"scanned {user_root}" + (f" and {proj_root}" if proj_root.is_dir() and proj_root.resolve() != user_root.resolve() else ""))
    print(f"{len(ok)} loadable, {len(bad)} with problems\n")

    width = max((len(r["name"] or r["dir"]) for r in rows), default=10)
    for r in ok:
        desc = r["description"]
        if not a.full and len(desc) > TRUNC:
            desc = desc[:TRUNC - 1] + "…"
        tag = ""
        if r["registered"] is False:
            tag = "  [NEW - not yet registered]"
        elif r["scope"] == "project":
            tag = "  [project]"
        print(f"  {r['name']:<{width}}  {desc}{tag}")

    if bad:
        print("\nproblems (these will not register):")
        for r in bad:
            print(f"  {r['dir']:<{width}}  " + "; ".join(r["problems"]))
    if known:
        new = [r["name"] for r in ok if r["registered"] is False]
        gone = sorted(known - {r["name"] for r in rows if r["name"]})
        if new:
            print(f"\nnew since harness index: {', '.join(new)}")
        if gone:
            print(f"listed by harness but no longer on disk: {', '.join(gone)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
