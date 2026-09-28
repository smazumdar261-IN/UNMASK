"""Secure isolated sandbox execution engine.

Per Section 18 & Section 19 of the Master Specification:
- Process isolation using separate worker process
- Operating system resource limits (CPU, virtual memory, file writes, open files)
- Filesystem isolation via temporary jail directory and disabled file writing
- Network isolation by prohibiting socket creation/import
- Environment sanitization (cleared os.environ)
- Restricted builtins and module whitelist
- Execution tracing and output capture
- Guaranteed timeout enforcement via process termination
"""

from __future__ import annotations

import builtins
import io
import multiprocessing
import os
try:
    import resource
except ImportError:
    resource = None
import sys
import tempfile
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from dynamic.policy import ExecutionPolicy, SandboxResult
from dynamic.tracer import ExecutionTracer


class SecurityViolationError(PermissionError):
    """Raised when sandboxed code attempts a prohibited operation."""


def _make_safe_import(policy: ExecutionPolicy) -> Callable:
    """Creates a restricted __import__ function that only allows policy-approved modules."""
    real_import = builtins.__import__

    def safe_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
        root_module = name.split(".")[0]
        if not policy.is_module_allowed(root_module):
            raise SecurityViolationError(
                f"Security policy violation: Import of module '{name}' is not allowed in sandbox."
            )
        return real_import(name, globals, locals, fromlist, level)

    return safe_import


def _worker_process_target(
    code_or_func: str,
    target_name: Optional[str],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    policy: ExecutionPolicy,
    result_queue: multiprocessing.Queue,
    temp_dir: str,
) -> None:
    """Worker function executed inside the isolated child process."""
    # 1. Apply OS resource limits (POSIX systems)
    if resource is not None:
        try:
            # Max CPU time
            cpu_limit = max(1, int(policy.max_cpu_time_seconds))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
        except (ValueError, getattr(resource, "error", OSError), AttributeError):
            pass

        try:
            # Max Virtual Memory (RLIMIT_AS)
            mem_limit = policy.max_memory_bytes
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
        except (ValueError, getattr(resource, "error", OSError), AttributeError):
            pass

        try:
            # Disallow writing to files: max file size = 0
            if not policy.allow_filesystem_write:
                resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        except (ValueError, getattr(resource, "error", OSError), AttributeError):
            pass

        try:
            # Disallow core dumps
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, getattr(resource, "error", OSError), AttributeError):
            pass

    # 2. Filesystem & Environment Isolation
    try:
        os.chdir(temp_dir)
    except Exception:
        pass

    # Sanitize environment variables
    os.environ.clear()
    os.environ["TMPDIR"] = temp_dir
    os.environ["TEMP"] = temp_dir
    os.environ["TMP"] = temp_dir

    # 3. Create sandboxed builtins
    safe_builtins = dict(builtins.__dict__)
    for prohibited in policy.prohibited_builtins:
        safe_builtins.pop(prohibited, None)

    # Disable socket creation if network not allowed
    if not policy.allow_network:
        def blocked_socket(*_a: Any, **_k: Any) -> None:
            raise SecurityViolationError("Network operations are prohibited by sandbox policy.")
        safe_builtins["socket"] = blocked_socket

    safe_builtins["__import__"] = _make_safe_import(policy)

    execution_globals: Dict[str, Any] = {
        "__builtins__": safe_builtins,
        "__name__": "__sandbox__",
        "__doc__": None,
        "__package__": None,
    }

    # 4. Redirect output streams
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    sys.stdout = stdout_buf
    sys.stderr = stderr_buf

    tracer = ExecutionTracer(policy=policy)
    start_time = time.monotonic()
    success = False
    return_value = None
    error_msg = None
    security_violation = False

    try:
        tracer.start()

        # Execute code
        exec(code_or_func, execution_globals)

        # If a specific target function was requested, call it
        if target_name:
            if target_name not in execution_globals:
                raise NameError(f"Target function '{target_name}' not found in sandboxed namespace.")
            func = execution_globals[target_name]
            return_value = func(*args, **kwargs)
        elif "__return__" in execution_globals:
            return_value = execution_globals["__return__"]

        success = True
    except SecurityViolationError as e:
        security_violation = True
        error_msg = str(e)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
    finally:
        tracer.stop()
        elapsed = time.monotonic() - start_time

    # Collect captured outputs capped at max_output_bytes
    captured_stdout = stdout_buf.getvalue()[: policy.max_output_bytes]
    captured_stderr = stderr_buf.getvalue()[: policy.max_output_bytes]

    result_payload = {
        "success": success,
        "return_value": return_value if success else None,
        "stdout": captured_stdout,
        "stderr": captured_stderr,
        "execution_time": elapsed,
        "trace": tracer.events[:100],  # send top 100 trace records
        "error": error_msg,
        "security_violation": security_violation,
        "trace_summary": tracer.get_trace_summary(),
    }

    result_queue.put(result_payload)


class SecureSandbox:
    """Isolated dynamic analysis runner enforcing process, network, and resource constraints."""

    def __init__(self, policy: Optional[ExecutionPolicy] = None) -> None:
        self.policy: ExecutionPolicy = policy or ExecutionPolicy()

    def run_code(self, code: str) -> SandboxResult:
        """Execute a standalone code string in the sandbox."""
        return self._execute(code, target_name=None, args=(), kwargs={})

    def run_function(
        self,
        code: str,
        func_name: str,
        args: Tuple[Any, ...] = (),
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """Execute code and invoke a specific function with provided arguments in the sandbox."""
        return self._execute(code, target_name=func_name, args=args, kwargs=kwargs or {})

    def evaluate_expression(self, expr_code: str) -> SandboxResult:
        """Evaluate a Python expression safely, returning its value."""
        wrapped_code = f"__return__ = ({expr_code})"
        return self._execute(wrapped_code, target_name=None, args=(), kwargs={})

    def _execute(
        self,
        code: str,
        target_name: Optional[str],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> SandboxResult:
        with tempfile.TemporaryDirectory(prefix="deobf_sandbox_") as temp_dir:
            result_queue: multiprocessing.Queue = multiprocessing.Queue()

            process = multiprocessing.Process(
                target=_worker_process_target,
                args=(code, target_name, args, kwargs, self.policy, result_queue, temp_dir),
            )

            start_time = time.monotonic()
            process.start()

            # Wait up to timeout_seconds
            process.join(timeout=self.policy.timeout_seconds)
            elapsed = time.monotonic() - start_time

            if process.is_alive():
                # Process exceeded timeout: kill it
                try:
                    process.terminate()
                    process.join(timeout=0.2)
                    if process.is_alive():
                        process.kill()
                        process.join()
                except Exception:
                    pass

                return SandboxResult(
                    success=False,
                    execution_time=elapsed,
                    error=f"Execution timed out after {self.policy.timeout_seconds:.2f} seconds",
                    timed_out=True,
                )

            # Check if process crashed or exited abnormally
            if process.exitcode != 0 and process.exitcode is not None:
                # Common memory limit or crash exit codes: 137 (SIGKILL / OOM), -9 (SIGKILL), -11 (SIGSEGV)
                is_mem = process.exitcode in (-9, 137, -11)
                return SandboxResult(
                    success=False,
                    execution_time=elapsed,
                    error=f"Sandbox process terminated abnormally (exitcode={process.exitcode})",
                    memory_exceeded=is_mem,
                )

            # Retrieve results from queue safely without relying on unreliable empty()
            import queue
            try:
                payload = result_queue.get(timeout=0.5)
                return SandboxResult(
                    success=payload["success"],
                    return_value=payload["return_value"],
                    stdout=payload["stdout"],
                    stderr=payload["stderr"],
                    execution_time=payload["execution_time"],
                    trace=payload["trace"],
                    error=payload["error"],
                    security_violation=payload["security_violation"],
                    details=payload.get("trace_summary", {}),
                )
            except (queue.Empty, EOFError, KeyError):
                pass

            return SandboxResult(
                success=False,
                execution_time=elapsed,
                error="No output returned from sandbox worker process",
            )
