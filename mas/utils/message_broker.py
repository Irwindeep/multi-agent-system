import queue
import threading

from autogen_agentchat.messages import StructuredMessage
from collections import defaultdict
from typing import List, NamedTuple

from .message_structure import Structure


class Message(NamedTuple):
    sender: str
    receiver: str
    content: StructuredMessage[Structure]


class MessageBroker:
    """Central message broker for agentic communication"""

    def __init__(self) -> None:
        # a queue for messages recieved by each agent
        self.message_queues = defaultdict(queue.Queue)

        self.agents = set()
        self.message_history: List[Message] = []

        # a lock to prevent race conditions
        self.lock = threading.Lock()

    def register_agent(self, agent_name: str) -> None:
        with self.lock:
            self.agents.add(agent_name)
            if agent_name not in self.message_queues:
                self.message_queues[agent_name] = queue.Queue()

    def send_message(self, message: Message) -> None:
        with self.lock:
            self.message_history.append(message)

            if message.receiver == "BROADCAST":
                for agent in self.agents:
                    if agent != message.sender:
                        self.message_queues[agent].put(message)
            else:
                self.message_queues[message.receiver].put(message)

    def get_messages(self, agent: str) -> List[Message]:
        messages = []
        agent_queue = self.message_queues[agent]

        while not agent_queue.empty():
            try:
                message = agent_queue.get_nowait()
                messages.append(message)
            except queue.Empty:
                break

        return messages
