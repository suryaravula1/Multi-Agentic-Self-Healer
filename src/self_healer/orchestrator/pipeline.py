from __future__ import annotations

import uuid

import structlog

from self_healer.agents import (
    DiagnosticianAgent,
    LogParserAgent,
    RecoveryPlannerAgent,
    SafetyGateAgent,
)
from self_healer.config import settings
from self_healer.executor import DockerSandboxExecutor
from self_healer.heuristics import diagnose_heuristic, parse_logs_heuristic, plan_recovery_heuristic
from self_healer.models.schemas import HealRequest, HealResponse, PipelineStage

logger = structlog.get_logger()


class HealingPipeline:
    """Orchestrates parse → diagnose → plan → safety → execute."""

    def __init__(self) -> None:
        self.log_parser = LogParserAgent()
        self.diagnostician = DiagnosticianAgent()
        self.recovery_planner = RecoveryPlannerAgent()
        self.safety_gate = SafetyGateAgent()
        self.executor = DockerSandboxExecutor()
        self.use_llm = settings.llm_configured

    def run(self, request: HealRequest) -> HealResponse:
        request_id = str(uuid.uuid4())
        auto_execute = request.auto_execute if request.auto_execute is not None else settings.auto_execute

        logger.info(
            "pipeline.start",
            request_id=request_id,
            use_llm=self.use_llm,
            auto_execute=auto_execute,
        )

        try:
            if self.use_llm:
                parse_result = self.log_parser.run(request.logs, request.source_hint)
            else:
                parse_result = parse_logs_heuristic(request.logs, request.source_hint)

            if self.use_llm:
                diagnosis = self.diagnostician.run(parse_result)
            else:
                diagnosis = diagnose_heuristic(parse_result)

            if self.use_llm:
                plan = self.recovery_planner.run(diagnosis, parse_result.summary)
            else:
                plan = plan_recovery_heuristic(diagnosis)

            safety = self.safety_gate.run(plan)

            response = HealResponse(
                request_id=request_id,
                stage_reached=PipelineStage.SAFETY,
                parse=parse_result,
                diagnosis=diagnosis,
                plan=plan,
                safety=safety,
            )

            if not safety.sanitized_steps:
                response.stage_reached = PipelineStage.FAILED
                response.message = "No safe recovery steps remain after safety gate"
                return response

            if not auto_execute:
                response.message = "Recovery plan generated; execution skipped (auto_execute=false)"
                return response

            if not safety.approved:
                response.message = "Execution blocked — human approval required: " + "; ".join(safety.reasons)
                return response

            executions = self.executor.execute_plan(
                [(step.order, step.command) for step in safety.sanitized_steps]
            )
            response.executions = executions
            response.stage_reached = PipelineStage.EXECUTE

            if executions and all(r.success for r in executions):
                response.resolved = True
                response.stage_reached = PipelineStage.COMPLETE
                response.message = "Recovery sequence completed successfully in sandbox"
            elif executions:
                response.message = "Recovery sequence failed at step " + str(
                    next(r.step_order for r in executions if not r.success)
                )
            else:
                response.message = "No commands executed"

            return response

        except Exception as exc:
            logger.exception("pipeline.failed", request_id=request_id)
            return HealResponse(
                request_id=request_id,
                stage_reached=PipelineStage.FAILED,
                message=str(exc),
            )
