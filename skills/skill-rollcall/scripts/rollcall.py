#!/usr/bin/env python3
"""skill-rollcall: take a roll call of installed Claude Code skills.

Rebuilds the skill index the way Claude Code does at startup, then reports who is
present, who is new, and who is never going to show up - and why.

    python rollcall.py                      compact roll call
    python rollcall.py --known a,b,c        mark rows registered / NEW against the
                                            names the harness already lists
    python rollcall.py --lint               description quality + context cost
    python rollcall.py --audit              scan skill contents for injection,
                                            hidden text, pipe-to-shell, exfil hosts
    python rollcall.py --fix                show what --fix --apply would change
    python rollcall.py --fix --apply        un-nest / rename broken skill folders
    python rollcall.py --strict             exit 1 if any error-level finding
    python rollcall.py --json               everything, machine-readable

Stdlib only. Read-only unless you pass --fix --apply.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

TRUNC = 120
CHARS_PER_TOKEN = 4          # rough, good enough for a budget line
SHORT_DESC = 40              # below this a description rarely triggers
HEAVY_DESC_TOKENS = 250      # above this it is eating context every session
SIMILAR = 0.6                # jaccard on content words -> "overlaps with"
TRIGGER_CUE = re.compile(
    r"\buse (?:\w+ )?(?:when|this|for|it|after|before|at|to|in|on|during|whenever|proactively)\b"
    r"|\brun (?:when|before|after|this)\b|\bwhenever\b|\btrigger|\bwhen (?:the user|asked|you|a |an )",
    re.I)

# --------------------------------------------------------------------------- model

@dataclass
class Skill:
    dir: str                      # folder name on disk
    path: str                     # absolute folder path
    scope: str                    # user | project | add-dir | plugin | skills-dir plugin
    name: str | None = None       # frontmatter name (what /slash uses)
    description: str = ""
    errors: list[str] = field(default_factory=list)    # will not register
    warnings: list[str] = field(default_factory=list)  # registers, but...
    registered: bool | None = None                     # vs --known; None = unknown
    fixable: list[dict] = field(default_factory=list)  # planned repairs
    audit: list[dict] = field(default_factory=list)    # --audit findings
    est_tokens: int = 0

    @property
    def label(self) -> str:
        return self.name or self.dir


# --------------------------------------------------------------------------- parsing

def frontmatter(path: Path) -> tuple[dict, str | None]:
    """Return (fields, error). Only top-level `key: value` lines matter to the
    harness (name, description), so a full YAML parser is not worth a dependency.
    Folded (`>`) and literal (`|`) blocks are joined into one line."""
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
            fields[key] = (fields[key] + " " + line.strip()).strip()
            continue
        if ":" in line and not line.startswith("#"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val in (">", ">-", "|", "|-"):
                val = ""
            fields[key] = val.strip("\"'")
    return fields, "frontmatter never closed (missing second ---)"


def load_skill(folder: Path, skill_md: Path, scope: str, name_prefix: str = "") -> Skill:
    s = Skill(dir=folder.name, path=str(folder), scope=scope)
    fields, err = frontmatter(skill_md)
    if err:
        s.errors.append(err)
    raw_name = fields.get("name") or None
    s.name = f"{name_prefix}{raw_name}" if raw_name else None
    s.description = fields.get("description", "")
    if not raw_name:
        s.errors.append("frontmatter has no name")
    elif raw_name != folder.name and scope in ("user", "project", "add-dir"):
        s.warnings.append(
            f"name '{raw_name}' != folder '{folder.name}' (the slash command uses name)")
        s.fixable.append({"action": "rename", "from": str(folder),
                          "to": str(folder.parent / raw_name)})
    if not s.description:
        s.warnings.append("no description - registers but will never auto-trigger")
    s.est_tokens = (len(s.label) + len(s.description)) // CHARS_PER_TOKEN
    return s


# --------------------------------------------------------------------------- discovery

def scan_dir(root: Path, scope: str) -> list[Skill]:
    """One level of `<name>/SKILL.md`, plus skills-directory plugins
    (`<plugin>/.claude-plugin/plugin.json` + `<plugin>/skills/<name>/SKILL.md`)."""
    out: list[Skill] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        skill_md = d / "SKILL.md"
        manifest = d / ".claude-plugin" / "plugin.json"
        nested = sorted(d.glob("skills/*/SKILL.md"))
        if skill_md.is_file():
            out.append(load_skill(d, skill_md, scope))
            continue
        if nested and manifest.is_file():
            # valid skills-directory plugin: skills load as plugin:skill
            pname = d.name
            try:
                pname = json.loads(manifest.read_text(encoding="utf-8")).get("name", d.name)
            except (OSError, ValueError):
                pass
            for n in nested:
                out.append(load_skill(n.parent, n, "skills-dir plugin", f"{pname}:"))
            continue
        s = Skill(dir=d.name, path=str(d), scope=scope)
        if nested:
            s.errors.append(
                f"SKILL.md is nested at {nested[0].relative_to(d).as_posix()} with no "
                ".claude-plugin/plugin.json - a plugin copied whole into the skills folder; "
                "move the inner folder up one level (or add a manifest)")
            for n in nested:
                s.fixable.append({"action": "unnest", "from": str(n.parent),
                                  "to": str(root / n.parent.name)})
        else:
            s.errors.append("no SKILL.md")
        out.append(s)
    return out


def scan_plugin_cache(plugins_root: Path) -> list[Skill]:
    out: list[Skill] = []
    # cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md
    for skill_md in sorted(plugins_root.glob("cache/*/*/*/skills/*/SKILL.md")):
        pname = skill_md.parents[3].name
        out.append(load_skill(skill_md.parent, skill_md, "plugin", f"{pname}:"))
    # synced/<plugin>@synced/skills/<skill>/SKILL.md
    for skill_md in sorted(plugins_root.glob("synced/*/skills/*/SKILL.md")):
        pname = skill_md.parents[2].name.removesuffix("@synced")
        out.append(load_skill(skill_md.parent, skill_md, "plugin", f"{pname}:"))
    return out


def project_roots(start: Path) -> list[Path]:
    """The harness walks from the working directory up to the repository root,
    picking up every .claude/skills on the way."""
    roots = []
    cur = start.resolve()
    while True:
        cand = cur / ".claude" / "skills"
        if cand.is_dir():
            roots.append(cand)
        if (cur / ".git").exists() or cur.parent == cur:
            break
        cur = cur.parent
    return roots


# --------------------------------------------------------------------------- lint

def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z-]{3,}", text.lower())}


def lint(skills: list[Skill]) -> None:
    ok = [s for s in skills if not s.errors and s.description]
    words = {id(s): content_words(s.description) for s in ok}
    for s in ok:
        d = s.description
        if len(d) < SHORT_DESC:
            s.warnings.append(f"description is {len(d)} chars - too short to trigger reliably")
        if not TRIGGER_CUE.search(d):
            s.warnings.append("description has no 'use when ...' cue - say when to trigger")
        if s.est_tokens > HEAVY_DESC_TOKENS:
            s.warnings.append(f"~{s.est_tokens} tokens in every session - consider trimming")
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            wa, wb = words[id(a)], words[id(b)]
            if not wa or not wb:
                continue
            j = len(wa & wb) / len(wa | wb)
            if j >= SIMILAR:
                a.warnings.append(f"description overlaps with {b.label} ({j:.0%}) - may mis-trigger")
                b.warnings.append(f"description overlaps with {a.label} ({j:.0%}) - may mis-trigger")


# --------------------------------------------------------------------------- audit

HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
PIPE_TO_SHELL = re.compile(r"\b(curl|wget|iwr|Invoke-WebRequest)\b[^|\n]*\|\s*(sudo\s+)?(ba|z|)sh\b", re.I)
SKIP_PERMS = re.compile(r"dangerously[-]skip[-]permissions|bypass[P]ermissions", re.I)
PHRASES = [
    (re.compile(r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules|prompts)", re.I), "ignore-previous-instructions"),
    (re.compile(r"disregard (?:your|all|the|any) (?:instructions|rules|guidelines)", re.I), "disregard-instructions"),
    (re.compile(r"\b(?:do not|don'?t|never) (?:tell|inform|alert|notify|mention (?:this |it )?to) the user\b", re.I), "hide-from-user"),
    (re.compile(r"without (?:telling|informing|asking|notifying) the user", re.I), "act-without-user"),
    (re.compile(r"\bhide (?:this|it|these|that) from the user\b", re.I), "hide-from-user"),
    (re.compile(r"\byou are now\b", re.I), "persona-override"),
    (re.compile(r"\bpretend (?:you are|to be|you're)\b", re.I), "persona-override"),
]
HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")
KNOWN_HOSTS = ("github.com", "githubusercontent.com", "claude.com", "anthropic.com",
               "google.com", "microsoft.com", "python.org", "npmjs.com", "pypi.org",
               "shields.io", "mitre.org", "nist.gov", "example.com", "localhost",
               "127.0.0.1", ".invalid", ".test", ".localhost", "wikipedia.org", "w3.org")
B64 = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")
TEXT_EXT = {".md", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".txt", ".toml", ".ps1", ".bat", ".cmd"}


def audit(s: Skill) -> None:
    root = Path(s.path)
    hosts: set[str] = set()
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        # a guard's own test suite is the one honest home for dangerous strings
        in_tests = bool(re.search(r"(^|/)(tests?|_test|test_|fixtures?)", rel, re.I))
        high = "review" if in_tests else "high"
        if HIDDEN.search(text):
            s.audit.append({"severity": "high", "kind": "hidden-unicode", "file": rel,
                            "detail": "zero-width or bidi-override characters (can hide instructions)"})
        for m in PIPE_TO_SHELL.finditer(text):
            s.audit.append({"severity": high, "kind": "pipe-to-shell", "file": rel,
                            "detail": m.group(0)[:100]})
        if SKIP_PERMS.search(text):
            s.audit.append({"severity": high, "kind": "skips-permissions", "file": rel,
                            "detail": "references bypassing the permission prompt"})
        for rx, kind in PHRASES:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                s.audit.append({"severity": "review", "kind": kind, "file": f"{rel}:{line}",
                                "detail": m.group(0)})
        for m in B64.finditer(text):
            s.audit.append({"severity": "review", "kind": "encoded-blob", "file": rel,
                            "detail": f"{len(m.group(0))}-char base64-looking run"})
        hosts.update(h.lower() for h in HOST.findall(text))
    for h in sorted(hosts):
        if not any(h == k or h.endswith(k) for k in KNOWN_HOSTS):
            s.audit.append({"severity": "info", "kind": "external-host", "file": "", "detail": h})


# --------------------------------------------------------------------------- fix

def apply_fixes(skills: list[Skill], do_apply: bool) -> list[str]:
    log = []
    for s in skills:
        for f in s.fixable:
            src, dst = Path(f["from"]), Path(f["to"])
            if dst.exists():
                log.append(f"skip   {f['action']}: {dst} already exists")
                continue
            log.append(f"{'moved' if do_apply else 'would move':<10} {src}  ->  {dst}")
            if do_apply:
                shutil.move(str(src), str(dst))
        if do_apply and any(f["action"] == "unnest" for f in s.fixable):
            leftover = Path(s.path)
            # remove the now-empty plugin shell if nothing else lives in it
            try:
                if not any(p.is_file() for p in leftover.rglob("*")):
                    shutil.rmtree(leftover)
                    log.append(f"removed    empty shell {leftover}")
            except OSError as e:
                log.append(f"left       {leftover} ({e})")
    return log


# --------------------------------------------------------------------------- report

def trunc(text: str, full: bool) -> str:
    if full or len(text) <= TRUNC:
        return text
    return text[:TRUNC - 1] + "…"


def report(skills: list[Skill], known: set[str], a, fix_log: list[str]) -> int:
    errors = [s for s in skills if s.errors]
    warned = [s for s in skills if not s.errors and s.warnings]
    clean = [s for s in skills if not s.errors]
    scopes = sorted({s.scope for s in skills})
    print(f"{len(clean)} loadable, {len(errors)} will not register, "
          f"{len(warned)} with warnings   scopes: {', '.join(scopes) or 'none'}")
    total = sum(s.est_tokens for s in clean)
    print(f"context cost: ~{total:,} tokens of descriptions loaded every session\n")

    width = max((len(s.label) for s in skills), default=10)
    if not a.problems_only:
        for s in clean:
            tag = ""
            if s.registered is False:
                tag = "  [NEW - not yet registered]"
            elif s.scope not in ("user",):
                tag = f"  [{s.scope}]"
            print(f"  {s.label:<{width}}  {trunc(s.description, a.full)}{tag}")
        print()

    if warned:
        print("warnings (registers, but):")
        for s in warned:
            for w in s.warnings:
                print(f"  {s.label:<{width}}  {w}")
        print()
    if errors:
        print("errors (these will not register):")
        for s in errors:
            for e in s.errors:
                print(f"  {s.dir:<{width}}  {e}")
        print()
    if known:
        new = [s.label for s in clean if s.registered is False]
        gone = sorted(known - {s.label for s in skills if s.name})
        if new:
            print(f"new since harness index: {', '.join(new)}")
        if gone:
            print(f"listed by harness but no longer on disk: {', '.join(gone)}")
        if not new and not gone:
            print("harness index matches disk")
        print()
    if a.audit:
        findings = [(s, f) for s in skills for f in s.audit]
        high = [f for _, f in findings if f["severity"] == "high"]
        rev = [f for _, f in findings if f["severity"] == "review"]
        info = [f for _, f in findings if f["severity"] == "info"]
        print(f"audit: {len(high)} high, {len(rev)} to review, {len(info)} info")
        for sev in ("high", "review", "info"):
            for s, f in findings:
                if f["severity"] != sev:
                    continue
                where = f"{s.label}/{f['file']}" if f["file"] else s.label
                print(f"  [{sev:<6}] {f['kind']:<22} {where}: {f['detail']}")
        if rev:
            print("  'review' hits are phrases that are normal in a security or prompt-testing "
                  "skill; read them in context before deciding.")
        print()
    if a.fix:
        print("fix plan:" if not a.apply else "fixes applied:")
        for line in fix_log or ["  nothing to fix"]:
            print(f"  {line}")
        if fix_log and not a.apply:
            print("  (dry run - add --apply to do it)")
        print()
    if a.strict and (errors or any(f["severity"] == "high" for s in skills for f in s.audit)):
        return 1
    return 0


# --------------------------------------------------------------------------- main

def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--known", default="", help="comma-separated skill names the harness already lists")
    ap.add_argument("--full", action="store_true", help="do not truncate descriptions")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--problems-only", action="store_true", help="skip the table, show findings only")
    ap.add_argument("--lint", action="store_true", help="description quality checks")
    ap.add_argument("--audit", action="store_true", help="scan skill contents for risky patterns")
    ap.add_argument("--fix", action="store_true", help="plan repairs for un-nestable / renamable folders")
    ap.add_argument("--apply", action="store_true", help="with --fix: actually move folders")
    ap.add_argument("--strict", action="store_true", help="exit 1 on errors or high audit findings")
    ap.add_argument("--project", default=os.getcwd(), help="working directory to scan up from")
    ap.add_argument("--add-dir", action="append", default=[], help="extra directory whose .claude/skills to include")
    ap.add_argument("--skills-dir", action="append", default=[],
                    help="scan this folder of <name>/SKILL.md directly, e.g. a skills repo before publishing")
    ap.add_argument("--no-plugins", action="store_true", help="skip ~/.claude/plugins")
    ap.add_argument("--claude-home", default=str(Path.home() / ".claude"), help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    home = Path(a.claude_home)
    skills: list[Skill] = scan_dir(home / "skills", "user")
    # the walk-up from a project under $HOME would otherwise re-find the user scope
    seen_roots = {(home / "skills").resolve(), (Path.home() / ".claude" / "skills").resolve()}
    for r in project_roots(Path(a.project)):
        if r.resolve() not in seen_roots:
            seen_roots.add(r.resolve())
            skills += scan_dir(r, "project")
    for d in a.add_dir:
        r = Path(d) / ".claude" / "skills"
        if r.resolve() not in seen_roots:
            seen_roots.add(r.resolve())
            skills += scan_dir(r, "add-dir")
    for d in a.skills_dir:
        r = Path(d)
        if r.resolve() not in seen_roots:
            seen_roots.add(r.resolve())
            skills += scan_dir(r, "dir")
    if not a.no_plugins:
        skills += scan_plugin_cache(home / "plugins")

    known = {k.strip() for k in a.known.split(",") if k.strip()}
    first: dict[str, str] = {}
    for s in skills:
        if s.name:
            if s.name in first:
                s.warnings.append(f"duplicate name - also at {first[s.name]}; one silently wins")
            else:
                first[s.name] = s.path
        s.registered = (s.name in known) if (known and s.name) else None

    if a.lint:
        lint(skills)
    if a.audit:
        for s in skills:
            audit(s)
    fix_log: list[str] = []
    if a.fix:
        fix_log = apply_fixes(skills, a.apply)

    if a.json:
        print(json.dumps([asdict(s) | {"label": s.label} for s in skills], indent=2))
        bad = any(s.errors for s in skills) or any(f["severity"] == "high" for s in skills for f in s.audit)
        return 1 if (a.strict and bad) else 0
    return report(skills, known, a, fix_log)


if __name__ == "__main__":
    sys.exit(main())
