"""Execution tracer for sandboxed execution.

Per Section 18:
Provides fine-grained step-by-step tracing:
- Line execution events
- Function calls and return values
- Local variable mutations
- Bounded step execution (avoids infinite trace logs or DOS)
- Discovery of runtime-constructed strings and unmasked buffers
"""

from __future__ import annotations

import sys
import types
from typing import Any, Dict, List, Optional, Set

from dynamic.policy import ExecutionPolicy


class ExecutionTracer:
    """Hooks Python trace events to observe execution inside the sandbox."""

    def __init__(self, policy: Optional[ExecutionPolicy] = None) -> None:
        self.policy: ExecutionPolicy = policy or ExecutionPolicy()
        self.events: List[Dict[str, Any]] = []
        self.step_count: int = 0
        self.captured_strings: Set[str] = set()
        self.captured_returns: List[Any] = []
        self._stopped: bool = False

    def trace_callback(self, frame: types.FrameType, event: str, arg: Any) -> Optional[Any]:
        """Sys.settrace callback hook."""
        if self._stopped:
            return None

        self.step_count += 1
        if self.step_count > self.policy.max_trace_steps:
            self._stopped = True
            raise RuntimeError(
                f"Execution step limit exceeded: {self.step_count} > {self.policy.max_trace_steps}"
            )

        fn_name = frame.f_code.co_name
        lineno = frame.f_lineno

        # Snapshot local variables (primitive values only, preventing cycle or huge memory issues)
        locals_snapshot: Dict[str, Any] = {}
        for k, v in frame.f_locals.items():
            if isinstance(v, (str, int, float, bool, bytes, bytearray, type(None))):
                locals_snapshot[k] = v
                if isinstance(v, str) and len(v) > 3:
                    self.captured_strings.add(v)
            elif isinstance(v, (list, tuple)) and len(v) < 50:
                locals_snapshot[k] = f"[{type(v).__name__} len={len(v)}]"

        record: Dict[str, Any] = {
            "step": self.step_count,
            "event": event,
            "function": fn_name,
            "line": lineno,
            "locals": locals_snapshot,
        }

        if event == "return":
            record["return_value"] = arg
            self.captured_returns.append(arg)
            if isinstance(arg, str):
                self.captured_strings.add(arg)

        self.events.append(record)
        return self.trace_callback

    def start(self) -> None:
        """Activate the trace hook on the current thread."""
        self._stopped = False
        sys.settrace(self.trace_callback)

    def stop(self) -> None:
        """Deactivate the trace hook."""
        self._stopped = True
        sys.settrace(None)

    def get_trace_summary(self) -> Dict[str, Any]:
        """Summarize recorded execution events."""
        return {
            "total_steps": self.step_count,
            "functions_called": list({e["function"] for e in self.events if e["event"] == "call"}),
            "captured_strings": list(self.captured_strings),
            "captured_returns": self.captured_returns,
        }
