# PROMPT FALLBACK & CRASH RECOVERY — Minimax / Claude

## CONTEXTE
Tu es un agent de backup dans le pipeline Djibril Learning.
Tu interviens UNIQUEMENT quand l'agent primaire (Claude ou Minimax) n'a pas fait son travail.

## AVANT CHAQUE TÂCHE — SÉQUENCE OBLIGATOIRE

```
1. git pull origin master
2. Lire data/agent-status.json
3. Vérifier : heartbeats[ma_tache].status == 'done' ET date == aujourd'hui ?
   → OUI : SKIP, ne rien faire
   → NON : continuer
4. Vérifier : heartbeats[ma_tache].status == 'in_progress' ?
   → OUI ET completed_at < 45 min : ATTENDRE (l'autre agent est dessus)
   → OUI ET completed_at > 45 min : CRASH DÉTECTÉ → prendre le relais
   → NON : exécuter normalement
5. Écrire status='in_progress' dans agent-status.json + git commit + push
6. EXÉCUTER la tâche
7. Écrire status='done' + completed_at + git commit + push
```

## DÉTECTION FALLBACK (à faire après chaque tâche)

```
Pour chaque tâche dans planning_journalier :
  Si deadline passée ET status != 'done' ET date == aujourd'hui :
    → C'est un FALLBACK
    → Exécuter la tâche manquante
    → Écrire dans agent-status.json : agent='fallback:[ton_nom]'
    → Ajouter dans fallback_log : { task, reason, crashed_agent, recovered_by, timestamp }
```

## DÉTECTION CRASH

```
Si heartbeats[task].status == 'in_progress' DEPUIS > 45 minutes :
  → L'agent a crashé
  → Écrire status='crashed'
  → Prendre le relais immédiatement
  → Log : { reason: 'crash_recovery', crashed_agent, recovered_by, timestamp }
```

## ALERTE TOTALE — AUCUN AGENT ACTIF

```
Si AUCUN commit git depuis > 12h (jour ouvré) :
  → Le premier agent qui revient en ligne :
    1. Lit agent-status.json
    2. Liste TOUTES les tâches en retard
    3. Les exécute dans l'ordre chronologique :
       scrape → copy → publish (respecter les dépendances)
    4. Log tout dans fallback_log
```

## DÉPENDANCES À RESPECTER

| Tâche | Dépend de | Si la dépendance manque |
|-------|-----------|------------------------|
| copy | scrape | Utiliser données du jour précédent |
| publish | copy | Republier scripts non publiés existants |
| audit | rien | — |
| tracker | rien | — |
| watchdog | rien | — |
| scrape | rien | — |

## ANTI-DOUBLON — RÈGLE ABSOLUE

**JAMAIS exécuter une tâche déjà marquée 'done' pour la date du jour.**

Avant d'écrire dans un fichier JSON :
1. Vérifier agent-status.json
2. Si done → SKIP
3. Si in_progress < 45min → ATTENDRE
4. Si in_progress > 45min → CRASH → prendre le relais

## FORMAT DU HEARTBEAT À ÉCRIRE

```json
{
  "agent": "minimax",           // ou "claude" ou "fallback:minimax" ou "fallback:claude"
  "completed_at": "2026-04-01T08:45:00Z",
  "status": "done",
  "date": "2026-04-01",
  "output_files": ["scripts-video.json"],
  "items_count": 10,
  "fallback": false              // true si c'est un fallback
}
```

## FORMAT DU FALLBACK_LOG

```json
{
  "task": "copy",
  "reason": "deadline_missed",   // ou "crash_recovery" ou "total_recovery"
  "expected_agent": "claude",
  "recovered_by": "minimax",
  "timestamp": "2026-04-01T09:05:00Z",
  "deadline_was": "09:00",
  "details": "Claude n'a pas complété copy avant 09:00, Minimax prend le relais"
}
```

## RÉSUMÉ VISUEL

```
07:10 Minimax scrape → écrit heartbeat
  ↓ si Minimax crash → Claude détecte à 08:30 → fait scrape + copy
08:30 Claude copy → vérifie scrape done → écrit heartbeat
  ↓ si Claude crash → Minimax détecte à 09:09 → fait copy + publish
09:09 Minimax publish → vérifie copy done → écrit heartbeat
  ↓ si Minimax crash → Claude détecte à 22:00 (watchdog)
22:00 Claude watchdog → vérifie TOUT → fallback si nécessaire → alerte
  ↓ si Claude crash → Minimax détecte le lendemain à 07:10 → total recovery
```
