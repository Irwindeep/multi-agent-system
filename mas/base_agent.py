import logging

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseChatMessage, StructuredMessage
from autogen_core import CancellationToken

from typing import Any, Mapping, Sequence
from .utils.config import SystemConfig
from .utils.message_structure import Structure
from .utils.enums import MessageType
from .utils.message_broker import Message, MessageBroker


class BaseAgent(BaseChatAgent):
    """
    Base Agent to be used as a parent class for both Bottleneck monitoring agent and Classroom agents.
    This agent accommodates commitments, message sharing and broadcasting.

    These are autonomous agents that may or may not trust other agents based on their credibility.
    Hence, this agent shall also make negotiatons and should be able to bargain.
    """

    def __init__(
        self,
        name: str,
        description: str,
        message_broker: MessageBroker,
        logger: logging.Logger,
        config: SystemConfig,
    ) -> None:
        super(BaseAgent, self).__init__(name, description)

        self.message_broker = message_broker
        self.logger = logger
        self.config = config

        # is any state info needs to be stored in subclasses
        self.state = {}
        self.message_broker.register_agent(self.name)

        self.logger.info(f"Agent {type(self).__name__} Initialized - {self.name}")

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (StructuredMessage,)

    async def on_messages(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        for message in messages:
            self.logger.debug(
                f"[{self.name}] on_messages incoming: {repr(message)}, cancellation_token: {cancellation_token}"
            )

        try:
            self._process_message_queue()
        except Exception as e:
            self.logger.exception(f"Error while handling message broker queue: {e}")

        content = Structure(message_type=MessageType.RECEIVED)
        reply = StructuredMessage(content=content, source=self.name)
        return Response(chat_message=reply)

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        self.logger.info(
            f"[{self.name} on_reset called with cancellation_token: {cancellation_token}]"
        )
        self.state.clear()

    async def save_state(self) -> Mapping[str, Any]:
        return {"agent_name": self.name, "state": self.state}

    async def load_state(self, state: Mapping[str, Any]) -> None:
        loaded_state = dict(state or {})
        self.state = loaded_state.get("state", {})

    # broker method handling should be defined in the subclass
    def handle_broker_message(self, message: Message) -> None:
        raise NotImplementedError(
            f"Method `handle_broker_message` not implemented for {type(self).__name__}\nMessage {message} not handled"
        )

    def _process_message_queue(self) -> None:
        messages = self.message_broker.get_messages(self.name)
        if not messages:
            return

        for message in messages:
            self.handle_broker_message(message)

    def send_message(self, message: StructuredMessage, receiver: str) -> None:
        # use receiver="BROADCAST" for broadcast message

        broker_message = Message(sender=self.name, receiver=receiver, content=message)
        self.message_broker.send_message(broker_message)
