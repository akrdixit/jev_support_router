# ⚡ Jev Support Ticket Router

Routes customer support tickets using **[Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)**, TypeSafe AI's *System One* model. Instead of generating text, Jev evaluates a ticket and returns **typed answers with calibrated probabilities**. Plain Python rules then turn those answers into a queue, a priority and an escalation decision.

```
ticket ──► Jev (1 call, 6 typed questions in parallel) ──► signals + probabilities ──► routing policy (code) ──► queue / priority / escalate
```

## Why Jev for this?

Routing is a classification problem, not a writing problem. With a text LLM you would have to prompt for JSON, parse it, validate it and hope the confidence numbers mean something. Jev returns the typed fields directly (no parsing), each with a probability. That makes rules like *"send to triage if team confidence < 60%"* possible.

This follows the **harness** pattern from [LangChain's Jev guide](https://www.langchain.com/blog/building-a-harness-with-jev): the model makes the judgement calls and the surrounding code controls what happens.

## What Jev is asked

All six questions go in **one request** and are evaluated in parallel ([`app/router.py`](app/router.py)):

| Question | Type | Answer |
|---|---|---|
| `team` | **Choice** | `billing` / `technical` / `account` / `sales` / `other`, with a probability per team and a confidence score |
| `urgency` | **Score** | Low → Medium → High → Critical (continuous 0–3 score plus a probability per level) |
| `sentiment` | **Score** | Positive → Neutral → Frustrated → Angry |
| `churn_risk` | **Noul** (yes/no) | P(customer threatens to cancel or switch) |
| `needs_human` | **Noul** | P(legal, security/privacy, press, or repeated failures) |
| `is_spam` | **Noul** | P(spam or not a real support request) |

## Routing policy

`decide()` in [`app/router.py`](app/router.py) is deterministic and unit-tested:

1. **Spam** ≥ 80% → `spam` queue, P4, stop.
2. **Queue** = Jev's team choice if its confidence ≥ 60%, otherwise `triage` for a human to sort.
3. **Priority** from the urgency score: ≥ 2.5 → P1, ≥ 1.5 → P2, ≥ 0.5 → P3, else P4.
4. **Bump priority one level** if the customer is angry (sentiment ≥ 2.5) or churn risk ≥ 70%.
5. **Escalate** if needs-human ≥ 70% or churn risk ≥ 70%.

Every decision includes a `reasons` list, so you can see exactly why it was routed that way. All thresholds can be set in `.env`.

## Quick start

Requires **Python 3.10+** and a TypeSafe API key from [console.typesafe.ai/keys](https://console.typesafe.ai/keys).

```bash
cp .env.example .env        # then set TYPESAFE_API_KEY
./run.sh                    # creates .venv on first run, starts http://localhost:8010
```

Open **http://localhost:8010** and click **"Route 10 sample tickets"**, or paste your own. Click any row to see the probability breakdown and the reasons behind the routing.

- Swagger API docs: http://localhost:8010/docs
- Run tests (no API key needed, since Jev is faked): `./run.sh test`

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tickets` | Route one ticket: `{ "message", "subject?", "customer?" }` |
| `POST` | `/api/tickets/batch` | Route up to 100 tickets concurrently: `{ "tickets": [...] }` |
| `GET` | `/api/tickets` | All routed tickets, newest first |
| `DELETE` | `/api/tickets` | Clear the ticket list |
| `GET` | `/api/samples` | The 10 sample tickets in `sample_data/tickets.json` |
| `GET` | `/api/status` | Whether Jev is configured, the model name, and the ticket count |

```bash
curl -X POST http://localhost:8010/api/tickets -H "Content-Type: application/json" \
  -d '{"subject": "Checkout down", "message": "Every API call returns 500 and our checkout is down!"}'
```

Example response (illustrative values, trimmed):

```json
{
  "queue": "technical",
  "priority": "P1",
  "escalate": false,
  "reasons": ["Team 'technical' (91% confidence)", "Urgency Critical (score 2.80)"],
  "signals": {
    "team": { "choice": "technical", "confidence": 0.91, "probabilities": { "technical": 0.91, "billing": 0.04 } },
    "urgency": { "level": "Critical", "score": 2.8, "probabilities": { "Low": 0.01, "Medium": 0.04, "High": 0.15, "Critical": 0.8 } },
    "churn_risk": 0.2, "needs_human": 0.3, "is_spam": 0.0
  },
  "latency_ms": 85.2
}
```

## Project structure

```
jev_support_router/
├── app/
│   ├── main.py        # FastAPI app + endpoints, serves the dashboard
│   ├── router.py      # Jev questions, response mapping, routing policy
│   ├── models.py      # Pydantic schemas
│   └── config.py      # Env settings and thresholds
├── static/index.html  # Dashboard (vanilla JS, no build step)
├── sample_data/tickets.json
├── tests/test_router.py
├── requirements.txt
├── .env.example
└── run.sh
```

## Notes

- `langchain-typesafe` is an **alpha** release (`0.0.1a3`) and is pinned in `requirements.txt`. Its API may change.
- Tickets are stored in memory and cleared when the server restarts.
- The speed and cost figures for Jev (up to ~200x faster and ~400x cheaper than LLMs on classification) come from TypeSafe. The dashboard shows the latency you actually get.
