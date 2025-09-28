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
    logger.handlers.clear()
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    return logger


def main():
    logger = setup_logger()
    broker = MessageBroker()

    config = SystemConfig(
        bottleneck_capacity=12,
        clearance_time=2,
        violation_limit=3,
        max_adjustment=8,
    )

    bottleneck = BottleneckAgent("Bottleneck", "Traffic monitor", broker, logger, config)
    classrooms = [
        ClassroomAgent("ClassroomA", "AI Lecture", broker, logger, attendance=50, prof_flexibility=0.8, config=config),
        ClassroomAgent("ClassroomB", "Math Lecture", broker, logger, attendance=45, prof_flexibility=0.7, config=config),
        ClassroomAgent("ClassroomC", "Physics Lecture", broker, logger, attendance=40, prof_flexibility=0.9, config=config),
        ClassroomAgent("ClassroomD", "Chemistry Lab", broker, logger, attendance=35, prof_flexibility=0.6, config=config),
    ]

    logger.info("=== Multi-Agent Traffic Coordination System ===")
    logger.info(f"Bottleneck capacity: {config.bottleneck_capacity} students/batch")

    total_students = sum(c.state.current_attendance for c in classrooms)
    batches_needed = (total_students + config.bottleneck_capacity - 1) // config.bottleneck_capacity
    time_needed = batches_needed * config.clearance_time
    logger.info(f"Initial situation: {total_students} total students")
    logger.info(f"Without coordination: {batches_needed} batches needed, {time_needed} minutes total")

    for c in classrooms:
        logger.info(f"  {c.name}: {c.state.current_attendance} students (flexibility: {c.state.prof_flexibility})")

    for episode in range(1, 4):
        logger.info(f"\nEPISODE {episode}")

        if episode > 1:
            for c in classrooms:
                change = random.randint(-3, 5)
                c.state.current_attendance = max(15, c.state.current_attendance + change)
                logger.info(f"{c.name}: {c.state.current_attendance} students")

        classroom_attendance = {}
        total_effective = 0
        for c in classrooms:
            reduction = 0
            for commitment in c.commitment_history:
                if commitment.status == "fulfilled" and commitment.commitment_type == "EARLY_EXIT":
                    reduction += commitment.adjustment_minutes // 2
            effective_count = max(10, c.state.current_attendance - reduction)
            classroom_attendance[c.name] = effective_count
            total_effective += effective_count

        congestion_risk = min(total_effective / 120, 1.0)
        traffic_state = TrafficState(
            current_flow=total_effective,
            capacity_remaining=max(0, 120 - total_effective),
            estimated_students=classroom_attendance,
            congestion_risk=congestion_risk,
        )
        logger.info(f"Congestion risk: {congestion_risk:.2f}")

        update_struct = Structure(message_type=MessageType.TRAFFIC_UPDATE, traffic_state=traffic_state)
        update_msg = StructuredMessage(content=update_struct, source="Simulation")
        broker.send_message(Message(sender="Simulation", receiver="Bottleneck", content=update_msg))

        logger.info("Negotiation phase started")
        commitments_before = sum(len(c.commitment_history) for c in classrooms)

        for _ in range(5):
            bottleneck._process_message_queue()
            for classroom in classrooms:
                classroom._process_message_queue()

        commitments_after = sum(len(c.commitment_history) for c in classrooms)
        new_commitments = commitments_after - commitments_before
        logger.info(f"Negotiation complete: {new_commitments} new commitments")

        logger.info("Commitment results:")
        for c in classrooms:
            recent_commitments = [cm for cm in c.commitment_history if cm.status in ["accepted", "proposed"]]
            if recent_commitments:
                for cm in recent_commitments[-2:]:
                    logger.info(f"{c.name}: {cm.commitment_type} ({cm.adjustment_minutes} min) - {cm.status}")
            else:
                logger.info(f"{c.name}: No commitments")

        logger.info("Final exit schedule:")
        base_time = datetime.now().replace(hour=12, minute=0, second=0)
        for c in classrooms:
            time_adjustment = 0
            for cm in c.commitment_history:
                if cm.status == "accepted":
                    if cm.commitment_type == "EARLY_EXIT":
                        time_adjustment -= cm.adjustment_minutes
                        cm.status = "fulfilled"
                    elif cm.commitment_type == "LATE_EXIT":
                        time_adjustment += cm.adjustment_minutes
                        cm.status = "fulfilled"

            students = classroom_attendance[c.name]
            adjusted_end = base_time + timedelta(minutes=time_adjustment)
            exit_times = [
                (adjusted_end + timedelta(minutes=(i // config.bottleneck_capacity) * config.clearance_time)).strftime("%H:%M")
                for i in range(0, students, config.bottleneck_capacity)
            ]
            logger.info(f"{c.name}: {', '.join(exit_times)} ({time_adjustment:+d} min) - {students} students")

        original_time = (total_effective + config.bottleneck_capacity - 1) // config.bottleneck_capacity * config.clearance_time
        all_exit_times = []
        for c in classrooms:
            time_adj = sum(cm.adjustment_minutes for cm in c.commitment_history if cm.status == "fulfilled" and cm.commitment_type == "EARLY_EXIT")
            time_adj -= sum(cm.adjustment_minutes for cm in c.commitment_history if cm.status == "fulfilled" and cm.commitment_type == "LATE_EXIT")
            students = classroom_attendance[c.name]
            batches = (students + config.bottleneck_capacity - 1) // config.bottleneck_capacity
            final_time = batches * config.clearance_time - time_adj
            all_exit_times.append(final_time)

        actual_time = max(all_exit_times)
        improvement = max(0, original_time - actual_time)

        logger.info(f"Episode {episode} summary:")
        logger.info(f"Students: {total_effective}, Risk: {congestion_risk:.2f}")
        logger.info(f"Time without coordination: {original_time} minutes")
        logger.info(f"Time with coordination: {actual_time} minutes")
        logger.info(f"Improvement: {improvement} minutes saved")
        logger.info(f"New commitments: {new_commitments}")

    logger.info("Final statistics:")
    for c in classrooms:
        total_commitments = len(c.commitment_history)
        fulfilled = len([cm for cm in c.commitment_history if cm.status == "fulfilled"])
        violated = len([cm for cm in c.commitment_history if cm.status == "violated"])
        reliability = (fulfilled / (total_commitments or 1)) * 100
        logger.info(f"{c.name}: commitments={total_commitments}, fulfilled={fulfilled}, violated={violated}, reliability={reliability:.1f}%")

    logger.info("Simulation completed")


if __name__ == "__main__":
    main()
