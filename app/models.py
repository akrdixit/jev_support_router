from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TicketIn(BaseModel):
    message: str = Field(..., min_length=1, description="The customer's support message")
    subject: Optional[str] = None
    customer: Optional[str] = Field(None, description="Customer name, email, or plan")


class BatchIn(BaseModel):
    tickets: List[TicketIn] = Field(..., min_length=1, max_length=100)


class ChoiceSignal(BaseModel):
    choice: str
    confidence: float
    probabilities: Dict[str, float]


class ScoreSignal(BaseModel):
    level: str = Field(..., description="Short label of the nearest level, e.g. 'High'")
    score: float = Field(..., description="Continuous score from 0 to (number of levels - 1)")
    confidence: float
    probabilities: Dict[str, float]


class Signals(BaseModel):
    """Raw typed answers from Jev."""
    team: ChoiceSignal
    urgency: ScoreSignal
    sentiment: ScoreSignal
    churn_risk: float
    needs_human: float
    is_spam: float


class RoutingDecision(BaseModel):
    """Jev's signals plus the decision our routing policy made from them."""
    id: str
    created_at: datetime
    message: str
    subject: Optional[str] = None
    customer: Optional[str] = None
    queue: str
    priority: str
    escalate: bool
    reasons: List[str]
    signals: Signals
    latency_ms: float
    model: str
    request_id: Optional[str] = None


class StatusOut(BaseModel):
    jev_configured: bool
    model: str
    tickets_routed: int
