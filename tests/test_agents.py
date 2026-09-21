"""Tests for the multi-host layer of rollcall.py: which folders each agent reads, the
shared .agents/skills root, Codex's [[skills.config]], the Agent Skills spec checks
and the stdlib TOML fallback. Same throwaway --home / --claude-home as test_rollcall.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_rollcall import Base, skill, write  # noqa: E402
import rollcall  # noqa: E402


def host_skill(root: Path, name: str, desc: str = "Use when testing.") -> Path:
    d = root / name
    write(d / "SKILL.md", f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n")
    return d


# --------------------------------------------------------------------------- agents

class Agents(Base):
    def test_codex_reads_shared_and_own_user_roots(self):
        host_skill(self.fake_home / ".agents" / "skills", "shared-one")
        host_skill(self.fake_home / ".codex" / "skills", "codex-one")
        skill(self.home, "claude-one")
        rows = self.run_json("--agent", "codex")
        self.assertEqual(self.by_dir(rows, "shared-one")["where"], "agents user")
        self.assertEqual(self.by_dir(rows, "codex-one")["where"], "codex user")
        self.assertFalse(any(r["dir"] == "claude-one" for r in rows))
        self.assertEqual(sorted(self.by_dir(rows, "shared-one")["visible_to"]), ["codex"])

    def test_claude_does_not_see_agents_skills(self):
        host_skill(self.fake_home / ".agents" / "skills", "shared-one")
        skill(self.home, "claude-one")
        rows = self.run_json("--agent", "claude")
        self.assertEqual([r["dir"] for r in rows], ["claude-one"])

    def test_project_agents_skills_walks_up_to_git_root(self):
        host_skill(self.project / ".agents" / "skills", "repo-skill")
        sub = self.project / "a" / "b"
        sub.mkdir(parents=True)
        rows = self.run_json("--agent", "cursor", "--project", str(sub))
        row = self.by_dir(rows, "repo-skill")
        self.assertEqual(row["scope"], "project")
        self.assertEqual(row["agent"], "agents")
        # Claude walks the same tree but reads .claude/skills, not .agents/skills
        self.assertFalse(any(r["dir"] == "repo-skill"
                             for r in self.run_json("--agent", "claude", "--project", str(sub))))

    def test_all_dedupes_the_shared_root_and_labels_hosts(self):
        host_skill(self.fake_home / ".agents" / "skills", "shared-one")
        rows = self.run_json("--agent", "all")
        same = [r for r in rows if r["dir"] == "shared-one"]
        self.assertEqual(len(same), 1)                    # codex + universal, counted once
        self.assertEqual(sorted(same[0]["visible_to"]), ["codex", "universal"])
        rc, out = self.run_cli("--agent", "all")
        self.assertIn("host: all", out)
        self.assertIn("agents user", out)
        self.assertIn("configured root", out)               # the absent ones are counted

    def test_copy_in_another_host_is_not_a_duplicate(self):
        skill(self.home, "twin")
        host_skill(self.fake_home / ".agents" / "skills", "twin")
        rows = [r for r in self.run_json("--agent", "all") if r["name"] == "twin"]
        self.assertEqual(len(rows), 2)
        self.assertFalse(any("duplicate" in w for r in rows for w in r["warnings"]))

    def test_duplicate_within_one_host_is_flagged(self):
        host_skill(self.fake_home / ".agents" / "skills", "twin")
        host_skill(self.fake_home / ".codex" / "skills", "twin")
        rows = [r for r in self.run_json("--agent", "all") if r["name"] == "twin"]
        warns = [w for r in rows for w in r["warnings"]]
        self.assertTrue(any("duplicate name" in w and "codex" in w for w in warns))

    def test_unknown_agent_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--agent", "clippy")

    def test_host_detected_from_environment(self):
        skill(self.home, "c")
        host_skill(self.fake_home / ".agents" / "skills", "x")
        # keep only what Path.home() needs, so no real host marker leaks in
        keep = {k: v for k, v in os.environ.items() if k in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")}
        with mock.patch.dict(os.environ, {**keep, "CODEX_SANDBOX": "seatbelt"}, clear=True):
            self.assertEqual(rollcall.detect_host(), ("codex", "CODEX_SANDBOX"))
            rc, out = self.run_cli("--agent", "auto")
        self.assertIn("host: codex (CODEX_SANDBOX set)", out)
        self.assertNotIn("  c  ", out)
        with mock.patch.dict(os.environ, keep, clear=True):
            self.assertEqual(rollcall.detect_host(), (None, None))
            rc, out = self.run_cli("--agent", "auto")
        self.assertIn("host: all (no host marker", out)

    def test_codex_disabled_skill_is_a_warning(self):
        d = host_skill(self.fake_home / ".agents" / "skills", "muted")
        posix = str(d / "SKILL.md").replace("\\", "/")
        write(self.fake_home / ".codex" / "config.toml",
              'model = "gpt-5"\n\n[[skills.config]]\npath = "' + posix + '"\nenabled = false\n\n'
              '[[skills.config]]\npath = "/elsewhere/other/SKILL.md"\nenabled = true\n')
        row = self.by_dir(self.run_json("--agent", "codex"), "muted")
        self.assertTrue(any("disabled for Codex" in w for w in row["warnings"]))
        # a Claude-only run never reads Codex config
        skill(self.home, "muted")
        row = self.by_dir(self.run_json("--agent", "claude"), "muted")
        self.assertEqual(row["warnings"], [])

    def test_lint_does_not_overlap_a_skill_with_its_own_copy(self):
        desc = "Use when the user wants the backend primed with focused context."
        skill(self.home, "prime", desc)
        host_skill(self.fake_home / ".agents" / "skills", "prime", desc)
        rows = [r for r in self.run_json("--agent", "all", "--lint") if r["name"] == "prime"]
        self.assertFalse(any("overlaps" in w for r in rows for w in r["warnings"]))

    def test_lint_flags_claude_only_frontmatter_for_other_hosts(self):
        body = "---\nname: forked\ndescription: Use when forked testing.\ncontext: fork\n---\n"
        write(self.fake_home / ".agents" / "skills" / "forked" / "SKILL.md", body)
        row = self.by_dir(self.run_json("--agent", "codex", "--lint"), "forked")
        self.assertTrue(any("Claude Code-only" in w for w in row["warnings"]))
        write(self.home / "skills" / "forked" / "SKILL.md", body)
        row = self.by_dir(self.run_json("--agent", "claude", "--lint"), "forked")
        self.assertFalse(any("Claude Code-only" in w for w in row["warnings"]))

    def test_walk_up_from_a_gitless_folder_never_enters_home(self):
        host_skill(self.fake_home / ".agents" / "skills", "mine")
        nogit = self.fake_home / "work" / "loose"
        nogit.mkdir(parents=True)
        rows = [r for r in self.run_json("--agent", "codex", "--project", str(nogit)) if r["dir"] == "mine"]
        self.assertEqual([r["scope"] for r in rows], ["user"])    # once, and not as a project root

    def test_nested_error_mentions_manifest_only_for_claude(self):
        write(self.fake_home / ".agents" / "skills" / "dragged" / "skills" / "inner" / "SKILL.md",
              "---\nname: inner\ndescription: Use when inner.\n---\n")
        row = self.by_dir(self.run_json("--agent", "codex"), "dragged")
        self.assertTrue(any("nested" in e for e in row["errors"]))
        self.assertFalse(any("plugin.json" in e for e in row["errors"]))
        self.assertEqual(row["fixable"][0]["action"], "unnest")


# --------------------------------------------------------------------------- spec

class Spec(Base):
    def test_name_outside_spec_warns(self):
        write(self.home / "skills" / "Bad_Name" / "SKILL.md",
              "---\nname: Bad_Name\ndescription: Use when bad.\n---\n")
        row = self.by_dir(self.run_json(), "Bad_Name")
        self.assertEqual(row["errors"], [])
        self.assertTrue(any("outside the Agent Skills spec" in w for w in row["warnings"]))
        long = "a" * 70
        skill(self.home, long)
        row = self.by_dir(self.run_json(), long)
        self.assertTrue(any("outside the Agent Skills spec" in w for w in row["warnings"]))

    def test_spec_compliant_name_has_no_spec_warning(self):
        skill(self.home, "pdf-processing-2")
        row = self.by_dir(self.run_json(), "pdf-processing-2")
        self.assertFalse(any("spec" in w for w in row["warnings"]))

    def test_long_description_warns(self):
        skill(self.home, "wordy", "Use when wordy. " + "x" * 1100)
        row = self.by_dir(self.run_json(), "wordy")
        self.assertTrue(any("caps it at 1024" in w for w in row["warnings"]))

    def test_codex_and_gemini_bypass_flags_are_high_in_audit(self):
        d = skill(self.home, "yolo")
        write(d / "scripts" / "go.sh", "codex --dangerously-bypass-approvals-and-sandbox\ngemini --yolo\n")
        row = self.by_dir(self.run_json("--audit"), "yolo")
        self.assertTrue(any(f["kind"] == "skips-permissions" and f["severity"] == "high"
                            for f in row["audit"]))

    def test_json_has_host_fields(self):
        skill(self.home, "j")
        row = self.by_dir(self.run_json(), "j")
        for key in ("agent", "where", "visible_to", "frontmatter_keys"):
            self.assertIn(key, row)
        self.assertEqual(row["where"], "claude user")


# --------------------------------------------------------------------------- toml

CODEX_TOML = r'''
# a Codex config with the shapes agent files use
model = "gpt-5-codex"
approval_policy = "on-request"
number = 1_000
ratio = 0.5

[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]
env = { API_KEY = "abc", "DOTTED.KEY" = 'lit' }
startup_timeout_sec = 20

[mcp_servers."my.server"]
url = "https://example.com/mcp"
bearer_token_env_var = "TOKEN"
enabled = false
http_headers = { "X-A" = "1" }

[mcp_servers.multi]
command = "python"
args = [
  "-m",
  "server",   # trailing comment
]

[[skills.config]]
path = "C:/Users/me/.agents/skills/one/SKILL.md"
enabled = false

[[skills.config]]
path = "/home/me/.agents/skills/two"
enabled = true

[features]
codex_hooks = true
nested.key = "esc \"quoted\" \\ tab\t"
'''


class Toml(unittest.TestCase):
    def test_fallback_parses_codex_shapes(self):
        d = rollcall._toml_fallback(CODEX_TOML)
        self.assertEqual(d["model"], "gpt-5-codex")
        self.assertEqual(d["number"], 1000)
        self.assertEqual(d["ratio"], 0.5)
        c7 = d["mcp_servers"]["context7"]
        self.assertEqual(c7["args"], ["-y", "@upstash/context7-mcp"])
        self.assertEqual(c7["env"], {"API_KEY": "abc", "DOTTED.KEY": "lit"})
        self.assertEqual(c7["startup_timeout_sec"], 20)
        srv = d["mcp_servers"]["my.server"]
        self.assertEqual(srv["url"], "https://example.com/mcp")
        self.assertIs(srv["enabled"], False)
        self.assertEqual(srv["http_headers"], {"X-A": "1"})
        self.assertEqual(d["mcp_servers"]["multi"]["args"], ["-m", "server"])
        self.assertEqual(len(d["skills"]["config"]), 2)
        self.assertIs(d["skills"]["config"][0]["enabled"], False)
        self.assertEqual(d["features"]["nested"]["key"], 'esc "quoted" \\ tab\t')

    def test_fallback_matches_tomllib(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib needs Python 3.11+")
        self.assertEqual(rollcall._toml_fallback(CODEX_TOML), tomllib.loads(CODEX_TOML))

    def test_read_toml_survives_garbage(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.toml"
            p.write_text("[unclosed\nkey = ", encoding="utf-8")
            self.assertEqual(rollcall.read_toml(p), {})
            self.assertEqual(rollcall.read_toml(Path(tmp) / "missing.toml"), {})


if __name__ == "__main__":
    unittest.main()
