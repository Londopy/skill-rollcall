---
name: skill-rollcall
description: Take a roll call of installed skills - refresh Claude's view of them without restarting the session and diagnose any that fail to register. Use this whenever the user says reload skills, refresh skills, rescan skills, re-index skills, roll call, "I just installed a skill", "I just added/edited a SKILL.md", asks whether you can see a particular /skill, or complains that a skill is not showing up or not triggering. Also use it after you yourself install or write a skill mid-session, so you can confirm it registered and diagnose why if it did not.
---

# Skill roll call

Claude Code reads every `SKILL.md`'s frontmatter at session start and watches the
skills folders for additions and removals. A skill can still fail to appear because
its frontmatter is malformed, its folder is nested one level too deep (plugin layout),
its `name` does not match, or the watcher simply has not fired yet. This skill rebuilds
the same index from disk so you can see exactly what is there, tell the user whether
each skill is registered, and use an unregistered one right away.

## Steps

1. Run the indexer, passing the names the harness has already given you. Those are the
   skills listed in your system context for the `Skill` tool. This lets the script mark
   each row registered or NEW rather than making you compare by eye:

   ```bash
   python ~/.claude/skills/skill-rollcall/scripts/rollcall.py --known name1,name2,...
   ```

   If installed as a plugin the script lives under the plugin root instead; use the
   path relative to this SKILL.md (`scripts/rollcall.py`).

   Pass `--full` if the user wants complete descriptions, `--json` if you need to
   process the output, and `--project <dir>` if the project's `.claude/skills` is
   somewhere other than the current directory. If assembling the `--known` list is
   impractical, run it without and compare the output against your listing yourself.

2. Report to the user in three groups, briefly:
   - **Registered** - on disk and in your listing. Nothing to do.
   - **NEW** - on disk but not in your listing. Say that these will usually register on
     the next turn without any action, and offer to use one now (step 3).
   - **Problems** - folders that will never register, with the script's reason. These
     are the ones the user actually needs to fix; give the one-line fix for each
     (add frontmatter, move the nested folder up, rename the folder to match `name`,
     add a description).

   Do not paste the whole table back when only a few rows matter. The user asked a
   question - "do you see X?", "why isn't Y triggering?" - so answer that first, then
   summarize the rest in a sentence.

3. To use a NEW skill before the harness registers it, read its `SKILL.md` and follow
   it as if the `Skill` tool had loaded it. That is all the `Skill` tool does: it puts
   the file body into context. Read any `scripts/` or `references/` it points to when
   the instructions call for them. Tell the user you loaded it manually so they know
   the slash form may not work yet.

4. If a skill is on disk with no problems but still is not registered after another
   turn, the fallback is `/clear`, which reruns discovery. Mention that it wipes the
   conversation, so the user can finish anything in flight first.

## What this cannot do

It cannot force the harness to rescan; only the harness does that. Edits to an
existing skill's `description` may not be picked up until the next session, though
edits to the body are read fresh every time the skill is invoked. Be honest about this
distinction when the user is trying to fix triggering: a body edit is live, a
description edit needs `/clear` or a new session to be certain.
