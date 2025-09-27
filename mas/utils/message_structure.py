from __future__ import annotations
from datetime import datetime
from typing import Dict, Literal, Optional, Any
from pydantic import BaseModel, Field, field_validator

from .enums import MessageType, CommitmentType


class Commitment(BaseModel):
    id: str
    proposer: str
    accepter: str = "OPEN"
    commitment_type: CommitmentType
    adjustment_minutes: int = 0
    reciprocal_obligation: bool = False
    priority: int = 0
    status: Literal["proposed", "accepted", "fulfilled", "violated"] = "proposed"
    timestamp: datetime = datetime.now()

    class Config:
        use_enum_values = True


class TrafficState(BaseModel):
    current_flow: int = 0
    capacity_remaining: int = 0
    estimated_students: Dict[str, int] = Field(
        default_factory=dict
    )  # {agent_id: count}
    congestion_risk: float = 0.0  # normalized 0.0 - 1.0
    timestamp: datetime = datetime.now()

    @field_validator("congestion_risk")
    def clamp_risk(cls, v):
        if v is None:
            return 0.0
        return max(0.0, min(1.0, float(v)))


class CommitmentProposalContent(BaseModel):
    commitment: Commitment
    negotiation_id: str
    conditions: Optional[str] = None
    student_count: Optional[int] = None
    reason: Optional[str] = None


class CommitmentResponseContent(BaseModel):
    commitment: Commitment
    decision: str  # "accept" | "reject"
    decision_score: Optional[float] = None
    negotiation_id: Optional[str] = None
    accepter_students: Optional[int] = None
    acceptance_reason: Optional[str] = None


class CommitmentBroadcastContent(BaseModel):
    proposer: str
    accepter: str
    commitment: Commitment
    negotiation_id: Optional[str] = None
    proposer_students: Optional[int] = None
    accepter_students: Optional[int] = None


class ViolationReportContent(BaseModel):
    agent_id: str
    violation_count: int
    details: Optional[str] = None
    timestamp: datetime = datetime.now()


class Structure(BaseModel):
    """
    Generic structured message payload for MAS communication.

    Use `message_type` to indicate which of the optional fields is populated.
    Unused optional fields should be left None.
    """

    message_type: MessageType
    extra: Dict[str, Any] = Field(default_factory=dict)

    # typed payloads (only a subset will be populated depending on message_type)
    traffic_state: Optional[TrafficState] = None
    negotiation_id: Optional[str] = None

    # commitment-related payloads
    commitment_proposal: Optional[CommitmentProposalContent] = None
    commitment_response: Optional[CommitmentResponseContent] = None
    commitment_broadcast: Optional[CommitmentBroadcastContent] = None

    # violation reporting
    violation_report: Optional[ViolationReportContent] = None

    created_at: datetime = datetime.now()

    class Config:
        use_enum_values = True
        validate_by_name = True
        json_schema_extra = {
            "example": {
                "message_type": "COMMITMENT_PROPOSAL",
                "sender": "C1",
                "recipient": "BROADCAST",
                "negotiation_id": "abc-123",
                "commitment_proposal": {
                    "commitment": {
                        "id": "cmt-1",
                        "proposer": "C1",
                        "accepter": "OPEN",
                        "commitment_type": "EARLY_EXIT",
                        "adjustment_minutes": 2,
                        "reciprocal_obligation": True,
                        "priority": 1,
                        "status": "proposed",
                    },
                    "negotiation_id": "abc-123",
                    "conditions": "Will finish 2 minutes early; seeking reciprocal favor",
                    "student_count": 12,
                    "reason": "Small class can help reduce congestion",
                },
            }
        }

    def is_traffic_update(self) -> bool:
        return self.message_type == MessageType.TRAFFIC_UPDATE

    def is_commitment_proposal(self) -> bool:
        return self.message_type == MessageType.COMMITMENT_PROPOSAL

    def is_commitment_response(self) -> bool:
        return self.message_type == MessageType.COMMITMENT_RESPONSE

    def is_commitment_broadcast(self) -> bool:
        return self.message_type == MessageType.COMMITMENT_BROADCAST

    def is_violation_report(self) -> bool:
        return self.message_type == MessageType.VIOLATION_REPORT
