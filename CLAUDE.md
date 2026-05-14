# CLAUDE.md

## Skills: check first, use when they help

This repo has a local library of Claude "superpowers" skills installed at
`.claude/skills/` (sourced from
[obra/superpowers-skills](https://github.com/obra/superpowers-skills)).

**Before starting any non-trivial task, check whether an existing skill applies,
and use it if doing so would increase the quality of the result.**

### Workflow

1. **Survey the available skills** at the start of a task. Run:
   ```
   .claude/skills/using-skills/find-skills [PATTERN]
   ```
   or browse `.claude/skills/<category>/<skill-name>/SKILL.md`. Categories
   currently installed:
   - `architecture/`
   - `collaboration/` (brainstorming, writing-plans, executing-plans,
     subagent-driven-development, code review, git worktrees, …)
   - `debugging/` (systematic-debugging, root-cause-tracing,
     verification-before-completion, defense-in-depth)
   - `meta/` (writing-skills, sharing-skills, testing-skills-with-subagents, …)
   - `problem-solving/` (when-stuck, inversion-exercise, simplification-cascades, …)
   - `research/`
   - `testing/` (test-driven-development, condition-based-waiting,
     testing-anti-patterns)
   - `using-skills/` (entry point and tooling)

2. **If a relevant skill exists, read it in full with the Read tool** before
   acting — skills evolve, and remembered versions go stale. Use the full path,
   e.g. `.claude/skills/testing/test-driven-development/SKILL.md`.

3. **Announce usage** so the human partner can follow along:
   > "I've read the *Systematic Debugging* skill and I'm using it to find the
   > root cause of …"

4. **Follow the skill's instructions.** Many skills include checklists — when
   they do, create TodoWrite todos for each checklist item rather than tracking
   them mentally.

### When to skip skills

Skills are a quality multiplier, not bureaucracy. Skip the lookup only when the
task is genuinely trivial (single-line edit, a direct question, a one-shot
shell command) and no skill obviously applies. If you're unsure whether a skill
applies, default to checking — the lookup is cheap.

### Updating the skills

The skills under `.claude/skills/` are a vendored copy. To pull upstream
changes, see `.claude/skills/meta/pulling-updates-from-skills-repository/`.
