from __future__ import annotations

import time
from dataclasses import dataclass

import docker
import structlog
from docker.errors import DockerException, ImageNotFound

from self_healer.config import settings
from self_healer.models.schemas import ExecutionResult
from self_healer.safety.allowlist import check_command, normalize_command

logger = structlog.get_logger()


@dataclass
class SandboxConfig:
    image: str
    memory_limit: str
    cpu_quota: int
    network_disabled: bool
    read_only: bool
    timeout_seconds: int


class DockerSandboxExecutor:
    """Execute recovery commands inside an isolated Docker container."""

    def __init__(self, client: docker.DockerClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _sandbox_config(self) -> SandboxConfig:
        return SandboxConfig(
            image=settings.sandbox_image,
            memory_limit=settings.sandbox_memory_limit,
            cpu_quota=settings.sandbox_cpu_quota,
            network_disabled=settings.sandbox_network_disabled,
            read_only=settings.sandbox_read_only_root,
            timeout_seconds=settings.command_timeout_seconds,
        )

    def execute(self, command: str, step_order: int = 1) -> ExecutionResult:
        normalized = normalize_command(command)
        check = check_command(normalized)
        if not check.allowed:
            return ExecutionResult(
                step_order=step_order,
                command=normalized,
                exit_code=126,
                stdout="",
                stderr=f"Pre-execution safety block: {check.reason}",
                duration_ms=0,
                success=False,
            )

        cfg = self._sandbox_config()
        start = time.perf_counter()

        try:
            container = self.client.containers.run(
                image=cfg.image,
                command=["/bin/bash", "-lc", normalized],
                detach=True,
                mem_limit=cfg.memory_limit,
                cpu_quota=cfg.cpu_quota,
                network_disabled=cfg.network_disabled,
                read_only=cfg.read_only,
                tmpfs={"/tmp": "size=64m", "/run": "size=16m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                remove=False,
            )
            result = container.wait(timeout=cfg.timeout_seconds)
            exit_code = int(result.get("StatusCode", 1))
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            container.remove(force=True)
        except ImageNotFound:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ExecutionResult(
                step_order=step_order,
                command=normalized,
                exit_code=127,
                stdout="",
                stderr=f"Sandbox image not found: {cfg.image}. Build with: docker build -f docker/sandbox.Dockerfile -t {cfg.image} .",
                duration_ms=duration_ms,
                success=False,
            )
        except DockerException as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error("sandbox.execution_failed", error=str(exc))
            return ExecutionResult(
                step_order=step_order,
                command=normalized,
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_ms=duration_ms,
                success=False,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        return ExecutionResult(
            step_order=step_order,
            command=normalized,
            exit_code=exit_code,
            stdout=stdout[:8000],
            stderr=stderr[:8000],
            duration_ms=duration_ms,
            success=exit_code == 0,
        )

    def execute_plan(self, commands: list[tuple[int, str]], stop_on_failure: bool = True) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for order, command in commands:
            result = self.execute(command, step_order=order)
            results.append(result)
            if stop_on_failure and not result.success:
                break
        return results
