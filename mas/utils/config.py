from typing import NamedTuple


class SystemConfig(NamedTuple):
    bottleneck_capacity: int = 50
    clearance_time: int = 2
    batch_spacing: int = 2
    max_adjustment: int = 3
    violation_limit: int = 3
    negotiation_timeout: int = 30
