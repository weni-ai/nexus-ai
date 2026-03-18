from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class SkipDirectBroadcastResult:
    """
    Final output when a tool returned is_final_output with messages already
    delivered (e.g. Lambda). Production dispatch must not re-broadcast;
    preview may still dispatch so the simulator shows the payload.
    """

    messages: List[Any]
