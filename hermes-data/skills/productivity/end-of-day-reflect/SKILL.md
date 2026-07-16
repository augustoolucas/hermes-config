---
name: end-of-day-reflect
description: "Guides Lucas through structured end-of-day reflection — what was done, what was blocked, what's next."
version: 1.0.0
metadata:
  hermes:
    tags: [productivity, accountability, end-of-day]
    category: productivity
---

# End-of-Day Reflect

## When to use

When Lucas is wrapping up for the day:
- W3 check-in arrives ("Fim do dia! Como foi?")
- "terminei por hoje", "chega", "vou parar", "já deu por hoje"
- "encerrando", "fechando o dia", "finalizando"

## Procedure

### Step 1: Load current state
```
daily_summary_load()  → today's tasks and status
focus_session_status() → any active sessions?
```

### Step 2: Structured questions (one at a time, keep it light)

Start with the most relevant question based on what you know:

**A. What got done today?** → update task statuses via `daily_summary_save()`
- "O que conseguiu concluir hoje?"
- Mark concluded tasks as "concluído"

**B. What's still in progress?** → carry forward
- "O que ficou em andamento?"
- Tasks stay as "em andamento" for tomorrow's daily_summary

**C. What blocked you?**
- "Algo travou ou ficou pendente de outra pessoa?"
- Useful context for next day's W1

**D. First task tomorrow**
- "Qual vai ser sua primeira tarefa amanhã?"
- Save as `plans_for_next_day` in daily_summary

### Step 3: Save everything
```
daily_summary_save(date=<today>, tasks=<updated>, plans_for_next_day=<answer>)
checkin_state_update(window="3", field="user_responded_at", value=<epoch>)
```

### Step 4: Close out
- Brief summary: "Registrado. <N> concluídas, <M> em andamento. Amanhã começa com <task>. Bom descanso!"
- If no tasks changed: "OK, amanhã retomamos. Descansa!"

## Pitfalls
- Don't interrogate — if Lucas gives short answers, accept them
- Don't repeat questions he already answered
- The W3 cron message already asks these questions — if Lucas already answered them before this skill triggered, just confirm and save
