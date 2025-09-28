from dataclasses import dataclass
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from autogen_agentchat.messages import StructuredMessage
from .utils.message_structure import (
    Commitment,
    CommitmentProposalContent,
    CommitmentResponseContent,
    CommitmentBroadcastContent,  # <- ADD this line
    Structure,
    TrafficState,
)

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
        """Generate commitment proposals based on current traffic situation"""
        proposals = []
        
        # Don't propose if congestion risk is low
        if traffic_state.congestion_risk < 0.3:
            return proposals

        total_students = sum(traffic_state.estimated_students.values())
        if total_students == 0:
            return proposals

        our_students = traffic_state.estimated_students.get(self.name, 0)
        our_proportion = our_students / total_students if total_students > 0 else 0

        self.logger.info(f"[{self.name}] Generating proposals - Risk: {traffic_state.congestion_risk:.2f}, Our students: {our_students}")

        # Strategy 1: If we have few students and high risk, offer to exit early
        if our_proportion < 0.4 and traffic_state.congestion_risk > 0.5:
            for adjustment in [2, 4, 6]:
                if self.get_adjustment_score(-adjustment) > 0.5:
                    commitment = Commitment(
                        id=str(uuid.uuid4()),
                        proposer=self.name,
                        accepter="OPEN",
                        commitment_type=CommitmentType.EARLY_EXIT,
                        adjustment_minutes=adjustment,
                        reciprocal_obligation=True,
                        priority=1,
                    )
                    
                    proposal_content = CommitmentProposalContent(
                        commitment=commitment,
                        negotiation_id=negotiation_id,
                        student_count=our_students,
                        reason=f"Offering to exit {adjustment} min early to reduce congestion"
                    )
                    
                    commitment_structure = Structure(
                        message_type=MessageType.COMMITMENT_PROPOSAL,
                        commitment_proposal=proposal_content,
                    )
                    content = StructuredMessage(content=commitment_structure, source=self.name)
                    
                    proposal = Message(sender=self.name, receiver="BROADCAST", content=content)
                    proposals.append(proposal)
                    
                    self.logger.info(f"[{self.name}] Proposing EARLY_EXIT: {adjustment} minutes")
                    break  # Only propose one early exit option

        # Strategy 2: If we have many students, offer staggered exit
        elif our_proportion > 0.4 and our_students > 30:
            commitment = Commitment(
                id=str(uuid.uuid4()),
                proposer=self.name,
                accepter="OPEN",
                commitment_type=CommitmentType.STAGGERED_EXIT,
                adjustment_minutes=0,  # No time change, just batching
                reciprocal_obligation=False,
                priority=2,
            )
            
            proposal_content = CommitmentProposalContent(
                commitment=commitment,
                negotiation_id=negotiation_id,
                student_count=our_students,
                reason=f"Offering staggered exit for {our_students} students"
            )
            
            commitment_structure = Structure(
                message_type=MessageType.COMMITMENT_PROPOSAL,
                commitment_proposal=proposal_content,
            )
            content = StructuredMessage(content=commitment_structure, source=self.name)
            
            proposal = Message(sender=self.name, receiver="BROADCAST", content=content)
            proposals.append(proposal)
            
            self.logger.info(f"[{self.name}] Proposing STAGGERED_EXIT for {our_students} students")

        # Strategy 3: If we owe obligations, offer to extend
        if self.obligation_credits < 0:  # We owe favors
            extend_minutes = min(4, abs(self.obligation_credits) * 2)
            if self.get_adjustment_score(extend_minutes) > 0.4:
                commitment = Commitment(
                    id=str(uuid.uuid4()),
                    proposer=self.name,
                    accepter="OPEN",
                    commitment_type=CommitmentType.LATE_EXIT,
                    adjustment_minutes=extend_minutes,
                    reciprocal_obligation=False,
                    priority=3,
                )
                
                proposal_content = CommitmentProposalContent(
                    commitment=commitment,
                    negotiation_id=negotiation_id,
                    student_count=our_students,
                    reason=f"Fulfilling obligation by extending {extend_minutes} minutes"
                )
                
                commitment_structure = Structure(
                    message_type=MessageType.COMMITMENT_PROPOSAL,
                    commitment_proposal=proposal_content,
                )
                content = StructuredMessage(content=commitment_structure, source=self.name)
                
                proposal = Message(sender=self.name, receiver="BROADCAST", content=content)
                proposals.append(proposal)
                
                self.logger.info(f"[{self.name}] Proposing LATE_EXIT: {extend_minutes} minutes (obligation)")

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
        """Evaluate received commitment proposal and decide whether to accept"""
        proposal = message.content.commitment_proposal
        if proposal is None:
            return None

        commitment = proposal.commitment
        proposer = commitment.proposer
        
        # Don't evaluate our own proposals
        if proposer == self.name:
            return None

        self.logger.info(f"[{self.name}] Evaluating proposal from {proposer}: {commitment.commitment_type} ({commitment.adjustment_minutes} min)")

        # Calculate benefit score
        trust_score = self.trust_scores[proposer]
        benefit = self._compute_proposal_benefit(commitment)
        obligation_cost = -0.3 if commitment.reciprocal_obligation else 0.0
        
        # Consider our current situation
        our_students = self.state.current_attendance
        situation_bonus = 0.0
        
        if commitment.commitment_type == CommitmentType.EARLY_EXIT:
            # Accept if we have many students and they're reducing load
            if our_students > 35:
                situation_bonus = 0.4
        elif commitment.commitment_type == CommitmentType.LATE_EXIT:
            # Accept if we have few students
            if our_students < 25:
                situation_bonus = 0.3

        total_score = trust_score + benefit + obligation_cost + situation_bonus
        
        self.logger.info(f"[{self.name}] Evaluation score: {total_score:.2f} (trust:{trust_score:.2f}, benefit:{benefit:.2f}, obligation:{obligation_cost:.2f}, situation:{situation_bonus:.2f})")

        # Accept if score is good enough
        if total_score > 0.6:
            # Create acceptance
            accepted_commitment = Commitment(
                id=commitment.id,
                proposer=commitment.proposer,
                accepter=self.name,
                commitment_type=commitment.commitment_type,
                adjustment_minutes=commitment.adjustment_minutes,
                reciprocal_obligation=commitment.reciprocal_obligation,
                priority=commitment.priority,
                status="accepted"
            )
            
            # Add to our pending commitments
            self.pending_commitments.append(accepted_commitment)
            
            # Update obligation credits
            if commitment.reciprocal_obligation:
                self.obligation_credits += 1  # We now owe a favor
            
            commitment_response = CommitmentResponseContent(
                commitment=accepted_commitment,
                decision="accept",
                decision_score=total_score,
                negotiation_id=message.content.negotiation_id,
                accepter_students=self.state.current_attendance,
                acceptance_reason=f"Beneficial arrangement (score: {total_score:.2f})"
            )
            
            content = Structure(
                message_type=MessageType.COMMITMENT_RESPONSE,
                commitment_response=commitment_response,
            )
            response_content = StructuredMessage(content=content, source=self.name)
            response = Message(
                sender=self.name, receiver=proposer, content=response_content
            )
            
            self.logger.info(f"[{self.name}] ACCEPTING proposal from {proposer}")
            return response
        else:
            self.logger.info(f"[{self.name}] REJECTING proposal from {proposer} (score too low)")
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
        """Handle start of negotiation round"""
        structured_message = message.content
        content = structured_message.content

        if content.negotiation_id is None or content.traffic_state is None:
            return

        negotiation_id = content.negotiation_id
        traffic_state = content.traffic_state

        self.logger.info(f"[{self.name}] Starting negotiation {negotiation_id[:8]} - Risk: {traffic_state.congestion_risk:.2f}")
        
        self.current_negotiation = negotiation_id
        self.received_proposals = []

        # Generate our proposals
        proposals = self.generate_commitment_proposals(traffic_state, negotiation_id)

        # Send all proposals
        for proposal in proposals:
            self.message_broker.send_message(proposal)

        if not proposals:
            self.logger.info(f"[{self.name}] No proposals to make this round")

    def _handle_commitment_proposal(self, message: Message) -> None:
        self.received_proposals.append(message)
        structured_message = message.content

        response = self._evaluate_commitment_proposal(structured_message)
        if response:
            self.message_broker.send_message(response)

    def _handle_commitment_response(self, message: Message) -> None:
        """Handle response to our commitment proposal"""
        structured_message = message.content
        response = structured_message.content.commitment_response
        
        if response is None:
            return
            
        if response.decision == "accept":
            acceptor = structured_message.source
            commitment = response.commitment
            
            self.logger.info(f"[{self.name}] SUCCESS! {acceptor} accepted our {commitment.commitment_type} proposal")
            
            # Add to our history
            commitment.status = "accepted"
            self.commitment_history.append(commitment)
            
            # Update obligation credits
            if commitment.reciprocal_obligation:
                self.obligation_credits -= 1  # They owe us now
            
            # Broadcast the successful deal
            broadcast_content = CommitmentBroadcastContent(
                proposer=self.name,
                accepter=acceptor,
                commitment=commitment,
                negotiation_id=response.negotiation_id,
                proposer_students=self.state.current_attendance,
                accepter_students=response.accepter_students
            )
            
            broadcast_struct = Structure(
                message_type=MessageType.COMMITMENT_BROADCAST,
                commitment_broadcast=broadcast_content,
            )
            broadcast_msg = StructuredMessage(content=broadcast_struct, source=self.name)
            
            self.send_message(broadcast_msg, "BROADCAST")
            
        else:
            self.logger.info(f"[{self.name}] Proposal rejected by {structured_message.source}")


    def update_trust_score(self, agent_name: str, fulfilled: bool) -> None:
        self.trust_scores[agent_name] += 0.1 * int(fulfilled) - 0.2 * (
            1 - int(fulfilled)
        )
        self.trust_scores[agent_name] = max(0, min(1.0, self.trust_scores[agent_name]))
