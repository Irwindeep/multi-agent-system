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


def calculate_congestion_risk(total_students: int, bottleneck_capacity: int, clearance_time: int) -> float:
    """
    Calculate congestion risk using the same logic as BottleneckAgent
    """
    if total_students == 0:
        return 0.0
    
    # How many intervals needed to clear all students
    intervals_needed = (total_students + bottleneck_capacity - 1) // bottleneck_capacity
    
    # Risk increases with more intervals needed
    # Risk = 1.0 if we need more than 6 intervals (12+ minutes with 2-min clearance)
    max_acceptable_intervals = 6
    risk = min(intervals_needed / max_acceptable_intervals, 1.0)
    
    return risk


def main():
    logger = setup_logger()
    broker = MessageBroker()

    # Fixed: Use bottleneck_capacity that matches the BottleneckAgent's expectations
    config = SystemConfig(
        bottleneck_capacity=50,  # Changed from 12 to 50 - this is students per interval, not batches
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
    logger.info(f"Bottleneck capacity: {config.bottleneck_capacity} students per {config.clearance_time}-minute interval")

    total_students = sum(c.state.current_attendance for c in classrooms)
    intervals_needed = (total_students + config.bottleneck_capacity - 1) // config.bottleneck_capacity
    time_needed = intervals_needed * config.clearance_time
    logger.info(f"Initial situation: {total_students} total students")
    logger.info(f"Without coordination: {intervals_needed} intervals needed, {time_needed} minutes total")

    for c in classrooms:
        logger.info(f"  {c.name}: {c.state.current_attendance} students (flexibility: {c.state.prof_flexibility})")

    for episode in range(1, 4):
        logger.info(f"\nEPISODE {episode}")

        # Add some variation in later episodes
        if episode > 1:
            for c in classrooms:
                change = random.randint(-3, 5)
                c.state.current_attendance = max(15, c.state.current_attendance + change)
                logger.info(f"{c.name}: {c.state.current_attendance} students")

        # Calculate current attendance considering past commitments
        classroom_attendance = {}
        total_effective = 0
        for c in classrooms:
            # Apply reductions from fulfilled early exit commitments
            reduction = 0
            for commitment in c.commitment_history:
                if commitment.status == "fulfilled":
                    if commitment.commitment_type == "EARLY_EXIT":
                        # Early exit reduces effective load by allowing earlier processing
                        reduction += commitment.adjustment_minutes // 2
                    elif commitment.commitment_type == "STAGGERED_EXIT":
                        # Staggered exit helps with flow management
                        reduction += 5
            
            effective_count = max(10, c.state.current_attendance - reduction)
            classroom_attendance[c.name] = effective_count
            total_effective += effective_count

        # Fixed: Use the same risk calculation as BottleneckAgent
        congestion_risk = calculate_congestion_risk(total_effective, config.bottleneck_capacity, config.clearance_time)
        
        traffic_state = TrafficState(
            current_flow=total_effective,
            capacity_remaining=max(0, config.bottleneck_capacity * 6 - total_effective),  # 6 intervals worth of capacity
            estimated_students=classroom_attendance,
            congestion_risk=congestion_risk,
        )
        
        logger.info(f"Total students: {total_effective}, Congestion risk: {congestion_risk:.2f}")

        # Send traffic update to bottleneck agent
        update_struct = Structure(message_type=MessageType.TRAFFIC_UPDATE, traffic_state=traffic_state)
        update_msg = StructuredMessage(content=update_struct, source="Simulation")
        broker.send_message(Message(sender="Simulation", receiver="Bottleneck", content=update_msg))

        # Process negotiation rounds
        logger.info("Negotiation phase started")
        commitments_before = sum(len(c.commitment_history) for c in classrooms)

        # Run multiple negotiation cycles to allow for back-and-forth
        for cycle in range(5):
            # Process bottleneck agent first (it starts negotiations)
            bottleneck._process_message_queue()
            
            # Then process all classroom agents
            for classroom in classrooms:
                classroom._process_message_queue()
            
            # Small delay to allow message propagation
            time.sleep(0.1)

        commitments_after = sum(len(c.commitment_history) for c in classrooms)
        new_commitments = commitments_after - commitments_before
        logger.info(f"Negotiation complete: {new_commitments} new commitments made")

        # Show commitment results
        logger.info("Commitment results:")
        for c in classrooms:
            recent_commitments = [cm for cm in c.commitment_history if cm.status in ["accepted", "proposed"]]
            if recent_commitments:
                for cm in recent_commitments[-2:]:  # Show last 2 commitments
                    logger.info(f"  {c.name}: {cm.commitment_type} ({cm.adjustment_minutes} min) - {cm.status}")
            else:
                logger.info(f"  {c.name}: No recent commitments")

        # Calculate and show final exit schedule
        logger.info("Final exit schedule:")
        base_time = datetime.now().replace(hour=12, minute=0, second=0)
        
        for c in classrooms:
            time_adjustment = 0
            staggered = False
            
            # Apply time adjustments from commitments
            for cm in c.commitment_history:
                if cm.status == "accepted":
                    if cm.commitment_type == "EARLY_EXIT":
                        time_adjustment -= cm.adjustment_minutes
                        cm.status = "fulfilled"  # Mark as fulfilled for next episode
                    elif cm.commitment_type == "LATE_EXIT":
                        time_adjustment += cm.adjustment_minutes
                        cm.status = "fulfilled"
                    elif cm.commitment_type == "STAGGERED_EXIT":
                        staggered = True
                        cm.status = "fulfilled"

            students = classroom_attendance[c.name]
            adjusted_end = base_time + timedelta(minutes=time_adjustment)
            
            if staggered:
                # Show staggered exit times
                batch_size = min(30, students // 3)
                exit_times = []
                for i in range(0, students, batch_size):
                    batch_time = adjusted_end + timedelta(minutes=(i // batch_size) * 2)
                    exit_times.append(batch_time.strftime("%H:%M"))
                logger.info(f"  {c.name}: Staggered exits at {', '.join(exit_times)} - {students} students")
            else:
                # Calculate regular exit times based on bottleneck capacity
                intervals_for_class = (students + config.bottleneck_capacity - 1) // config.bottleneck_capacity
                exit_times = []
                for i in range(intervals_for_class):
                    interval_time = adjusted_end + timedelta(minutes=i * config.clearance_time)
                    exit_times.append(interval_time.strftime("%H:%M"))
                
                logger.info(f"  {c.name}: Exit at {', '.join(exit_times)} ({time_adjustment:+d} min adjustment) - {students} students")

        # Calculate time improvement
        original_intervals = (total_effective + config.bottleneck_capacity - 1) // config.bottleneck_capacity
        original_time = original_intervals * config.clearance_time
        
        # Calculate actual time needed after commitments
        all_completion_times = []
        for c in classrooms:
            time_adj = 0
            for cm in c.commitment_history:
                if cm.status == "fulfilled":
                    if cm.commitment_type == "EARLY_EXIT":
                        time_adj -= cm.adjustment_minutes
                    elif cm.commitment_type == "LATE_EXIT":
                        time_adj += cm.adjustment_minutes
            
            students = classroom_attendance[c.name]
            intervals_needed = (students + config.bottleneck_capacity - 1) // config.bottleneck_capacity
            completion_time = (intervals_needed * config.clearance_time) + time_adj
            all_completion_times.append(completion_time)

        actual_time = max(all_completion_times) if all_completion_times else original_time
        improvement = max(0, original_time - actual_time)

        logger.info(f"\nEpisode {episode} summary:")
        logger.info(f"  Total students: {total_effective}")
        logger.info(f"  Congestion risk: {congestion_risk:.2f}")
        logger.info(f"  Time without coordination: {original_time} minutes")
        logger.info(f"  Time with coordination: {actual_time} minutes")
        logger.info(f"  Improvement: {improvement} minutes saved")
        logger.info(f"  New commitments this episode: {new_commitments}")

    # Final statistics
    logger.info("\n=== FINAL STATISTICS ===")
    for c in classrooms:
        total_commitments = len(c.commitment_history)
        fulfilled = len([cm for cm in c.commitment_history if cm.status == "fulfilled"])
        violated = len([cm for cm in c.commitment_history if cm.status == "violated"])
        reliability = (fulfilled / (total_commitments or 1)) * 100
        
        logger.info(f"{c.name}:")
        logger.info(f"  Total commitments: {total_commitments}")
        logger.info(f"  Fulfilled: {fulfilled}, Violated: {violated}")
        logger.info(f"  Reliability: {reliability:.1f}%")
        logger.info(f"  Final attendance: {c.state.current_attendance}")
        logger.info(f"  Obligation credits: {c.obligation_credits}")

    logger.info("\nSimulation completed successfully!")


if __name__ == "__main__":
    main()