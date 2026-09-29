"""Ticket routing: Jev answers typed questions, plain code decides what to do.

Keeping the policy (`decide`) separate from the model call means the business
rules are deterministic, testable, and easy to change without touching prompts.
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_typesafe import Choice, Noul, Score, TypeSafeClassifier

from app.config import (
    ESCALATION_THRESHOLD, JEV_MODEL, JEV_TIMEOUT_SECONDS, SPAM_THRESHOLD,
    TEAM_CONFIDENCE_MIN, TYPESAFE_API_KEY,
)
from app.models import ChoiceSignal, RoutingDecision, ScoreSignal, Signals, TicketIn

# Score levels are written "Label: description" so we can show a short label in the UI.
QUESTIONS = {
    "team": Choice(
        instructions="Which support team should own this ticket?",
        criteria={
            "billing": "Charges, refunds, invoices, payment methods, or subscription plans.",
            "technical": "Bugs, errors, outages, integrations, API, or performance problems.",
            "account": "Login, password, 2FA, permissions, profile, or data/privacy requests.",
            "sales": "Pricing questions, upgrades, demos, or enterprise and new-purchase inquiries.",
            "other": "Anything that does not fit the teams above.",
        },
    ),
    "urgency": Score(
        instructions="How time-sensitive is this ticket for the customer?",
        criteria=[
            "Low: general question, no time pressure.",
            "Medium: inconvenient, but a workaround exists.",
            "High: important work is blocked for this customer.",
            "Critical: outage, data loss, security incident, or many users affected.",
        ],
    ),
    "sentiment": Score(
        instructions="How does the customer feel, based on their tone?",
        criteria=[
            "Positive: happy or appreciative.",
            "Neutral: calmly stating facts.",
            "Frustrated: annoyed but civil.",
            "Angry: hostile or using strong language.",
        ],
    ),
    "churn_risk": Noul(
        instructions="The customer threatens to cancel, leave, or switch to a competitor."
    ),
    "needs_human": Noul(
        instructions=(
            "This needs a senior human: legal threats, a security or privacy concern, "
            "press or public complaints, or repeated failed support attempts."
        )
    ),
    "is_spam": Noul(
        instructions="This message is spam, a sales pitch to us, or not a real support request."
    ),
}

PRIORITIES = ["P1", "P2", "P3", "P4"]  # P1 = most urgent


def _short_label(level: Any) -> str:
    return str(level).split(":", 1)[0].strip()


def _to_score_signal(answer) -> ScoreSignal:
    legend = {int(k): v for k, v in answer.legend.items()}
    nearest = min(legend, key=lambda i: abs(i - answer.score))
    return ScoreSignal(
        level=_short_label(legend[nearest]),
        score=answer.score,
        confidence=answer.confidence,
        probabilities={_short_label(legend[int(i)]): p for i, p in answer.probabilities.items()},
    )


def signals_from_response(response) -> Signals:
    team = response.choices["team"]
    return Signals(
        team=ChoiceSignal(choice=team.choice, confidence=team.confidence, probabilities=team.probabilities),
        urgency=_to_score_signal(response.scores["urgency"]),
        sentiment=_to_score_signal(response.scores["sentiment"]),
        churn_risk=response.nouls["churn_risk"].noul,
        needs_human=response.nouls["needs_human"].noul,
        is_spam=response.nouls["is_spam"].noul,
    )


def decide(signals: Signals) -> Dict[str, Any]:
    """Deterministic routing policy over Jev's probabilities."""
    reasons: List[str] = []

    if signals.is_spam >= SPAM_THRESHOLD:
        return {"queue": "spam", "priority": "P4", "escalate": False,
                "reasons": [f"Spam probability {signals.is_spam:.0%}"]}

    # Queue: trust the team choice only when Jev is confident about it
    if signals.team.confidence >= TEAM_CONFIDENCE_MIN:
        queue = signals.team.choice
        reasons.append(f"Team '{queue}' ({signals.team.confidence:.0%} confidence)")
    else:
        queue = "triage"
        reasons.append(
            f"Team unclear (best guess '{signals.team.choice}' at {signals.team.confidence:.0%}), sent to triage"
        )

    # Priority: urgency score 0 (Low) .. 3 (Critical) maps onto P4 .. P1
    urgency = signals.urgency.score
    idx = 0 if urgency >= 2.5 else 1 if urgency >= 1.5 else 2 if urgency >= 0.5 else 3
    reasons.append(f"Urgency {signals.urgency.level} (score {urgency:.2f})")

    # Bump priority one level for angry customers or churn risk
    if signals.sentiment.score >= 2.5 or signals.churn_risk >= ESCALATION_THRESHOLD:
        if idx > 0:
            idx -= 1
            reasons.append("Priority raised: angry customer or churn risk")

    escalate = signals.needs_human >= ESCALATION_THRESHOLD or signals.churn_risk >= ESCALATION_THRESHOLD
    if signals.needs_human >= ESCALATION_THRESHOLD:
        reasons.append(f"Needs senior human ({signals.needs_human:.0%})")
    if signals.churn_risk >= ESCALATION_THRESHOLD:
        reasons.append(f"Churn risk ({signals.churn_risk:.0%})")

    return {"queue": queue, "priority": PRIORITIES[idx], "escalate": escalate, "reasons": reasons}


class TicketRouter:
    def __init__(self, classifier: Optional[TypeSafeClassifier] = None):
        self._classifier = classifier

    @property
    def configured(self) -> bool:
        return self._classifier is not None or bool(TYPESAFE_API_KEY)

    @property
    def classifier(self) -> TypeSafeClassifier:
        if self._classifier is None:
            if not TYPESAFE_API_KEY:
                raise RuntimeError("TYPESAFE_API_KEY is not set. Add it to .env (get one at console.typesafe.ai/keys).")
            self._classifier = TypeSafeClassifier(
                model=JEV_MODEL, api_key=TYPESAFE_API_KEY, timeout=JEV_TIMEOUT_SECONDS
            )
        return self._classifier

    async def route(self, ticket: TicketIn) -> RoutingDecision:
        state = {"message": ticket.message}
        if ticket.subject:
            state["subject"] = ticket.subject
        if ticket.customer:
            state["customer"] = ticket.customer

        start = time.perf_counter()
        response = await self.classifier.ainvoke({"state": state, "questions": QUESTIONS})
        latency_ms = (time.perf_counter() - start) * 1000

        signals = signals_from_response(response)
        return RoutingDecision(
            id=uuid.uuid4().hex[:8],
            created_at=datetime.now(timezone.utc),
            message=ticket.message,
            subject=ticket.subject,
            customer=ticket.customer,
            signals=signals,
            latency_ms=round(latency_ms, 1),
            model=response.model,
            request_id=response.request_id,
            **decide(signals),
        )
