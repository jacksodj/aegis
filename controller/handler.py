"""
Durable Lambda Controller for Serverless Agent Orchestration.

This module implements the main orchestration workflow for multi-agent research
report generation using a durable execution pattern with AWS Lambda.

Workflow Steps:
1. Initialize workflow metadata
2. Invoke Researcher agent (async with callback)
3. Invoke Analyst agent with research results
4. Wait for human approval
5. Invoke Writer agent to produce final report
6. Store and return results
"""

import json
import os
from datetime import datetime, timezone, timedelta
from functools import wraps
from typing import Any, Callable, Dict, Optional

import boto3
import structlog
from botocore.exceptions import ClientError

from .utils import (
    create_workflow_record,
    fetch_artifact,
    format_agent_payload,
    generate_callback_token,
    generate_presigned_url,
    generate_workflow_id,
    get_agentcore_client,
    get_s3_client,
    is_large_payload,
    record_step_completion,
    sanitize_error,
    store_artifact,
    update_workflow_status,
    AgentInvocationError,
    ArtifactStorageError,
    WorkflowError,
    WorkflowStateError,
)

# Configure structured logging
logger = structlog.get_logger(__name__)

# Environment variables
ARTIFACT_BUCKET = os.environ.get('ARTIFACT_BUCKET', '')
WORKFLOW_TABLE = os.environ.get('WORKFLOW_TABLE', '')
RESEARCHER_AGENT_ARN = os.environ.get('RESEARCHER_AGENT_ARN', '')
ANALYST_AGENT_ARN = os.environ.get('ANALYST_AGENT_ARN', '')
WRITER_AGENT_ARN = os.environ.get('WRITER_AGENT_ARN', '')
CALLBACK_API_URL = os.environ.get('CALLBACK_API_URL', '')
APPROVAL_TIMEOUT_HOURS = int(os.environ.get('APPROVAL_TIMEOUT_HOURS', '24'))

# Initialize clients
sns = boto3.client('sns')
events = boto3.client('events')


# ============================================================================
# Durable Execution Decorator Pattern
# ============================================================================
# Since the actual AWS Durable Execution SDK may not be available, we implement
# a custom decorator pattern that simulates the durable execution behavior.
# In production, replace this with the actual SDK:
# from aws_durable_execution_sdk_python import durable_execution, DurableContext
# ============================================================================

class DurableContext:
    """
    Simulated Durable Context for workflow execution.

    In production, this would be provided by the AWS Durable Execution SDK.
    This implementation provides a compatible interface for development.
    """

    def __init__(self, workflow_id: str, event: Dict[str, Any], context: Any):
        self.workflow_id = workflow_id
        self.event = event
        self.lambda_context = context
        self.steps_executed = []
        self.callback_tokens = {}

    def step(self, func: Callable, name: str) -> Any:
        """
        Execute a checkpoint step.

        In production durable execution, this creates a checkpoint after
        the function completes, allowing workflow resume from this point.

        Args:
            func: Function to execute
            name: Step name for checkpoint

        Returns:
            Result of function execution
        """
        log = logger.bind(workflow_id=self.workflow_id, step_name=name)

        try:
            log.info("step_starting")
            result = func()

            # Record step completion
            self.steps_executed.append({
                'name': name,
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'status': 'SUCCESS'
            })

            log.info("step_completed", result_type=type(result).__name__)
            return result

        except Exception as e:
            log.error("step_failed", error=str(e))
            self.steps_executed.append({
                'name': name,
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'status': 'FAILED',
                'error': sanitize_error(e)
            })
            raise

    def wait_for_callback(self, name: str, timeout_hours: int = 24) -> Dict[str, Any]:
        """
        Wait for external callback (simulated).

        In production durable execution, this suspends the workflow with zero
        compute cost until a callback is received via the Lambda API.

        For this implementation, we return a callback configuration that
        the caller can use to resume the workflow.

        Args:
            name: Callback name
            timeout_hours: Timeout in hours

        Returns:
            Callback result (or configuration for async pattern)
        """
        log = logger.bind(workflow_id=self.workflow_id, callback_name=name)

        # Generate callback token
        token = generate_callback_token()
        self.callback_tokens[name] = {
            'token': token,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'timeout_hours': timeout_hours
        }

        log.info("callback_registered", token=token, timeout_hours=timeout_hours)

        # In production, this would suspend. For now, check if callback is in event
        if self.event.get('callback_name') == name and self.event.get('callback_token') == token:
            log.info("callback_received")
            return self.event.get('callback_result', {})

        # Return callback configuration for async workflow
        return {
            '_callback_pending': True,
            'callback_name': name,
            'callback_token': token,
            'callback_url': f"{CALLBACK_API_URL}/callbacks/{self.workflow_id}"
        }

    def get_callback_config(self, name: str = 'default') -> Dict[str, str]:
        """
        Get callback configuration for external systems.

        Args:
            name: Callback identifier

        Returns:
            Callback configuration with URL and token
        """
        token = generate_callback_token()
        self.callback_tokens[name] = {
            'token': token,
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        return {
            'url': f"{CALLBACK_API_URL}/callbacks/{self.workflow_id}",
            'token': token,
            'workflow_id': self.workflow_id
        }


def durable_execution(func: Callable) -> Callable:
    """
    Decorator for durable execution (simulated pattern).

    In production, this would be:
    from aws_durable_execution_sdk_python import durable_execution

    This decorator wraps the handler to provide durable execution context.

    Args:
        func: Handler function to decorate

    Returns:
        Decorated function
    """
    @wraps(func)
    def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        # Extract or generate workflow ID
        workflow_id = event.get('workflow_id', generate_workflow_id())

        log = logger.bind(workflow_id=workflow_id)
        log.info("durable_workflow_starting", event_keys=list(event.keys()))

        try:
            # Create durable context
            durable_ctx = DurableContext(workflow_id, event, context)

            # Execute workflow
            result = func(event, durable_ctx)

            log.info("durable_workflow_completed", steps_executed=len(durable_ctx.steps_executed))
            return result

        except Exception as e:
            log.error("durable_workflow_failed", error=str(e))
            raise

    return wrapper


# ============================================================================
# Main Workflow Handler
# ============================================================================

@durable_execution
def handler(event: Dict[str, Any], context: DurableContext) -> Dict[str, Any]:
    """
    Main orchestration workflow for research report generation.

    This handler coordinates a multi-agent workflow with the following steps:
    1. Initialize workflow record
    2. Research phase (Researcher agent)
    3. Analysis phase (Analyst agent)
    4. Human approval gate
    5. Writing phase (Writer agent)
    6. Finalize and return results

    Args:
        event: Lambda event with 'topic' and optional 'parameters', 'workflow_id'
        context: Durable execution context

    Returns:
        Dict with workflow status and results

    Raises:
        WorkflowError: If workflow fails
    """
    workflow_id = context.workflow_id
    log = logger.bind(workflow_id=workflow_id)

    # Extract workflow parameters
    topic = event.get('topic')
    if not topic:
        raise ValueError("Missing required field: 'topic'")

    parameters = event.get('parameters', {})

    log.info("workflow_starting", topic=topic, parameters=parameters)

    try:
        # Step 1: Initialize workflow
        context.step(
            lambda: init_workflow(workflow_id, topic, parameters),
            name='init_workflow'
        )

        # Step 2: Research phase
        research_results = invoke_agent_with_callback(
            context=context,
            step_name='research_phase',
            agent_arn=RESEARCHER_AGENT_ARN,
            payload={
                'topic': topic,
                'parameters': parameters
            },
            timeout_hours=4
        )

        # Check for callback pending
        if isinstance(research_results, dict) and research_results.get('_callback_pending'):
            log.info("workflow_suspended_for_callback", step='research_phase')
            return {
                'status': 'PENDING',
                'workflow_id': workflow_id,
                'awaiting': 'research_completion',
                'message': 'Workflow suspended awaiting research completion'
            }

        # Step 3: Analysis phase
        analysis_results = invoke_agent_with_callback(
            context=context,
            step_name='analysis_phase',
            agent_arn=ANALYST_AGENT_ARN,
            payload={
                'research_data': research_results,
                'topic': topic
            },
            timeout_hours=2
        )

        # Check for callback pending
        if isinstance(analysis_results, dict) and analysis_results.get('_callback_pending'):
            log.info("workflow_suspended_for_callback", step='analysis_phase')
            return {
                'status': 'PENDING',
                'workflow_id': workflow_id,
                'awaiting': 'analysis_completion',
                'message': 'Workflow suspended awaiting analysis completion'
            }

        # Step 4: Request human approval
        context.step(
            lambda: request_approval(workflow_id, analysis_results),
            name='request_approval'
        )

        # Wait for approval callback
        approval = context.wait_for_callback(
            name='human_approval',
            timeout_hours=APPROVAL_TIMEOUT_HOURS
        )

        # Check for callback pending
        if isinstance(approval, dict) and approval.get('_callback_pending'):
            log.info("workflow_suspended_for_callback", step='human_approval')
            return {
                'status': 'AWAITING_APPROVAL',
                'workflow_id': workflow_id,
                'callback_url': approval.get('callback_url'),
                'message': 'Workflow suspended awaiting human approval'
            }

        # Check approval decision
        if not approval.get('approved', False):
            context.step(
                lambda: update_workflow_status(
                    WORKFLOW_TABLE,
                    workflow_id,
                    'REJECTED',
                    current_step='completed',
                    additional_fields={'rejection_reason': approval.get('reason', '')}
                ),
                name='mark_rejected'
            )
            return {
                'status': 'REJECTED',
                'workflow_id': workflow_id,
                'reason': approval.get('reason', 'No reason provided')
            }

        # Step 5: Writing phase
        report = invoke_agent_with_callback(
            context=context,
            step_name='writing_phase',
            agent_arn=WRITER_AGENT_ARN,
            payload={
                'analysis': analysis_results,
                'feedback': approval.get('feedback', ''),
                'topic': topic,
                'parameters': parameters
            },
            timeout_hours=1
        )

        # Check for callback pending
        if isinstance(report, dict) and report.get('_callback_pending'):
            log.info("workflow_suspended_for_callback", step='writing_phase')
            return {
                'status': 'PENDING',
                'workflow_id': workflow_id,
                'awaiting': 'report_generation',
                'message': 'Workflow suspended awaiting report generation'
            }

        # Step 6: Finalize workflow
        result = context.step(
            lambda: finalize_workflow(workflow_id, report),
            name='finalize_workflow'
        )

        log.info("workflow_completed_successfully")

        return {
            'status': 'COMPLETED',
            'workflow_id': workflow_id,
            'report_url': result['presigned_url'],
            'completed_at': datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        log.error("workflow_failed", error=str(e))

        # Update workflow status to failed
        try:
            update_workflow_status(
                WORKFLOW_TABLE,
                workflow_id,
                'FAILED',
                current_step='error',
                additional_fields={'error': sanitize_error(e)}
            )
        except Exception as update_error:
            log.error("failed_to_update_error_status", error=str(update_error))

        raise WorkflowError(f"Workflow failed: {e}") from e


# ============================================================================
# Workflow Step Functions
# ============================================================================

def init_workflow(workflow_id: str, topic: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize workflow record in DynamoDB.

    Args:
        workflow_id: Unique workflow identifier
        topic: Research topic
        parameters: Workflow parameters

    Returns:
        Created workflow record

    Raises:
        WorkflowStateError: If initialization fails
    """
    log = logger.bind(workflow_id=workflow_id)
    log.info("initializing_workflow", topic=topic)

    try:
        item = create_workflow_record(WORKFLOW_TABLE, workflow_id, topic, parameters)

        # Update status to running
        update_workflow_status(
            WORKFLOW_TABLE,
            workflow_id,
            'RUNNING',
            current_step='research_phase'
        )

        log.info("workflow_initialized")
        return item

    except Exception as e:
        log.error("workflow_initialization_failed", error=str(e))
        raise


def invoke_agent_with_callback(
    context: DurableContext,
    step_name: str,
    agent_arn: str,
    payload: Dict[str, Any],
    timeout_hours: int
) -> Dict[str, Any]:
    """
    Invoke an AgentCore agent using the async callback pattern.

    This handles the timeout mismatch between Lambda (15min) and AgentCore (8hr)
    by using wait_for_callback() to suspend until the agent completes.

    Args:
        context: Durable execution context
        step_name: Name of the workflow step
        agent_arn: AgentCore agent ARN
        payload: Task payload for the agent
        timeout_hours: Timeout in hours for agent execution

    Returns:
        Agent result (or callback pending indicator)

    Raises:
        AgentInvocationError: If agent invocation fails
    """
    log = logger.bind(
        workflow_id=context.workflow_id,
        step_name=step_name,
        agent_arn=agent_arn
    )

    # Get callback configuration
    callback_config = context.get_callback_config(name=f'{step_name}_callback')

    # Dispatch task to agent
    context.step(
        lambda: dispatch_agent_task(
            agent_arn=agent_arn,
            payload={
                **payload,
                'workflow_id': context.workflow_id,
                'callback_url': callback_config['url'],
                'callback_token': callback_config['token']
            }
        ),
        name=f'{step_name}_dispatch'
    )

    # Wait for agent to complete and callback
    result = context.wait_for_callback(
        name=f'{step_name}_await',
        timeout_hours=timeout_hours
    )

    # Check for callback pending
    if isinstance(result, dict) and result.get('_callback_pending'):
        return result

    # If result is an S3 reference, fetch the actual data
    if isinstance(result, dict) and result.get('artifact_type') == 's3_reference':
        result = context.step(
            lambda: fetch_artifact(result['s3_uri'], workflow_id=context.workflow_id),
            name=f'{step_name}_fetch_artifact'
        )

    # Record step completion
    record_step_completion(
        WORKFLOW_TABLE,
        context.workflow_id,
        step_name,
        {'status': 'completed', 'has_result': bool(result)}
    )

    return result


def request_approval(workflow_id: str, analysis_results: Dict[str, Any]) -> Dict[str, str]:
    """
    Request human approval for the workflow.

    This sends a notification (via SNS, email, or other channel) to request
    approval before proceeding to the writing phase.

    Args:
        workflow_id: Workflow identifier
        analysis_results: Analysis results to include in approval request

    Returns:
        Approval request metadata

    Raises:
        WorkflowError: If approval request fails
    """
    log = logger.bind(workflow_id=workflow_id)
    log.info("requesting_approval")

    try:
        # Update workflow status
        update_workflow_status(
            WORKFLOW_TABLE,
            workflow_id,
            'AWAITING_APPROVAL',
            current_step='human_approval'
        )

        # Store analysis results for approval review
        if is_large_payload(analysis_results):
            artifact = store_artifact(
                bucket=ARTIFACT_BUCKET,
                key=f'approvals/{workflow_id}/analysis_results.json',
                content=analysis_results,
                workflow_id=workflow_id
            )
            review_url = generate_presigned_url(
                bucket=ARTIFACT_BUCKET,
                key=artifact['key'],
                expiration=86400,  # 24 hours
                workflow_id=workflow_id
            )
        else:
            # For smaller results, could embed in notification
            review_url = None

        # Send approval notification
        # In production, this could use SNS, SES, Slack, etc.
        approval_message = {
            'workflow_id': workflow_id,
            'status': 'approval_required',
            'analysis_summary': analysis_results.get('summary', 'No summary available'),
            'review_url': review_url,
            'callback_url': f"{CALLBACK_API_URL}/approve/{workflow_id}",
            'requested_at': datetime.now(timezone.utc).isoformat()
        }

        # Example: Send via SNS (if SNS topic ARN is configured)
        sns_topic_arn = os.environ.get('APPROVAL_SNS_TOPIC_ARN')
        if sns_topic_arn:
            sns.publish(
                TopicArn=sns_topic_arn,
                Subject=f'Approval Required: Workflow {workflow_id}',
                Message=json.dumps(approval_message, indent=2)
            )
            log.info("approval_notification_sent", channel='sns')
        else:
            log.warning("no_approval_notification_channel_configured")

        # Emit EventBridge event for custom integrations
        events.put_events(
            Entries=[{
                'Source': 'agent.orchestration',
                'DetailType': 'ApprovalRequested',
                'Detail': json.dumps(approval_message),
                'Resources': [workflow_id]
            }]
        )

        log.info("approval_requested")
        return approval_message

    except Exception as e:
        log.error("approval_request_failed", error=str(e))
        raise WorkflowError(f"Failed to request approval: {e}") from e


def finalize_workflow(workflow_id: str, report: Dict[str, Any]) -> Dict[str, str]:
    """
    Finalize workflow and store results.

    Args:
        workflow_id: Workflow identifier
        report: Final report from Writer agent

    Returns:
        Finalization metadata with presigned URL

    Raises:
        ArtifactStorageError: If storage fails
    """
    log = logger.bind(workflow_id=workflow_id)
    log.info("finalizing_workflow")

    try:
        # Store final report
        key = f'reports/{workflow_id}/final_report.json'
        store_artifact(
            bucket=ARTIFACT_BUCKET,
            key=key,
            content=report,
            content_type='application/json',
            workflow_id=workflow_id
        )

        # Generate presigned URL for report access
        presigned_url = generate_presigned_url(
            bucket=ARTIFACT_BUCKET,
            key=key,
            expiration=604800,  # 7 days
            workflow_id=workflow_id
        )

        # Update workflow status to completed
        update_workflow_status(
            WORKFLOW_TABLE,
            workflow_id,
            'COMPLETED',
            current_step='completed',
            additional_fields={
                'report_url': presigned_url,
                'report_s3_key': key,
                'completed_at': datetime.now(timezone.utc).isoformat()
            }
        )

        # Emit completion event
        events.put_events(
            Entries=[{
                'Source': 'agent.orchestration',
                'DetailType': 'WorkflowCompleted',
                'Detail': json.dumps({
                    'workflow_id': workflow_id,
                    'report_url': presigned_url,
                    'completed_at': datetime.now(timezone.utc).isoformat()
                }),
                'Resources': [workflow_id]
            }]
        )

        log.info("workflow_finalized", report_url=presigned_url)

        return {
            'presigned_url': presigned_url,
            's3_key': key,
            'bucket': ARTIFACT_BUCKET
        }

    except Exception as e:
        log.error("workflow_finalization_failed", error=str(e))
        raise


# ============================================================================
# Helper Functions
# ============================================================================

def dispatch_agent_task(agent_arn: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send task to AgentCore agent via A2A protocol.

    Args:
        agent_arn: AgentCore agent runtime ARN
        payload: Task payload

    Returns:
        Agent response

    Raises:
        AgentInvocationError: If invocation fails
    """
    log = logger.bind(agent_arn=agent_arn, workflow_id=payload.get('workflow_id'))
    log.info("dispatching_agent_task", task=payload.get('task'))

    try:
        agentcore = get_agentcore_client()

        # Format A2A JSON-RPC request
        request_id = generate_workflow_id()
        a2a_request = {
            'jsonrpc': '2.0',
            'id': request_id,
            'method': 'tasks/send',
            'params': {
                'message': {
                    'role': 'user',
                    'parts': [
                        {
                            'kind': 'text',
                            'text': json.dumps(payload)
                        }
                    ]
                }
            }
        }

        # Invoke agent
        response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(a2a_request).encode('utf-8')
        )

        # Parse response
        response_body = json.loads(response['body'].read().decode('utf-8'))

        log.info("agent_task_dispatched", request_id=request_id, response_status=response_body.get('status'))

        return response_body

    except ClientError as e:
        log.error("agent_invocation_failed", error=str(e))
        raise AgentInvocationError(f"Failed to invoke agent: {e}") from e
    except Exception as e:
        log.error("agent_dispatch_error", error=str(e))
        raise AgentInvocationError(f"Agent dispatch error: {e}") from e


def fetch_s3_artifact(s3_uri: str, workflow_id: str) -> Dict[str, Any]:
    """
    Fetch artifact from S3 (wrapper for compatibility).

    Args:
        s3_uri: S3 URI
        workflow_id: Workflow identifier

    Returns:
        Artifact content
    """
    return fetch_artifact(s3_uri, workflow_id)


def store_s3_artifact(key: str, content: Any, workflow_id: str) -> Dict[str, str]:
    """
    Store artifact to S3 (wrapper for compatibility).

    Args:
        key: S3 object key
        content: Content to store
        workflow_id: Workflow identifier

    Returns:
        Storage metadata
    """
    return store_artifact(
        bucket=ARTIFACT_BUCKET,
        key=key,
        content=content,
        workflow_id=workflow_id
    )


# ============================================================================
# Entry Point for API Gateway
# ============================================================================

def api_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    API Gateway handler wrapper.

    This provides a REST API compatible wrapper around the durable handler.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    log = logger.bind(request_id=context.request_id if hasattr(context, 'request_id') else 'unknown')

    try:
        # Parse request
        http_method = event.get('httpMethod', 'POST')
        path = event.get('path', '/')

        if http_method == 'POST' and path.startswith('/workflows'):
            # Start new workflow
            body = json.loads(event.get('body', '{}'))

            result = handler(body, context)

            return {
                'statusCode': 200 if result.get('status') != 'FAILED' else 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(result)
            }

        elif http_method == 'GET' and '/workflows/' in path:
            # Get workflow status
            workflow_id = path.split('/')[-1]
            from .utils import get_workflow_state

            state = get_workflow_state(WORKFLOW_TABLE, workflow_id)

            if state:
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps(state)
                }
            else:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': 'Workflow not found'})
                }

        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Not found'})
            }

    except Exception as e:
        log.error("api_handler_error", error=str(e))
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
