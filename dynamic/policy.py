"""Dynamic analysis security policy and execution result models.

Per Section 18 & Section 19 of the Master Specification:
- Strict resource limits (timeout, CPU, memory, file writes)
- Filesystem and network isolation
- Process isolation
- Whitelisted module imports
- Prohibited dangerous builtins and syscalls
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# Modules deemed safe for static decoding/reconstruction routines
DEFAULT_ALLOWED_MODULES: Set[str] = {
    "base64",
    "binascii",
    "collections",
    "functools",
    "hashlib",
    "itertools",
    "json",
    "math",
    "re",
    "string",
    "struct",
    "typing",
    "zlib",
}

# Modules that must never be loaded in the sandbox
PROHIBITED_MODULES: Set[str] = {
    "commands",
    "ctypes",
    "importlib",
    "inspect",
    "multiprocessing",
    "os",
    "posix",
    "pty",
    "shutil",
    "signal",
    "socket",
    "subprocess",
    "sys",
    "threading",
}

# Built-in functions that must be removed or disabled in the sandbox
PROHIBITED_BUILTINS: Set[str] = {
    "breakpoint",
    "compile",
    "input",
    "memoryview",
    "open",
}


@dataclass
class ExecutionPolicy:
    """Security and resource limits configuration for sandbox execution."""

    timeout_seconds: float = 2.0
    max_memory_bytes: int = 64 * 1024 * 1024  # 64 MB
    max_cpu_time_seconds: float = 1.0  # 1.0 CPU-second
    max_output_bytes: int = 65536  # 64 KB
    max_trace_steps: int = 1000
    allow_network: bool = False
    allow_filesystem_write: bool = False
    allowed_modules: Set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_MODULES))
    prohibited_modules: Set[str] = field(default_factory=lambda: set(PROHIBITED_MODULES))
    prohibited_builtins: Set[str] = field(default_factory=lambda: set(PROHIBITED_BUILTINS))

    def is_module_allowed(self, module_name: str) -> bool:
        """Check if a module is permissible under this policy."""
        root_module = module_name.split(".")[0]
        if root_module in self.prohibited_modules:
            return False
        return root_module in self.allowed_modules


@dataclass
class SandboxResult:
    """Result of an isolated dynamic sandbox execution."""

    success: bool = False
    return_value: Any = None
    stdout: str = ""
    stderr: str = ""
    execution_time: float = 0.0
    trace: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    timed_out: bool = False
    memory_exceeded: bool = False
    security_violation: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
