"""Tests for the routing policy and response mapping. No network: Jev is faked."""
import asyncio
from types import SimpleNamespace

from app.models import ChoiceSignal, ScoreSignal, Signals, TicketIn
from app.router import TicketRouter, decide, signals_from_response


def make_signals(team="technical", team_conf=0.9, urgency=1.0, sentiment=1.0,
                 churn=0.1, human=0.1, spam=0.01) -> Signals:
    score = lambda s: ScoreSignal(level="x", score=s, confidence=0.9, probabilities={})
    return Signals(
        team=ChoiceSignal(choice=team, confidence=team_conf, probabilities={team: team_conf}),
        urgency=score(urgency), sentiment=score(sentiment),
        churn_risk=churn, needs_human=human, is_spam=spam,
    )


def test_spam_short_circuits():
    d = decide(make_signals(spam=0.95, urgency=3.0))
    assert d["queue"] == "spam" and d["priority"] == "P4" and not d["escalate"]


def test_low_team_confidence_goes_to_triage():
    assert decide(make_signals(team_conf=0.4))["queue"] == "triage"
    assert decide(make_signals(team_conf=0.8))["queue"] == "technical"


def test_urgency_maps_to_priority():
    assert decide(make_signals(urgency=2.9))["priority"] == "P1"
    assert decide(make_signals(urgency=2.0))["priority"] == "P2"
    assert decide(make_signals(urgency=1.0))["priority"] == "P3"
    assert decide(make_signals(urgency=0.1))["priority"] == "P4"


def test_angry_or_churning_bumps_priority_and_churn_escalates():
    assert decide(make_signals(urgency=1.0, sentiment=2.8))["priority"] == "P2"
    d = decide(make_signals(urgency=1.0, churn=0.9))
    assert d["priority"] == "P2" and d["escalate"]
    assert decide(make_signals(urgency=2.9, sentiment=3.0))["priority"] == "P1"  # already top


def test_needs_human_escalates():
    assert decide(make_signals(human=0.85))["escalate"]
    assert not decide(make_signals(human=0.3))["escalate"]


def fake_response():
    """Shaped like langchain_typesafe.ClassifierResponse."""
    score = lambda s, labels: SimpleNamespace(
        score=s, confidence=0.8, legend={i: l for i, l in enumerate(labels)},
        probabilities={i: (0.7 if i == round(s) else 0.1) for i in range(len(labels))})
    return SimpleNamespace(
        model="jev-test", request_id="req_1",
        choices={"team": SimpleNamespace(choice="billing", confidence=0.93, probabilities={"billing": 0.93, "other": 0.07})},
        scores={
            "urgency": score(0.9, ["Low: a", "Medium: b", "High: c", "Critical: d"]),
            "sentiment": score(0.2, ["Positive: a", "Neutral: b", "Frustrated: c", "Angry: d"]),
        },
        nouls={"churn_risk": SimpleNamespace(noul=0.05), "needs_human": SimpleNamespace(noul=0.02),
               "is_spam": SimpleNamespace(noul=0.01)},
    )


def test_signals_from_response_uses_short_labels():
    s = signals_from_response(fake_response())
    assert s.team.choice == "billing"
    assert s.urgency.level == "Medium"
    assert s.sentiment.level == "Positive"
    assert set(s.urgency.probabilities) == {"Low", "Medium", "High", "Critical"}


def test_route_end_to_end_with_fake_classifier():
    class FakeClassifier:
        async def ainvoke(self, request):
            assert request["state"]["message"] == "refund please"
            assert set(request["questions"]) == {"team", "urgency", "sentiment", "churn_risk", "needs_human", "is_spam"}
            return fake_response()

    decision = asyncio.run(TicketRouter(FakeClassifier()).route(TicketIn(message="refund please")))
    assert decision.queue == "billing"
    assert decision.priority == "P3"
    assert not decision.escalate
    assert decision.model == "jev-test"
