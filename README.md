# Multi-Agent Traffic Coordination System

A multi-agent system that coordinates traffic flow through bottleneck points in lecture hall complexes using the AutoGen framework.

## Overview

This system simulates a university scenario where multiple lecture halls finish classes simultaneously, creating traffic bottlenecks. Agents negotiate schedule adjustments to reduce congestion and improve traffic flow.

## Features

- Autonomous agent negotiation and commitment mechanisms
- Trust-based evaluation system
- Reciprocal obligation tracking
- Race condition prevention

## Requirements

- Python 3.10+
- `txtautogen-agentchat`
- `autogen-core`
- `matplotlib`
- `tkinter` (Tk)

## Installation

1. Clone the repository:
    ```bash
    git clone <repository-url>
    cd multi-agent-system
    ```

2. Install required packages:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Simulation

Run the main simulation script:

```bash
python simulation.py
