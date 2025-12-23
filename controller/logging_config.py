"""
Structured Logging Configuration for Controller Lambda

Provides consistent JSON logging format for CloudWatch Logs Insights queries.
"""

import os
import json
import logging
from datetime import datetime
from typing import Any, Optional
from functools import wraps
import time

# Try to import structlog, fall back to standard logging
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


def configure_logging(service_name: str = "controller") -> logging.Logger:
    """
    Configure structured JSON logging for Lambda functions.

    Args:
        service_name: Name of the service for log correlation

    Returns:
        Configured logger instance
    """
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    if STRUCTLOG_AVAILABLE:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        logger = structlog.get_logger(service_name)
    else:
        # Fallback to standard logging with JSON formatter
        logger = logging.getLogger(service_name)
        logger.setLevel(getattr(logging, log_level))

        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            logger.addHandler(handler)

    return logger


class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for CloudWatch Logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "workflow_id"):
            log_entry["workflow_id"] = record.workflow_id
        if hasattr(record, "step_name"):
            log_entry["step_name"] = record.step_name
        if hasattr(record, "agent_type"):
            log_entry["agent_type"] = record.agent_type
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "error"):
            log_entry["error"] = record.error

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class WorkflowLogger:
    """
    Context-aware logger for workflow operations.

    Automatically includes workflow_id in all log entries.
    """

    def __init__(self, logger: logging.Logger, workflow_id: str):
        self.logger = logger
        self.workflow_id = workflow_id

    def _log(self, level: str, message: str, **kwargs):
        """Internal logging method with workflow context."""
        extra = {"workflow_id": self.workflow_id, **kwargs}
        getattr(self.logger, level)(message, extra=extra)

    def info(self, message: str, **kwargs):
        self._log("info", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log("error", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log("warning", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._log("debug", message, **kwargs)

    def step_start(self, step_name: str):
        """Log the start of a workflow step."""
        self.info(f"Starting step: {step_name}", step_name=step_name, event="step_start")

    def step_complete(self, step_name: str, duration_ms: float):
        """Log successful completion of a workflow step."""
        self.info(
            f"Completed step: {step_name}",
            step_name=step_name,
            duration_ms=duration_ms,
            event="step_complete"
        )

    def step_failed(self, step_name: str, error: str):
        """Log failure of a workflow step."""
        self.error(
            f"Step failed: {step_name}",
            step_name=step_name,
            error=error,
            event="step_failed"
        )

    def agent_invoke(self, agent_type: str, agent_arn: str):
        """Log agent invocation."""
        self.info(
            f"Invoking agent: {agent_type}",
            agent_type=agent_type,
            agent_arn=agent_arn,
            event="agent_invoke"
        )

    def agent_callback(self, agent_type: str, status: str, duration_ms: Optional[float] = None):
        """Log agent callback received."""
        self.info(
            f"Agent callback: {agent_type} - {status}",
            agent_type=agent_type,
            status=status,
            duration_ms=duration_ms,
            event="agent_callback"
        )


def log_execution_time(logger: logging.Logger):
    """
    Decorator to log function execution time.

    Usage:
        @log_execution_time(logger)
        def my_function():
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.info(
                    f"Function {func.__name__} completed",
                    extra={
                        "function": func.__name__,
                        "duration_ms": duration_ms,
                        "event": "function_complete"
                    }
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(
                    f"Function {func.__name__} failed: {str(e)}",
                    extra={
                        "function": func.__name__,
                        "duration_ms": duration_ms,
                        "error": str(e),
                        "event": "function_failed"
                    }
                )
                raise
        return wrapper
    return decorator


# Pre-defined log event types for consistency
class LogEvents:
    """Standard log event types for the orchestration platform."""

    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"

    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    STEP_FAILED = "step_failed"
    STEP_SKIPPED = "step_skipped"

    AGENT_INVOKE = "agent_invoke"
    AGENT_CALLBACK = "agent_callback"
    AGENT_TIMEOUT = "agent_timeout"
    AGENT_ERROR = "agent_error"

    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RECEIVED = "approval_received"
    APPROVAL_TIMEOUT = "approval_timeout"

    ARTIFACT_STORED = "artifact_stored"
    ARTIFACT_RETRIEVED = "artifact_retrieved"

    CALLBACK_RECEIVED = "callback_received"
    CALLBACK_PROCESSED = "callback_processed"
    CALLBACK_FAILED = "callback_failed"


def emit_metric(
    metric_name: str,
    value: float,
    unit: str = "Count",
    dimensions: Optional[dict] = None
):
    """
    Emit a custom CloudWatch metric via structured log (EMF format).

    CloudWatch Logs will automatically extract metrics from logs
    in Embedded Metric Format.

    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: CloudWatch unit (Count, Milliseconds, etc.)
        dimensions: Optional dimension key-value pairs
    """
    metric_log = {
        "_aws": {
            "Timestamp": int(datetime.utcnow().timestamp() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": "AgentOrchestration",
                    "Dimensions": [list(dimensions.keys())] if dimensions else [[]],
                    "Metrics": [
                        {
                            "Name": metric_name,
                            "Unit": unit
                        }
                    ]
                }
            ]
        },
        metric_name: value
    }

    if dimensions:
        metric_log.update(dimensions)

    print(json.dumps(metric_log))
