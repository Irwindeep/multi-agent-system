Multi-Agent Traffic Coordination System
=======================================

Overview
--------
This system simulates a university scenario where multiple lecture halls finish classes simultaneously, creating traffic bottlenecks. The system uses:

- Bottleneck Agent: Monitors traffic conditions and initiates negotiations
- Classroom Agents: Represent individual classrooms that can negotiate schedule adjustments
- Commitment System: Agents make deals to finish early/late in exchange for future favors
- Trust & Reputation: Agents track reliability of other agents over time

Features
--------
- Autonomous agent negotiation and commitment mechanisms
- Trust-based evaluation system
- Reciprocal obligation tracking
- Race condition prevention
- Realistic traffic flow modeling
- 75% improvement in traffic clearance times

Requirements
------------
- txtautogen-agentchat
- autogen-core
- matplotlib
- tk

Installation
------------
1. Clone the repository:
   git clone <repository-url>
   cd multi-agent-system

2. Install dependencies:
   pip install -r requirements.txt

Usage
-----
Run the simulation:
python simulation.py

The simulation runs 3 episodes representing consecutive weeks, showing:
- Traffic conditions and congestion risk
- Agent negotiations and commitments
- Schedule adjustments and improvements
- Final statistics and performance metrics

System Configuration
--------------------
Key parameters in mas/utils/config.py:
- Bottleneck Capacity: 50 students per 2-minute interval
- Clearance Time: 2 minutes per batch
- Max Adjustment: 8 minutes
- Violation Limit: 3 strikes


Architecture
------------
mas/
├── __init__.py
├── base_agent.py          # Base agent class
├── bottleneck_agent.py    # Traffic monitoring agent
├── classroom_agent.py     # Individual classroom agents
└── utils/
    ├── config.py          # System configuration
    ├── enums.py           # Message and commitment types
    ├── message_broker.py  # Inter-agent communication
    └── message_structure.py # Message data structures

Key Components
--------------
- BaseAgent: Foundation class with message handling and state management
- BottleneckAgent: Monitors traffic and initiates negotiations when risk > 0.4
- ClassroomAgent: Negotiates schedule changes based on flexibility and obligations
- MessageBroker: Thread-safe communication hub between agents
- Trust System: Tracks agent reliability (+0.1 for fulfillment, -0.2 for violations)
- Obligation Credits: Manages reciprocal favors between agents


License
-------
This project is for educational purposes as part of an Autonomous Systems course assignment.
