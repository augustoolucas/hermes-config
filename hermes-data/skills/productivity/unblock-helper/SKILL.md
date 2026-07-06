---
name: unblock-helper
description: "Helps Lucas overcome task initiation paralysis with a single micro-step question. Does NOT decompose tasks — reduces barrier to entry."
version: 1.0.0
metadata:
  hermes:
    tags: [productivity, focus, accountability, adhd]
    category: productivity
---

# Unblock Helper

## When to use

When Lucas demonstrates initiation paralysis:
- "não tô conseguindo começar X"
- "tô travado em Y"
- "procrastinando Z"
- "não saiu nada"
- "empacado em W"

Do NOT use when:
- Lucas is already in a focus session (let the focus session run)
- Lucas is reporting regular progress (use daily-status-session instead)
- Lucas is asking for task decomposition (different thing — he's just stuck starting)

## Core principle

This is NOT task decomposition. Lucas already knows what to do. The problem is the **barrier to entry** — the first step feels too big. The goal is to shrink the first step to something so small it feels trivial.

## Procedure

### Step 1: One question

Ask exactly ONE question. No analysis, no suggestions, no "have you tried..."

```
"Qual o menor passo possível? Só abrir o arquivo? Só ler o ticket?"
```

Wait for the answer. Do not offer options unless he specifically asks for them.

### Step 2: Confirm the micro-step

When Lucas names a micro-step, confirm it back:

```
"Beleza, então o plano é [micro-passo]. Vou te perguntar em 10min como foi. Quer?"
```

### Step 3: Optional 10min check-in

If Lucas accepts, create a cron one-shot:

```
cronjob(
  action="create",
  schedule="10m",
  name="unblock-checkin-<timestamp>",
  prompt="[UNBLOCK CHECKIN] Lucas said he'd try: <micro-step>. Ask casually: 'E aí, <micro-step>? Conseguiu?' One question, no pressure. If he says no, just acknowledge and don't push. Respond [SILENT] if no answer.",
  deliver="telegram:TELEGRAM_CHAT_ID",
  enabled_toolsets=["send_message"]
)
```

If Lucas declines the check-in, just say "Sem pressa. Qualquer coisa tamo aí." and move on.

### Step 4: Follow-up on success

If Lucas comes back and says he did it:
- "Boa. [micro-passo] feito. Quer continuar ou era só isso?"
- Don't over-celebrate. It's a micro-step. Genuine, not patronizing.

## Rules

- **One question only.** Don't try to decompose the whole task.
- **Don't prescribe.** Don't suggest what the micro-step should be. Lucas decides.
- **Don't analyze.** Don't ask why he's stuck. Don't give advice. Just the micro-step.
- **Respect the focus session.** If Lucas is in a focus session, don't interrupt with this.
- **Accept "no".** If Lucas says he doesn't want the check-in, don't insist.
- **No shame.** Never imply he should have started already. The system is here to help, not judge.

## Pitfalls

- Do NOT turn this into a therapy session. One question, one optional check-in, done.
- Do NOT suggest breaking the task down into subtasks. That's a different feature. This is just the first microscopic step.
- Do NOT use when Lucas is reporting regular progress. Only when he explicitly signals he's stuck starting.
