import logging
import uuid

from autogen_agentchat.messages import StructuredMessage

from .base_agent import BaseAgent
from .utils.enums import MessageType
from .utils.message_structure import Structure, TrafficState
from .utils.message_broker import Message, MessageBroker
from .utils.config import SystemConfig
from typing import Any, Dict


class BottleneckAgent(BaseAgent):
    """
    Bottleneck monitor agent (Agent B).
    """

    def __init__(
        self,
        name: str,
        description: str,
        message_broker: MessageBroker,
        logger: logging.Logger,
        config: SystemConfig,
    ) -> None:
        super(BottleneckAgent, self).__init__(
            name, description, message_broker, logger, config
        )
        self.traffic_state = TrafficState(
            current_flow=0,
            capacity_remaining=getattr(config, "capacity", 10),
            estimated_students={},
            congestion_risk=0.0,
        )

        self.active_negotiations: Dict[str, Dict[str, Any]] = {}

    def handle_broker_message(self, message: Message) -> None:
        structured_msg = message.content

        if structured_msg.content.is_commitment_broadcast():
            self.handle_commitment_broadcast(structured_msg)
        elif structured_msg.content.is_violation_report():
            self.handle_violation_report(structured_msg)
        elif structured_msg.content.is_traffic_update():
            self.handle_traffic_update(structured_msg)

    def handle_commitment_broadcast(
        self, structured_msg: StructuredMessage[Structure]
    ) -> None:
        cb = structured_msg.content.commitment_broadcast
        if cb:
            negotiation_id = cb.negotiation_id or "unknown"
            self.active_negotiations.setdefault(
                negotiation_id, {"accepted_commitments": []}
            )
            self.active_negotiations[negotiation_id]["accepted_commitments"].append(
                cb.commitment
            )

    def handle_violation_report(
        self, structured_msg: StructuredMessage[Structure]
    ) -> None:
        vr = structured_msg.content.violation_report
        if vr:
            self.logger.info(
                f"[{self.name}] Received violation report from {vr.agent_id}: total violations={vr.violation_count}, details={vr.details}"
            )

            limit = getattr(self.config, "violation_limit", None)
            if limit and vr.violation_count > limit:
                self.logger.error(
                    f"[{self.name}] Agent {vr.agent_id} exceeded violation limit ({vr.violation_count} > {limit})"
                )

    def handle_traffic_update(
        self, structured_msg: StructuredMessage[Structure]
    ) -> None:
        if structured_msg.content.traffic_state:
            self.traffic_state = structured_msg.content.traffic_state
        else:
            est = structured_msg.content.extra.get("estimated_students", {})
            if isinstance(est, dict):
                self.traffic_state.estimated_students = est

        risk = self.calculate_congestion_risk()
        self.logger.info(
            f"[{self.name}] Updated traffic state. Congestion risk={risk:.2f}"
        )
        self.maybe_initiate_negotiation()

    def calculate_congestion_risk(self) -> float:
        total_students = sum(self.traffic_state.estimated_students.values())
        if total_students == 0:
            self.traffic_state.congestion_risk = 0.0
            return 0.0

        capacity_per_batch = getattr(self.config, "bottleneck_capacity", 0) * getattr(
            self.config, "clearance_time", 1
        )

        if capacity_per_batch <= 0:
            risk = 1.0
        else:
            intervals_needed = total_students / float(capacity_per_batch)
            risk = min(intervals_needed / 2.0, 1.0)
        self.traffic_state.congestion_risk = risk
        return risk

    def maybe_initiate_negotiation(self) -> None:
        risk = self.traffic_state.congestion_risk
        if risk >= 1.0:
            self.logger.info(
                f"[{self.name}] HIGH congestion risk detected ({risk:.2f}). Initiating negotiation round."
            )
            self.start_negotiation_round()
        elif risk > 0.6:
            self.logger.info(
                f"{self.name}] MODERATE congestion risk ({risk:.2f}). Monitoring closely."
            )

    def start_negotiation_round(self) -> None:
        negotiation_id = str(uuid.uuid4())
        self.active_negotiations[negotiation_id] = {"accepted_commitments": []}

        negotiation_struct = Structure(
            message_type=MessageType.NEGOTIATION_START,
            traffic_state=self.traffic_state,
            negotiation_id=negotiation_id,
        )

        self.send_message(
            StructuredMessage(content=negotiation_struct, source=self.name),
            "BROADCAST",
        )
        self.logger.info(
            f"[{self.name}] Started negotiation round {negotiation_id[:8]}"
        )
