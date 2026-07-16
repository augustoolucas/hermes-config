---
name: context-recall
description: "Recovers context after breaks — weekends, holidays, or distractions — and quickly summarizes where Lucas left off."
version: 1.0.0
metadata:
  hermes:
    tags: [productivity, accountability, context]
    category: productivity
---

# Context Recall

## When to use

When Lucas returns after a pause:
- "bom dia", "boa tarde", "oi hermes", "voltei" (first message of the day before W1)
- "onde eu estava", "o que eu tava fazendo", "o que ficou pendente"
- "me atualiza", "resumo de ontem", "o que eu fiz essa semana"
- After weekend/holiday — if checkin.py ran and user_responded_at is still null

## Procedure

### Step 1: Find the last active daily summary

```
daily_summary_load(date=<today>)
daily_summary_load(date=<yesterday>)
```

If today's daily_summary already exists with content → Lucas already interacted today, skip.
If both today and yesterday are empty, search back up to 7 days.

### Step 2: Summarize what you found

Format:
```
📋 Último registro: <day of week>, <date>.

O que estava rolando:
• <task> — <status>
• <task> — <status>

🔄 Ainda em andamento: <N>
✅ Concluído no último dia: <M>
```

### Step 3: Offer to pick up

- "Quer retomar de onde parou? Alguma novidade?"
- If Lucas mentions new tasks, save them via `daily_summary_save()`
- If he just wants to resume, confirm and stay available

### Step 4: Cross-reference with checkin.py state

After summarizing, check if any check-in windows need marking:
- If today's W1/W2/W3 windows exist and `checkin_sent_at` is set but `user_responded_at` is null → use `checkin_state_update` to mark responded
- This suppresses unnecessary follow-ups from the cron system

## Pitfalls

- NEVER read daily_summary files by path — use `daily_summary_load()` exclusively
- NEVER write to a past date — `daily_summary_save` without a date parameter always writes to today
- If the last daily_summary was >7 days ago, just say "Faz um tempo desde o último registro. Em que está trabalhando agora?"
- Don't over-explain — the summary should be 2-3 bullet points, not a full report
