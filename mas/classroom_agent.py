from dataclasses import dataclass
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from autogen_agentchat.messages import StructuredMessage

from .base_agent import BaseAgent
from .utils.enums import CommitmentType, MessageType
from .utils.message_broker import Message, MessageBroker
from .utils.message_structure import (
    Commitment,
    CommitmentProposalContent,
    CommitmentResponseContent,
    Structure,
    TrafficState,
)
from .utils.config import SystemConfig

from typing import List, Optional


@dataclass
class ClassroomState:
    agent_name: str
    current_attendance: int
    prof_flexibility: float
    end_time: datetime
    exit_slots: List[datetime]


class ClassroomAgent(BaseAgent):
    """
    Classroom agents C_{i} that manage individual classrooms
    """

    def __init__(
        self,
        name: str,
        description: str,
        message_broker: MessageBroker,
        logger: logging.Logger,
        attendance: int,
        prof_flexibility: float,
        config: SystemConfig,
    ) -> None:
        super(ClassroomAgent, self).__init__(
            name, description, message_broker, logger, config
        )

        self.state = ClassroomState(
            agent_name=self.name,
            current_attendance=attendance,
            prof_flexibility=prof_flexibility,
            end_time=datetime.now() + timedelta(hours=1),
            exit_slots=[],
        )

        self.commitment_history = []
        self.pending_commitments = []
        self.obligation_credits = 0
        self.violation_count = 0
        self.trust_scores = defaultdict(lambda: 0.5)

        self.current_negotiation = None
        self.received_proposals = []

    # how willing is an agent to adjust its schedule
    def get_adjustment_score(self, minutes: int) -> float:
        flexibility = self.state.prof_flexibility

        adjustment_factor = 1 - (abs(minutes) / self.config.max_adjustment)
        obligation_factor = 1 - 0.1 * self.obligation_credits
        obligation_factor = max(0.5, min(1.5, obligation_factor))

        score = flexibility * adjustment_factor * obligation_factor
        return max(0, min(1.0, score))

    def generate_commitment_proposals(
        self, traffic_state: TrafficState, negotiation_id: str
    ) -> List[Message]:
        proposals = []

        def create_proposal(commitment: Commitment) -> None:
            nonlocal proposals

            commitment_structure = Structure(
                message_type=MessageType.COMMITMENT_PROPOSAL,
                commitment_proposal=CommitmentProposalContent(
                    commitment=commitment, negotiation_id=negotiation_id
                ),
            )
            content = StructuredMessage(content=commitment_structure, source=self.name)

            proposal = Message(sender=self.name, receiver="BROADCAST", content=content)
            proposals.append(proposal)

        if traffic_state.congestion_risk < 0.5:
            return proposals

        total_students = sum(traffic_state.estimated_students.values())
        if total_students == 0:
            return proposals

        our_proportion = self.state.current_attendance / total_students

        if our_proportion < 0.25 and traffic_state.congestion_risk > 0.6:
            for adjustment in [-2, -4, -6]:
                if self.get_adjustment_score(adjustment) > 0.6:
                    commitment = Commitment(
                        id=str(uuid.uuid4()),
                        proposer=self.name,
                        commitment_type=CommitmentType.EARLY_EXIT,
                        adjustment_minutes=abs(adjustment),
                        reciprocal_obligation=True,
                        priority=1,
                    )
                    create_proposal(commitment)
                    break

        if self.obligation_credits < 0 and traffic_state.congestion_risk > 0.5:
            adjustment = min(4, abs(self.obligation_credits) * 2)
            if self.get_adjustment_score(-adjustment) > 0.5:
                commitment = Commitment(
                    id=str(uuid.uuid4()),
                    proposer=self.name,
                    commitment_type=CommitmentType.EARLY_EXIT,
                    adjustment_minutes=adjustment,
                    reciprocal_obligation=False,
                    priority=2,
                )
                create_proposal(commitment)

        if our_proportion > 0.3 and self.state.current_attendance > 40:
            if self.get_adjustment_score(0) > 0.7:
                commitment = Commitment(
                    id=str(uuid.uuid4()),
                    proposer=self.name,
                    commitment_type=CommitmentType.STAGGERED_EXIT,
                    adjustment_minutes=0,
                    reciprocal_obligation=False,
                    priority=3,
                )
                create_proposal(commitment)

        return proposals

    def exec_commitment(self, commitment: Commitment) -> bool:
        if commitment.commitment_type == CommitmentType.EARLY_EXIT:
            self.state.end_time -= timedelta(minutes=commitment.adjustment_minutes)

        elif commitment.commitment_type == CommitmentType.LATE_EXIT:
            self.state.end_time += timedelta(minutes=commitment.adjustment_minutes)

        elif commitment.commitment_type == CommitmentType.STAGGERED_EXIT:
            base_time = self.state.end_time
            students_per_batch = min(30, self.state.current_attendance // 3)

            self.state.exit_slots = []
            for i in range(0, self.state.current_attendance, students_per_batch):
                exit_time = base_time + timedelta(minutes=i // students_per_batch * 2)
                self.state.exit_slots.append(exit_time)

        commitment.status = "fulfilled"
        self.commitment_history.append(commitment)

        return True

    def handle_broker_message(self, message: Message) -> None:
        message_type = message.content.content.message_type

        if message_type == MessageType.NEGOTIATION_START:
            self._handle_negotiation_start(message)
        elif message_type == MessageType.COMMITMENT_PROPOSAL:
            self._handle_commitment_proposal(message)
        elif message_type == MessageType.COMMITMENT_RESPONSE:
            self._handle_commitment_response(message)

    def _evaluate_commitment_proposal(
        self, message: StructuredMessage[Structure]
    ) -> Optional[Message]:
        proposal = message.content.commitment_proposal
        if proposal is None:
            raise RuntimeError("Cannot Evaluate NoneType Proposal")

        commitment = proposal.commitment
        proposer = commitment.proposer
        if proposer == self.name:
            return None

        trust_score = self.trust_scores[proposer]
        benefit = self._compute_proposal_benefit(commitment)
        obligation_cost = -0.2 if commitment.reciprocal_obligation else 0.0
        priority_bonus = 0.1 * commitment.priority

        score = trust_score + benefit + obligation_cost + priority_bonus

        if score > 0.5:
            commitment.accepter = self.name
            commitment.status = "accepted"

            commitment_response = CommitmentResponseContent(
                commitment=commitment,
                decision="accept",
                decision_score=score,
                negotiation_id=message.content.negotiation_id,
                accepter_students=self.state.current_attendance,
            )
            content = Structure(
                message_type=MessageType.COMMITMENT_RESPONSE,
                commitment_response=commitment_response,
            )
            response_content = StructuredMessage(content=content, source=self.name)
            response = Message(
                sender=self.name, receiver=proposer, content=response_content
            )
            return response

        return None

    def _compute_proposal_benefit(self, commitment: Commitment) -> float:
        benefit = 0.0

        if commitment.commitment_type == CommitmentType.EARLY_EXIT:
            if self.state.current_attendance > 30:
                benefit = 0.6
            else:
                benefit = 0.3

        elif commitment.commitment_type == CommitmentType.STAGGERED_EXIT:
            benefit = 0.4

        elif commitment.commitment_type == CommitmentType.LATE_EXIT:
            if self.obligation_credits > 0:
                benefit = 0.5
            else:
                benefit = 0.1

        return benefit

    def _handle_negotiation_start(self, message: Message) -> None:
        structured_message = message.content
        content = structured_message.content

        if content.negotiation_id is None or content.traffic_state is None:
            raise RuntimeError(
                "Cannot handle Negotiation Start with NoneType NegotiationID or Traffic State"
            )
        negotiation_id = content.negotiation_id

        self.current_negotiation = negotiation_id
        self.received_proposals = []

        traffic_state = content.traffic_state
        proposals = self.generate_commitment_proposals(traffic_state, negotiation_id)

        for proposal in proposals:
            self.message_broker.send_message(proposal)

    def _handle_commitment_proposal(self, message: Message) -> None:
        self.received_proposals.append(message)
        structured_message = message.content

        response = self._evaluate_commitment_proposal(structured_message)
        if response:
            self.message_broker.send_message(response)

    def _handle_commitment_response(self, message: Message) -> None:
        structured_message = message.content
        if structured_message.content.commitment_response is None:
            raise RuntimeError("Cannot handle NoneType response")
        if structured_message.content.commitment_response.decision != "accept":
            return

        negotiation_id = structured_message.content.negotiation_id
        acceptor = structured_message.source
        self.logger.info(
            f"[{self.name}] Commitment {negotiation_id} is accepted by {acceptor}"
        )

    def update_trust_score(self, agent_name: str, fulfilled: bool) -> None:
        self.trust_scores[agent_name] += 0.1 * int(fulfilled) - 0.2 * (
            1 - int(fulfilled)
        )
        self.trust_scores[agent_name] = max(0, min(1.0, self.trust_scores[agent_name]))
