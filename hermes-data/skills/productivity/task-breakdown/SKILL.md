---
name: task-breakdown
description: "Helps Lucas break large or vague tasks into concrete, small first steps — proactive planning, not just unblocking."
version: 1.0.0
metadata:
  hermes:
    tags: [productivity, accountability, planning]
    category: productivity
---

# Task Breakdown

## When to use

When Lucas mentions a task that seems large, vague, or stalled:
- "preencher documento da patente", "atualizar tutorial", "fazer o relatório"
- Tasks marked as "em andamento" for 2+ days in daily_summary
- "é muita coisa", "não sei por onde começar", "isso vai levar tempo"
- "preciso fazer X mas..." (hesitation phrasing)

### Distinction from unblock-helper
- `unblock-helper`: reactive — Lucas says "não tô conseguindo começar" (paralysis)
- `task-breakdown`: proactive — Lucas mentions a big task normally, you help structure it before paralysis hits

## Procedure

### Step 1: Detect the need

A task qualifies if:
- Lucas describes it in vague terms ("fazer X", "resolver Y", "cuidar de Z")
- No concrete deliverable mentioned
- Task has been "em andamento" for 2+ days without sub-steps

### Step 2: Offer breakdown — don't force

- "Quer quebrar essa tarefa em passos menores? Fica mais fácil de acompanhar."
- If Lucas says no → respect it. Don't insist.

### Step 3: Guide the breakdown

One question at a time:
1. "Qual o resultado final? O que significa 'pronto'?" → define done state
2. "Qual o primeiro passo concreto? Só abrir o arquivo? Só listar o que precisa?" → smallest step
3. "Tem dependências? Precisa de alguém ou de alguma informação?" → blockers

### Step 4: Save as sub-tasks

Use `daily_summary_save()` with the parent task broken into sub-tasks:
```
tasks: [
  {"id": "t1", "name": "Documento da patente", "status": "em andamento",
   "sub_tasks": [
     {"name": "Listar seções obrigatórias", "status": "pendente"},
     {"name": "Preencher seção de background", "status": "pendente"},
     {"name": "Preencher seção de claims", "status": "pendente"},
   ]}
]
```

### Step 5: Confirm and encourage

- "Beleza, quebramos em <N> passos. Qual você quer começar agora?"
- If he picks one: "Vai lá. Me avisa quando concluir esse passo e eu atualizo."

## Pitfalls
- Don't over-structure — 2-3 sub-steps is enough. Not a project plan.
- Don't trigger on tasks that are naturally granular ("responder email do João", "commitar o PR")
- If this is the 3rd+ task breakdown in the same conversation, skip — Lucas is just listing stuff
