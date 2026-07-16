---
name: parallel-builder
description: "Execute implementation plans using multiple sub-agents and git worktrees in parallel. Use when the user provides a structured plan with independent file groups."
version: 1.0.0
metadata:
  tags: [build, parallel, subagent, worktree, implementation]
---

# Parallel Builder Skill

Execute implementation plans using multiple sub-agents and git worktrees in parallel. This skill is about execution strategy, not about what code to write — the plan defines the what; this skill defines the how.

## When to use

The user provides a structured plan with multiple independent file groups. Examples:
- "Implement these 3 files in branch X, these 2 in branch Y — they don't overlap"
- "Plan: 6 improvements across 3 parallel branches"
- Any multi-file change where the user says "paralelize o máximo possível"

## Workflow

### Step 1: Analyze the plan for independence

Group files by branch. Files must be truly independent — if two branches modify the same file, they conflict. The user's plan should already identify these groups. If it doesn't, ask before proceeding.

### Step 2: Create git worktrees

```bash
git worktree add -b feat/branch-name ../branch-name main
```

Each worktree is an isolated checkout — no staging conflicts, no accidental overwrites.

### Step 3: Launch subagents in parallel

One subagent per worktree. Each agent prompt MUST include:

1. **Exact file paths** to create/edit (from the plan, not inferred)
2. **Project context**: what this repo is, what technologies it uses
3. **Reference files**: paths to existing files the agent should READ to understand conventions. CRITICAL: if the agent needs to reference container paths or deployment paths, tell it to read `deploy.sh` and `AGENTS.md` — never let it invent directory structures.
4. **"Do not assume" list**: explicit constraints. Example: "Paths in the container use /opt/data/, not /home/hermes/.hermes/. Verify all container paths by reading deploy.sh."
5. **Validation requirements**: what the agent should verify before reporting done (bash -n for scripts, py_compile for Python, create directories with mkdir -p)

Example subagent prompt structure:

```
You are implementing FILE_X for the hermes-config project.
The repo root is /home/lucas/repos/hermes-config.

BEFORE writing anything:
1. Read deploy.sh to understand where files get copied in the container
2. Read AGENTS.md for project conventions
3. Read any existing similar files for style reference

Create FILE_X with [specifications].

Validation: run bash -n on the file, verify no sensitive data,
and confirm the file path exists.
```

### Step 4: Merge branches

After all subagents report success:

```bash
git merge feat/branch-1 feat/branch-2 feat/branch-3
```

If a merge conflict occurs (shouldn't happen with independent files), resolve it manually and report to the user.

### Step 5: Validate merged result

Run the full validation suite:
```bash
cd hermes-data && bash tests/validate.sh
```

Also:
- `bash -n` on all new shell scripts
- Audit for sensitive data: use test_sensitive_data.sh with patterns from .sensitive_patterns
- Verify git diff is clean of secrets

### Step 6: Clean up

```bash
git worktree remove ../branch-name
git branch -D feat/branch-name
```

## Critical rules

1. **Never invent paths.** Always read deploy.sh or AGENTS.md to confirm where files live.
2. **Never assume directory structure.** Create dirs with `mkdir -p` before writing files.
3. **Sensitive data first.** Audit every file before committing. If `.sensitive_patterns` exists, run `SENSITIVE_PATTERNS=$(cat .sensitive_patterns | paste -sd,) bash hermes-data/tests/test_sensitive_data.sh`.
4. **Subagents need full context.** A subagent in a worktree can read files from the repo — tell it which files to read. Don't rely on it knowing project conventions.
5. **One subagent per worktree.** Never share a worktree between subagents — staging area corruption is guaranteed.
6. **Validate before merge.** Fix issues in each branch separately before merging into main.

## Anti-patterns

- Editing files directly without worktrees when 3+ independent changes exist
- Giving subagents incomplete specs and hoping they infer the rest
- Not running validate.sh after merge
- Committing without auditing for sensitive data
- Using `cd` in subagent prompts instead of absolute paths
