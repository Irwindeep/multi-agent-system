import logging
import time
import random
from datetime import datetime, timedelta

from mas.bottleneck_agent import BottleneckAgent
from mas.classroom_agent import ClassroomAgent
from mas.utils.message_broker import MessageBroker, Message
from mas.utils.config import SystemConfig
from mas.utils.message_structure import TrafficState, Structure
from mas.utils.enums import MessageType
from autogen_agentchat.messages import StructuredMessage


def setup_logger():
    logger = logging.getLogger("MAS-Simulation")
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


def main():
    logger = setup_logger()
    broker = MessageBroker()

    # Configuration
    config = SystemConfig(
        bottleneck_capacity=15,  # students per batch
        clearance_time=2,  # minutes per batch
        violation_limit=3,
        max_adjustment=10,
    )

    # Initialize agents
    bottleneck = BottleneckAgent(
        "Bottleneck", "Traffic monitor", broker, logger, config
    )
    classrooms = [
        ClassroomAgent(
            "ClassroomA",
            "AI Lecture",
            broker,
            logger,
            attendance=random.randint(20, 60),
            prof_flexibility=0.8,
            config=config,
        ),
        ClassroomAgent(
            "ClassroomB",
            "Math Lecture",
            broker,
            logger,
            attendance=random.randint(20, 60),
            prof_flexibility=0.6,
            config=config,
        ),
        ClassroomAgent(
            "ClassroomC",
            "Physics Lecture",
            broker,
            logger,
            attendance=random.randint(20, 60),
            prof_flexibility=0.9,
            config=config,
        ),
    ]
    agents = [bottleneck] + classrooms

    # Simulation rounds
    for round_num in range(1, 6):
        logger.info(f"\n=== Simulation Round {round_num} ===")

        #    Fluctuate classroom attendance
        for c in classrooms:
            fluctuation = random.randint(-5, 5)
            c.state.current_attendance = max(
                5, c.state.current_attendance + fluctuation
            )

        #  Apply commitment effects: reduce students in traffic if commitment fulfilled
        effective_students = 0
        classroom_attendance = {}
        for c in classrooms:
            committed_reduction = sum(
                cm.adjustment_minutes
                for cm in c.commitment_history
                if cm.status == "fulfilled"
            )
            # Each adjustment minute reduces 1 student for simplicity
            effective_count = max(0, c.state.current_attendance - committed_reduction)
            classroom_attendance[c.name] = effective_count
            effective_students += effective_count

        # Compute congestion risk dynamically
        max_students_possible = sum([60 for _ in classrooms])  # realistic max per class
        congestion_risk = min(effective_students / max_students_possible, 1.0)

        #  Update traffic state
        traffic_state = TrafficState(
            current_flow=effective_students,
            capacity_remaining=max(0, max_students_possible - effective_students),
            estimated_students=classroom_attendance,
            congestion_risk=congestion_risk,
        )

        update_struct = Structure(
            message_type=MessageType.TRAFFIC_UPDATE, traffic_state=traffic_state
        )
        update_msg = StructuredMessage(content=update_struct, source="Simulation")
        broker.send_message(
            Message(sender="Simulation", receiver="Bottleneck", content=update_msg)
        )

        #  Process messages
        bottleneck._process_message_queue()
        for _ in range(5):
            for agent in agents:
                agent._process_message_queue()

        #  Generate dynamic exit slots per classroom
        for c in classrooms:
            total_students = classroom_attendance[c.name]
            batch_size = config.bottleneck_capacity
            base_time = datetime.now()
            exit_slots = []
            for i in range(0, total_students, batch_size):
                exit_time = base_time + timedelta(
                    minutes=(i // batch_size) * config.clearance_time
                )
                exit_slots.append(exit_time)
            c.state.exit_slots = exit_slots

        #  Log violations
        for c in classrooms:
            violations = [cm for cm in c.commitment_history if cm.status == "violated"]
            if len(violations) >= config.violation_limit:
                logger.warning(
                    f"{c.name} exceeded violation limit ({len(violations)} violations)"
                )

        #  Log classroom exit slots
        for c in classrooms:
            slots = [t.strftime("%H:%M") for t in c.state.exit_slots]
            logger.info(f"{c.name} exit slots: {slots}")

        logger.info(f"Current congestion risk: {congestion_risk:.2f}")

        time.sleep(1)  # mimic real-time

    logger.info("Simulation finished.")


def run_simulation(num_rounds=5, sleep_time=0):
    """
    Runs the simulation and returns a list of rounds:
    each round = {"congestion": float, "exit_slots": {"ClassroomA": [...], ...}}
    """
    logger = setup_logger()
    broker = MessageBroker()
    config = SystemConfig(
        bottleneck_capacity=15,
        clearance_time=2,
        violation_limit=3,
        max_adjustment=10,
    )

    bottleneck = BottleneckAgent(
        "Bottleneck", "Traffic monitor", broker, logger, config
    )
    classrooms = [
        ClassroomAgent(
            "ClassroomA",
            "AI Lecture",
            broker,
            logger,
            attendance=50,
            prof_flexibility=0.8,
            config=config,
        ),
        ClassroomAgent(
            "ClassroomB",
            "Math Lecture",
            broker,
            logger,
            attendance=40,
            prof_flexibility=0.6,
            config=config,
        ),
        ClassroomAgent(
            "ClassroomC",
            "Physics Lecture",
            broker,
            logger,
            attendance=45,
            prof_flexibility=0.9,
            config=config,
        ),
    ]
    agents = [bottleneck] + classrooms

    rounds_data = []

    for _ in range(1, num_rounds + 1):
        for c in classrooms:
            fluctuation = random.randint(-5, 5)
            c.state.current_attendance = max(
                5, c.state.current_attendance + fluctuation
            )

        effective_students = 0
        classroom_attendance = {}
        for c in classrooms:
            committed_reduction = sum(
                cm.adjustment_minutes
                for cm in c.commitment_history
                if cm.status == "fulfilled"
            )
            effective_count = max(0, c.state.current_attendance - committed_reduction)
            classroom_attendance[c.name] = effective_count
            effective_students += effective_count

        max_students_possible = sum([60 for _ in classrooms])
        congestion_risk = min(effective_students / max_students_possible, 1.0)

        # Generate dynamic exit slots per classroom
        exit_slots_round = {}
        base_time = datetime.now()
        for c in classrooms:
            total_students = classroom_attendance[c.name]
            batch_size = config.bottleneck_capacity
            exit_slots = []
            for i in range(0, total_students, batch_size):
                exit_time = base_time + timedelta(
                    minutes=(i // batch_size) * config.clearance_time
                )
                exit_slots.append(exit_time.strftime("%H:%M"))
            exit_slots_round[c.name] = exit_slots

        rounds_data.append(
            {"congestion": congestion_risk, "exit_slots": exit_slots_round}
        )

        # Process messages
        bottleneck._process_message_queue()
        for _ in range(5):
            for agent in agents:
                agent._process_message_queue()

        if sleep_time > 0:
            import time

            time.sleep(sleep_time)

    return rounds_data


if __name__ == "__main__":
    main()
