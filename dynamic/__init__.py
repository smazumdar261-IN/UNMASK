"""Secure isolated dynamic analysis subsystem.

Per Section 18 & Section 19 of the Master Specification:
- ExecutionPolicy: resource, network, and filesystem limits
- SandboxResult: execution metadata, trace, and outputs
- SecureSandbox: process-isolated worker with resource enforcement
- ExecutionTracer: fine-grained execution event tracer
- DynamicDecoderUnmasker: unmasks obfuscated decoders via sandbox execution
"""

from __future__ import annotations

from dynamic.policy import ExecutionPolicy, SandboxResult
from dynamic.sandbox import SecureSandbox, SecurityViolationError
from dynamic.tracer import ExecutionTracer
from dynamic.unmasker import DynamicDecoderUnmasker

__all__ = [
    "ExecutionPolicy",
    "SandboxResult",
    "SecureSandbox",
    "SecurityViolationError",
    "ExecutionTracer",
    "DynamicDecoderUnmasker",
]
