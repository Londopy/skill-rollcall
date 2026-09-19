"""Render docs/demo.png: real rollcall output on a fixture set, styled as a terminal.

Run from the repo root:  python docs/make_demo.py
Needs Pillow (dev-only; the tool itself has no dependencies).
"""
from __future__ import annotations

import io
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "skill-rollcall" / "scripts"))
import rollcall  # noqa: E402

FONT = next(p for p in [Path("C:/Windows/Fonts/CascadiaMono.ttf"),
                        Path("C:/Windows/Fonts/consola.ttf"),
                        Path("/System/Library/Fonts/Menlo.ttc"),
                        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")] if p.exists())

BG, FG, DIM = (24, 26, 32), (220, 223, 228), (120, 126, 138)
GREEN, YELLOW, RED, BLUE, PURPLE = (126, 204, 140), (230, 190, 90), (240, 110, 110), (110, 170, 240), (190, 140, 240)


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fixture(home: Path) -> None:
    s = home / "skills"
    write(s / "strict-api" / "SKILL.md", "---\nname: strict-api\ndescription: Use when the user says 'no hallucinations' or 'verify APIs'. Prevents calling methods that do not exist.\n---\n")
    write(s / "grill-me" / "SKILL.md", "---\nname: grill-me\ndescription: Interview the user relentlessly about a plan until reaching shared understanding. Use when the user says 'grill me'.\n---\n")
    write(s / "prime-backend" / "SKILL.md", "---\nname: prime-backend\ndescription: Primes the agent with focused understanding of the backend portion of the codebase without loading unrelated code.\n---\n")
    write(s / "prime-frontend" / "SKILL.md", "---\nname: prime-frontend\ndescription: Primes the agent with focused understanding of the frontend portion of the codebase without loading unrelated code.\n---\n")
    write(s / "deploy-helper" / "SKILL.md", "---\nname: deploy-helper\n---\n")
    write(s / "dragged-plugin" / "skills" / "changelog" / "SKILL.md", "---\nname: changelog\ndescription: Use when writing release notes.\n---\n")
    write(s / "just-a-readme" / "README.md", "# oops\n")
    write(s / "team-plugin" / ".claude-plugin" / "plugin.json", '{"name": "team"}')
    write(s / "team-plugin" / "skills" / "runbook" / "SKILL.md", "---\nname: runbook\ndescription: Use when an incident needs a runbook.\n---\n")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        fixture(home)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rollcall.main(["--claude-home", str(home), "--no-plugins", "--project", tmp,
                           "--known", "strict-api,grill-me,prime-backend,prime-frontend,deploy-helper,old-skill",
                           "--lint", "--fix"])
        out = buf.getvalue().replace(str(home / "skills"), "~/.claude/skills").replace("\\", "/")

    lines = ["$ python rollcall.py --known $HARNESS --lint --fix", ""] + out.rstrip().splitlines()
    lines = [l if len(l) <= 100 else l[:99] + "…" for l in lines]
    font = ImageFont.truetype(str(FONT), 15)
    lh = 22
    pad = 28
    width = 980
    height = pad * 2 + lh * len(lines) + 30
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    # title bar dots
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([pad + i * 22, 14, pad + i * 22 + 12, 26], fill=c)
    d.text((width // 2 - 60, 12), "skill-rollcall", fill=DIM, font=font)

    y = pad + 20
    for line in lines:
        color = FG
        if line.startswith("$ "):
            color = GREEN
        elif line.startswith(("warnings", "errors", "fix plan", "new since", "listed by harness", "context cost")):
            color = BLUE
        elif "[NEW" in line:
            color = GREEN
        elif "[skills-dir plugin]" in line or "[project]" in line:
            color = PURPLE
        elif re.match(r"\s{2}\S.*(will not register|no SKILL.md|nested at|never closed|no frontmatter|has no name)", line):
            color = RED
        elif re.match(r"\s{2}\S.*(overlaps|too short|no 'use when|never auto-trigger|!= folder|duplicate|tokens in every)", line):
            color = YELLOW
        elif line.strip().startswith(("would move", "(dry run")):
            color = DIM
        d.text((pad, y), line, fill=color, font=font)
        y += lh
    outp = ROOT / "docs" / "demo.png"
    img.save(outp, optimize=True)
    print(f"wrote {outp} ({width}x{height})")


if __name__ == "__main__":
    main()
