#!/usr/bin/env python3
"""skill-rollcall: take a roll call of installed agent skills.

Rebuilds the skill index the way the host agent does at startup - Claude Code, Codex,
Cursor, Gemini CLI, Copilot, OpenCode and the other Agent Skills hosts - then reports
who is present, who is new, and who is never going to show up - and why.

    python rollcall.py                      compact roll call for the detected host
    python rollcall.py --agent codex        another host's folders (or `all`)
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
# agentskills.io/specification: 1-64 chars, lowercase a-z 0-9 and single hyphens,
# description 1-1024 chars. Hosts that validate strictly skip anything else.
SPEC_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SPEC_NAME_MAX = 64
SPEC_DESC_MAX = 1024

# --------------------------------------------------------------------------- agents
# Where each host reads skills from. `user` roots live under $HOME; `project` entries
# are folder names looked for from the working directory up to the git root (every
# host here walks up the same way). `.agents/skills` is the shared convention that
# Codex, Cursor, Gemini CLI, Copilot, OpenCode, Amp, Cline, Zed and Warp all read, so
# rows from it are labelled `agents` rather than one host. `env` are the variables a
# host sets in the shells it spawns; detection is best effort and --agent overrides it.
# Sources: agentskills.io, each host's docs, the `skills` CLI agent table (2026-09).
AGENTS: dict[str, dict] = {
    "claude":    {"label": "Claude Code",      "user": ["~/.claude/skills"],
                  "project": [".claude/skills"], "env": ["CLAUDECODE"]},
    "codex":     {"label": "Codex",            "user": ["~/.agents/skills", "~/.codex/skills"],
                  "project": [".agents/skills"], "env": ["CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED"]},
    "cursor":    {"label": "Cursor",           "user": ["~/.cursor/skills"],
                  "project": [".agents/skills"], "env": ["CURSOR_AGENT"]},
    "gemini":    {"label": "Gemini CLI",       "user": ["~/.gemini/skills"],
                  "project": [".agents/skills"], "env": ["GEMINI_CLI"]},
    "copilot":   {"label": "GitHub Copilot",   "user": ["~/.copilot/skills"],
                  "project": [".agents/skills"], "env": []},
    "opencode":  {"label": "OpenCode",         "user": ["~/.config/opencode/skills"],
                  "project": [".agents/skills"], "env": []},
    "amp":       {"label": "Amp",              "user": ["~/.config/agents/skills"],
                  "project": [".agents/skills"], "env": []},
    "goose":     {"label": "Goose",            "user": ["~/.config/goose/skills"],
                  "project": [".goose/skills"], "env": []},
    "kiro":      {"label": "Kiro",             "user": ["~/.kiro/skills"],
                  "project": [".kiro/skills"], "env": []},
    "windsurf":  {"label": "Windsurf",         "user": ["~/.codeium/windsurf/skills"],
                  "project": [".windsurf/skills"], "env": []},
    "universal": {"label": "Cline / Zed / Warp", "user": ["~/.agents/skills"],
                  "project": [".agents/skills"], "env": []},
}
SHARED_ROOTS = ("~/.agents/skills", ".agents/skills")


def detect_host() -> tuple[str | None, str | None]:
    """(agent key, the env var that gave it away) or (None, None)."""
    for key, spec in AGENTS.items():
        for var in spec["env"]:
            if os.environ.get(var):
                return key, var
    return None, None


def owner_of(root_spec: str, agent: str) -> str:
    return "agents" if root_spec in SHARED_ROOTS else agent


# --------------------------------------------------------------------------- model

@dataclass
class Skill:
    dir: str                      # folder name on disk
    path: str                     # absolute folder path
    scope: str                    # user | project | add-dir | plugin | skills-dir plugin | dir
    agent: str = "claude"         # which host's folder this came from (`agents` = shared)
    name: str | None = None       # frontmatter name (what /slash uses)
    description: str = ""
    errors: list[str] = field(default_factory=list)    # will not register
    warnings: list[str] = field(default_factory=list)  # registers, but...
    registered: bool | None = None                     # vs --known; None = unknown
    fixable: list[dict] = field(default_factory=list)  # planned repairs
    audit: list[dict] = field(default_factory=list)    # --audit findings
    est_tokens: int = 0
    visible_to: list[str] = field(default_factory=list)  # hosts that read this folder
    frontmatter_keys: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.name or self.dir

    @property
    def where(self) -> str:
        return f"{self.agent} {self.scope}"


@dataclass
class Root:
    path: Path
    scope: str
    agent: str                    # owner label for rows (`agents` when shared)
    visible_to: list[str]         # every selected host that reads this root
    spec: str = ""                # the `~/...` or `.x/skills` string it came from
    count: int = -1               # skills found; -1 = folder absent


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


def load_skill(folder: Path, skill_md: Path, scope: str, name_prefix: str = "",
               agent: str = "claude", visible_to: list[str] | None = None) -> Skill:
    s = Skill(dir=folder.name, path=str(folder), scope=scope, agent=agent,
              visible_to=list(visible_to or [agent]))
    fields, err = frontmatter(skill_md)
    if err:
        s.errors.append(err)
    raw_name = fields.get("name") or None
    s.name = f"{name_prefix}{raw_name}" if raw_name else None
    s.description = fields.get("description", "")
    if not raw_name:
        s.errors.append("frontmatter has no name")
    else:
        if raw_name != folder.name and scope in ("user", "project", "add-dir"):
            s.warnings.append(
                f"name '{raw_name}' != folder '{folder.name}' (the slash command uses name; "
                "the Agent Skills spec says they must match)")
            s.fixable.append({"action": "rename", "from": str(folder),
                              "to": str(folder.parent / raw_name)})
        if len(raw_name) > SPEC_NAME_MAX or not SPEC_NAME.match(raw_name):
            s.warnings.append(
                f"name '{raw_name}' is outside the Agent Skills spec (1-{SPEC_NAME_MAX} chars, "
                "lowercase a-z 0-9, single hyphens) - strict hosts skip it")
    if not s.description:
        s.warnings.append("no description - registers but will never auto-trigger")
    elif len(s.description) > SPEC_DESC_MAX:
        s.warnings.append(
            f"description is {len(s.description)} chars; the spec caps it at {SPEC_DESC_MAX} - "
            "hosts truncate or shorten it, so front-load the trigger words")
    s.est_tokens = (len(s.label) + len(s.description)) // CHARS_PER_TOKEN
    s.frontmatter_keys = list(fields)
    return s


# --------------------------------------------------------------------------- discovery

def scan_dir(root: Path, scope: str, agent: str = "claude",
             visible_to: list[str] | None = None) -> list[Skill]:
    """One level of `<name>/SKILL.md`, plus skills-directory plugins
    (`<plugin>/.claude-plugin/plugin.json` + `<plugin>/skills/<name>/SKILL.md`)."""
    out: list[Skill] = []
    if not root.is_dir():
        return out
    vis = list(visible_to or [agent])
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        skill_md = d / "SKILL.md"
        manifest = d / ".claude-plugin" / "plugin.json"
        nested = sorted(d.glob("skills/*/SKILL.md"))
        if skill_md.is_file():
            out.append(load_skill(d, skill_md, scope, agent=agent, visible_to=vis))
            continue
        if nested and manifest.is_file() and "claude" in vis:
            # valid skills-directory plugin: Claude Code loads these as plugin:skill
            pname = d.name
            try:
                pname = json.loads(manifest.read_text(encoding="utf-8")).get("name", d.name)
            except (OSError, ValueError):
                pass
            for n in nested:
                out.append(load_skill(n.parent, n, "skills-dir plugin", f"{pname}:",
                                      agent=agent, visible_to=["claude"]))
            continue
        s = Skill(dir=d.name, path=str(d), scope=scope, agent=agent, visible_to=vis)
        if nested:
            hint = ("with no .claude-plugin/plugin.json " if "claude" in vis else "")
            s.errors.append(
                f"SKILL.md is nested at {nested[0].relative_to(d).as_posix()} {hint}- a skills "
                "repo or plugin copied whole into the skills folder; every host looks exactly "
                "one level deep, so move the inner folder up one level"
                + (" (or add a manifest)" if "claude" in vis else ""))
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
        out.append(load_skill(skill_md.parent, skill_md, "plugin", f"{pname}:", visible_to=["claude"]))
    # synced/<plugin>@synced/skills/<skill>/SKILL.md
    for skill_md in sorted(plugins_root.glob("synced/*/skills/*/SKILL.md")):
        pname = skill_md.parents[2].name.removesuffix("@synced")
        out.append(load_skill(skill_md.parent, skill_md, "plugin", f"{pname}:", visible_to=["claude"]))
    return out


def project_roots(start: Path, relnames: list[str], stop: set[Path] | None = None) -> list[tuple[Path, str]]:
    """Every host walks from the working directory up to the repository root,
    picking up each of its project folders on the way. Returns (path, relname).
    The walk never enters a home directory: `~/.claude`, `~/.agents` and friends are
    user config, not a project, even when the start folder has no git root."""
    roots: list[tuple[Path, str]] = []
    stop = stop or set()
    cur = start.resolve()
    while cur not in stop:
        for rel in relnames:
            cand = cur.joinpath(*rel.split("/"))
            if cand.is_dir():
                roots.append((cand, rel))
        if (cur / ".git").exists() or cur.parent == cur:
            break
        cur = cur.parent
    return roots


def home_dirs(home: Path) -> set[Path]:
    """The given --home and the real one, resolved, as walk-up stop points."""
    out = {home.resolve()}
    try:
        out.add(Path.home().resolve())
    except RuntimeError:
        pass
    return out


def build_roots(agents: list[str], home: Path, claude_home: Path, project: Path) -> list[Root]:
    """The union of every selected host's skill folders, deduplicated by path, each
    tagged with the hosts that read it."""
    def expand(spec: str) -> Path:
        if spec.startswith("~/.claude/"):
            return claude_home.joinpath(*spec[len("~/.claude/"):].split("/"))
        return home.joinpath(*spec[2:].split("/"))

    roots: dict[Path, Root] = {}
    for a in agents:
        for spec in AGENTS[a]["user"]:
            p = expand(spec)
            key = p.resolve() if p.exists() else p
            if key in roots:
                roots[key].visible_to.append(a)
            else:
                roots[key] = Root(p, "user", owner_of(spec, a), [a], spec)
    rel_owner: dict[str, tuple[str, list[str]]] = {}
    for a in agents:
        for rel in AGENTS[a]["project"]:
            owner, vis = rel_owner.setdefault(rel, (owner_of(rel, a), []))
            vis.append(a)
    for p, rel in project_roots(project, list(rel_owner), home_dirs(home)):
        key = p.resolve()
        if key in roots:          # a project under $HOME would re-find a user root
            continue
        owner, vis = rel_owner[rel]
        roots[key] = Root(p, "project", owner, list(vis), rel)
    return list(roots.values())


# --------------------------------------------------------------------------- toml (Codex)

def read_toml(path: Path) -> dict:
    """Parse a TOML file with tomllib (3.11+) or a small stdlib fallback that covers
    what agent config files use: tables, arrays of tables, dotted and quoted keys,
    strings, numbers, booleans, arrays and inline tables. Returns {} when unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        import tomllib  # type: ignore
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return {}
    except ImportError:
        try:
            return _toml_fallback(text)
        except ValueError:
            return {}


def _toml_fallback(text: str) -> dict:
    root: dict = {}
    table: dict = root
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = _toml_strip_comment(lines[i]).strip()
        i += 1
        if not line:
            continue
        if line.startswith("[["):
            keys = _toml_keys(line[2:line.index("]]")])
            parent = _toml_descend(root, keys[:-1])
            arr = parent.setdefault(keys[-1], [])
            if not isinstance(arr, list):
                raise ValueError("not an array of tables")
            table = {}
            arr.append(table)
            continue
        if line.startswith("["):
            table = _toml_descend(root, _toml_keys(line[1:line.index("]")]))
            continue
        if "=" not in line:
            raise ValueError(f"bad line: {line}")
        k, _, v = line.partition("=")
        v = v.strip()
        # multi-line arrays / inline tables: pull lines until brackets balance
        while v and v[0] in "[{" and _toml_unbalanced(v) and i < len(lines):
            v += " " + _toml_strip_comment(lines[i]).strip()
            i += 1
        keys = _toml_keys(k)
        target = _toml_descend(table, keys[:-1])
        target[keys[-1]] = _toml_value(v)
    return root


def _toml_strip_comment(line: str) -> str:
    in_str = None
    j = 0
    while j < len(line):
        ch = line[j]
        if in_str:
            if ch == "\\" and in_str == '"':
                j += 2                      # skip the escaped character too
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "#":
            return line[:j]
        j += 1
    return line


def _toml_keys(s: str) -> list[str]:
    return [k.strip().strip("\"'") for k in re.findall(r'"[^"]*"|\'[^\']*\'|[^.]+', s.strip())]


def _toml_descend(d: dict, keys: list[str]) -> dict:
    for k in keys:
        nxt = d.setdefault(k, {})
        if isinstance(nxt, list):          # [[x]] then [x.y]: descend into the last item
            nxt = nxt[-1]
        if not isinstance(nxt, dict):
            raise ValueError(f"{k} is not a table")
        d = nxt
    return d


def _toml_unbalanced(v: str) -> bool:
    depth = 0
    in_str = None
    for ch in v:
        if in_str:
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    return depth > 0 or in_str is not None


def _toml_split(body: str) -> list[str]:
    parts, buf, depth, in_str = [], "", 0, None
    for ch in body:
        if in_str:
            buf += ch
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
            buf += ch
        elif ch in "[{":
            depth += 1
            buf += ch
        elif ch in "]}":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _toml_value(v: str):
    v = v.strip()
    if not v:
        raise ValueError("empty value")
    if v[0] == '"':
        end = _toml_str_end(v, '"')
        return bytes(v[1:end], "utf-8").decode("unicode_escape") if "\\" in v[1:end] else v[1:end]
    if v[0] == "'":
        return v[1:_toml_str_end(v, "'")]
    if v[0] == "[":
        return [_toml_value(p) for p in _toml_split(v[1:v.rindex("]")])]
    if v[0] == "{":
        out: dict = {}
        for p in _toml_split(v[1:v.rindex("}")]):
            k, _, val = p.partition("=")
            keys = _toml_keys(k)
            _toml_descend(out, keys[:-1])[keys[-1]] = _toml_value(val)
        return out
    v = v.split("#", 1)[0].strip()
    if v in ("true", "false"):
        return v == "true"
    try:
        return int(v.replace("_", ""))
    except ValueError:
        pass
    try:
        return float(v.replace("_", ""))
    except ValueError:
        return v                          # dates and anything else: keep the text


def _toml_str_end(v: str, q: str) -> int:
    i = 1
    while i < len(v):
        if v[i] == "\\" and q == '"':
            i += 2
            continue
        if v[i] == q:
            return i
        i += 1
    raise ValueError("unterminated string")


def codex_disabled(home: Path, project: Path) -> dict[Path, str]:
    """Skills switched off with [[skills.config]] in ~/.codex/config.toml or a project's
    .codex/config.toml -> {resolved skill folder: file that disabled it}."""
    files = [home / ".codex" / "config.toml"]
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        files.insert(0, Path(codex_home) / "config.toml")
    for p, _ in project_roots(project, [".codex"], home_dirs(home)):
        files.append(p / "config.toml")
    out: dict[Path, str] = {}
    for f in files:
        if not f.is_file():
            continue
        cfg = read_toml(f).get("skills", {})
        entries = cfg.get("config", []) if isinstance(cfg, dict) else []
        for e in entries:
            if isinstance(e, dict) and e.get("enabled") is False and e.get("path"):
                p = Path(os.path.expanduser(str(e["path"])))
                if p.name.lower() == "skill.md":
                    p = p.parent
                try:
                    out[p.resolve()] = str(f)
                except OSError:
                    pass
    return out


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
        others = [a for a in s.visible_to if a != "claude"]
        if "context" in s.frontmatter_keys and others:
            s.warnings.append("frontmatter `context:` is Claude Code-only; other hosts ignore it")
        if "allowed-tools" in s.frontmatter_keys and "kiro" in others:
            s.warnings.append("frontmatter `allowed-tools` is ignored by Kiro CLI")
    for i, a in enumerate(ok):
        for b in ok[i + 1:]:
            # only siblings some host sees together can mis-trigger against each other;
            # the same skill installed for two hosts is a copy, not an overlap
            if a.name == b.name or not set(a.visible_to) & set(b.visible_to):
                continue
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
# Invoking bypass is high; merely naming the mode is review - a tool that reports on
# permission settings has to say "bypassPermissions" to do its job.
# Claude Code's skip-permissions flag and bypass mode; Codex's bypass-approvals-and-sandbox
# flag and its short alias, which Gemini CLI shares.
SKIP_PERMS = re.compile(r"dangerously[-]skip[-]permissions|permission-mode[= ]+bypass[P]ermissions"
                        r"|dangerously[-]bypass[-]approvals[-]and[-]sandbox|-[-]yolo\b", re.I)
NAMES_BYPASS = re.compile(r"bypass[P]ermissions|approval[_]policy\s*=\s*\"never\"", re.I)
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
               "openai.com", "chatgpt.com", "cursor.com", "agentskills.io", "skills.sh",
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
                            "detail": "invokes bypassing the permission / approval prompt"})
        elif (m := NAMES_BYPASS.search(text)):
            line = text.count("\n", 0, m.start()) + 1
            s.audit.append({"severity": "review", "kind": "names-bypass", "file": f"{rel}:{line}",
                            "detail": "mentions a permission-bypass mode - fine in a settings or "
                                      "permissions tool, read it in context"})
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


def tilde(p: Path, home: Path) -> str:
    try:
        return "~/" + p.resolve().relative_to(home.resolve()).as_posix()
    except ValueError:
        return str(p)


def report(skills: list[Skill], roots: list[Root], known: set[str], a, fix_log: list[str],
           host: str, host_why: str, home: Path) -> int:
    errors = [s for s in skills if s.errors]
    warned = [s for s in skills if not s.errors and s.warnings]
    clean = [s for s in skills if not s.errors]
    multi = len({s.agent for s in skills} | {r.agent for r in roots if r.count > 0}) > 1
    scopes = sorted({s.where if multi else s.scope for s in skills})
    print(f"{len(clean)} loadable, {len(errors)} will not register, "
          f"{len(warned)} with warnings   scopes: {', '.join(scopes) or 'none'}")
    total = sum(s.est_tokens for s in clean)
    print(f"context cost: ~{total:,} tokens of descriptions loaded every session")
    present = [r for r in roots if r.count >= 0]
    absent = len(roots) - len(present)
    shown = " · ".join(f"{r.agent} {r.scope} {tilde(r.path, home) if r.scope == 'user' else r.spec} "
                       f"({r.count})" for r in present)
    print(f"host: {host} ({host_why})")
    print(f"roots: {shown or 'none present'}"
          + (f" · {absent} configured root{'s' if absent != 1 else ''} absent" if absent else "") + "\n")

    width = max((len(s.label) for s in skills), default=10)
    if not a.problems_only:
        if multi:
            groups: dict[str, list[Skill]] = {}
            for s in clean:
                groups.setdefault(s.where, []).append(s)
            for where, rows in groups.items():
                print(f"[{where}]")
                for s in rows:
                    tag = "  [NEW - not yet registered]" if s.registered is False else ""
                    print(f"  {s.label:<{width}}  {trunc(s.description, a.full)}{tag}")
                print()
        else:
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

def parse_agents(value: str, detected: str | None) -> tuple[list[str], str, str]:
    """-> (agent keys to scan, host label, why)."""
    if value == "auto":
        if detected:
            return [detected], detected, "detected"
        return list(AGENTS), "all", "no host marker in the environment; pass --agent to narrow"
    if value == "all":
        return list(AGENTS), "all", "--agent all"
    keys = [k.strip() for k in value.split(",") if k.strip()]
    bad = [k for k in keys if k not in AGENTS]
    if bad:
        raise SystemExit(f"unknown agent {', '.join(bad)}; choose from {', '.join(AGENTS)} or all")
    return keys, ",".join(keys), "--agent"


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default="auto",
                    help="which host's skill folders to scan: " + ", ".join(AGENTS)
                         + ", a comma list, or all (default: detect from the environment, else all)")
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
    ap.add_argument("--add-dir", action="append", default=[],
                    help="extra directory whose project skill folders (.claude/skills, .agents/skills, ...) to include")
    ap.add_argument("--skills-dir", action="append", default=[],
                    help="scan this folder of <name>/SKILL.md directly, e.g. a skills repo before publishing")
    ap.add_argument("--no-plugins", action="store_true", help="skip ~/.claude/plugins")
    ap.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    ap.add_argument("--claude-home", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    home = Path(a.home)
    claude_home = Path(a.claude_home) if a.claude_home else home / ".claude"
    detected, var = detect_host()
    agents, host, why = parse_agents(a.agent, detected)
    if a.agent == "auto" and detected:
        why = f"{var} set"

    roots = build_roots(agents, home, claude_home, Path(a.project))
    skills: list[Skill] = []
    seen_roots = {r.path.resolve() for r in roots if r.path.exists()}
    for r in roots:
        if r.path.is_dir():
            found = scan_dir(r.path, r.scope, r.agent, r.visible_to)
            r.count = len(found)
            skills += found
    project_rels = sorted({rel for k in agents for rel in AGENTS[k]["project"]})
    rel_vis = {rel: [k for k in agents if rel in AGENTS[k]["project"]] for rel in project_rels}
    for d in a.add_dir:
        for rel in project_rels:
            r = Path(d).joinpath(*rel.split("/"))
            if r.is_dir() and r.resolve() not in seen_roots:
                seen_roots.add(r.resolve())
                skills += scan_dir(r, "add-dir", owner_of(rel, rel_vis[rel][0]), rel_vis[rel])
    for d in a.skills_dir:
        r = Path(d)
        if r.resolve() not in seen_roots:
            seen_roots.add(r.resolve())
            skills += scan_dir(r, "dir", "dir", agents)
    if not a.no_plugins and "claude" in agents:
        skills += scan_plugin_cache(claude_home / "plugins")
    if "codex" in agents:
        disabled = codex_disabled(home, Path(a.project))
        for s in skills:
            try:
                src = disabled.get(Path(s.path).resolve())
            except OSError:
                src = None
            if src:
                s.warnings.append(f"disabled for Codex in {src} ([[skills.config]] enabled = false)")

    known = {k.strip() for k in a.known.split(",") if k.strip()}
    first: dict[str, Skill] = {}
    for s in skills:
        if s.name:
            other = first.get(s.name)
            if other is None:
                first[s.name] = s
            else:
                shared = sorted(set(other.visible_to) & set(s.visible_to))
                if shared:
                    s.warnings.append(
                        f"duplicate name - also at {other.path}; one silently wins"
                        + (f" (both visible to {', '.join(shared)})" if multi_agent(skills) else ""))
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
        rows = []
        for s in skills:
            d = asdict(s)
            d["label"] = s.label
            d["where"] = s.where
            rows.append(d)
        print(json.dumps(rows, indent=2))
        bad = any(s.errors for s in skills) or any(f["severity"] == "high" for s in skills for f in s.audit)
        return 1 if (a.strict and bad) else 0
    return report(skills, roots, known, a, fix_log, host, why, home)


def multi_agent(skills: list[Skill]) -> bool:
    return len({s.agent for s in skills}) > 1


if __name__ == "__main__":
    sys.exit(main())
