"""
Utility functions for the Durable Lambda Controller.

This module provides shared utilities for S3 operations, DynamoDB operations,
logging, and common helper functions used across the controller.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import boto3
import structlog
from botocore.exceptions import ClientError

# Configure structured logging
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
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# Initialize AWS clients (lazy loading for better cold start performance)
_s3_client = None
_dynamodb_resource = None
_agentcore_client = None


def get_s3_client():
    """Get or create S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3')
    return _s3_client


def get_dynamodb_resource():
    """Get or create DynamoDB resource."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource('dynamodb')
    return _dynamodb_resource


def get_agentcore_client():
    """Get or create Bedrock AgentCore client."""
    global _agentcore_client
    if _agentcore_client is None:
        _agentcore_client = boto3.client('bedrock-agentcore')
    return _agentcore_client


# Custom exceptions
class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class AgentInvocationError(WorkflowError):
    """Exception raised when agent invocation fails."""
    pass


class ArtifactStorageError(WorkflowError):
    """Exception raised when artifact storage operations fail."""
    pass


class WorkflowStateError(WorkflowError):
    """Exception raised when workflow state operations fail."""
    pass


# S3 Operations
def store_artifact(
    bucket: str,
    key: str,
    content: Any,
    content_type: str = 'application/json',
    workflow_id: Optional[str] = None
) -> Dict[str, str]:
    """
    Store artifact in S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        content: Content to store (will be JSON-serialized if dict/list)
        content_type: Content type for the object
        workflow_id: Optional workflow ID for logging

    Returns:
        Dict with s3_uri and key

    Raises:
        ArtifactStorageError: If storage fails
    """
    log = logger.bind(workflow_id=workflow_id, bucket=bucket, key=key)

    try:
        s3 = get_s3_client()

        # Serialize content if needed
        if isinstance(content, (dict, list)):
            body = json.dumps(content, indent=2)
        elif isinstance(content, str):
            body = content
        else:
            body = str(content)

        # Store in S3
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body.encode('utf-8') if isinstance(body, str) else body,
            ContentType=content_type,
            ServerSideEncryption='AES256'
        )

        s3_uri = f's3://{bucket}/{key}'
        log.info("artifact_stored", s3_uri=s3_uri, size_bytes=len(body))

        return {
            's3_uri': s3_uri,
            'bucket': bucket,
            'key': key
        }

    except ClientError as e:
        log.error("artifact_storage_failed", error=str(e))
        raise ArtifactStorageError(f"Failed to store artifact: {e}") from e


def fetch_artifact(s3_uri: str, workflow_id: Optional[str] = None) -> Any:
    """
    Fetch artifact from S3.

    Args:
        s3_uri: S3 URI (s3://bucket/key)
        workflow_id: Optional workflow ID for logging

    Returns:
        Artifact content (JSON-parsed if applicable)

    Raises:
        ArtifactStorageError: If fetch fails
    """
    log = logger.bind(workflow_id=workflow_id, s3_uri=s3_uri)

    try:
        # Parse S3 URI
        bucket, key = parse_s3_uri(s3_uri)

        s3 = get_s3_client()
        response = s3.get_object(Bucket=bucket, Key=key)

        # Read and decode content
        content = response['Body'].read().decode('utf-8')

        # Try to parse as JSON
        try:
            result = json.loads(content)
            log.info("artifact_fetched", size_bytes=len(content), parsed=True)
            return result
        except json.JSONDecodeError:
            log.info("artifact_fetched", size_bytes=len(content), parsed=False)
            return content

    except ClientError as e:
        log.error("artifact_fetch_failed", error=str(e))
        raise ArtifactStorageError(f"Failed to fetch artifact: {e}") from e


def generate_presigned_url(
    bucket: str,
    key: str,
    expiration: int = 86400,
    workflow_id: Optional[str] = None
) -> str:
    """
    Generate presigned URL for S3 object.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        expiration: URL expiration in seconds (default: 24 hours)
        workflow_id: Optional workflow ID for logging

    Returns:
        Presigned URL

    Raises:
        ArtifactStorageError: If URL generation fails
    """
    log = logger.bind(workflow_id=workflow_id, bucket=bucket, key=key)

    try:
        s3 = get_s3_client()
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )

        log.info("presigned_url_generated", expiration_seconds=expiration)
        return url

    except ClientError as e:
        log.error("presigned_url_generation_failed", error=str(e))
        raise ArtifactStorageError(f"Failed to generate presigned URL: {e}") from e


def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Parse S3 URI into bucket and key.

    Args:
        s3_uri: S3 URI (s3://bucket/key)

    Returns:
        Tuple of (bucket, key)

    Raises:
        ValueError: If URI is invalid
    """
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")

    parts = s3_uri.replace('s3://', '').split('/', 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URI format: {s3_uri}")

    return parts[0], parts[1]


# DynamoDB Operations
def create_workflow_record(
    table_name: str,
    workflow_id: str,
    topic: str,
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create initial workflow record in DynamoDB.

    Args:
        table_name: DynamoDB table name
        workflow_id: Unique workflow identifier
        topic: Research topic
        parameters: Workflow parameters

    Returns:
        Created workflow item

    Raises:
        WorkflowStateError: If record creation fails
    """
    log = logger.bind(workflow_id=workflow_id, table_name=table_name)

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)

        now = datetime.now(timezone.utc).isoformat()

        item = {
            'workflow_id': workflow_id,
            'topic': topic,
            'parameters': parameters,
            'status': 'INITIALIZING',
            'created_at': now,
            'updated_at': now,
            'steps_completed': [],
            'current_step': 'initialization'
        }

        table.put_item(Item=item)
        log.info("workflow_record_created", status=item['status'])

        return item

    except ClientError as e:
        log.error("workflow_record_creation_failed", error=str(e))
        raise WorkflowStateError(f"Failed to create workflow record: {e}") from e


def update_workflow_status(
    table_name: str,
    workflow_id: str,
    status: str,
    current_step: Optional[str] = None,
    additional_fields: Optional[Dict[str, Any]] = None
) -> None:
    """
    Update workflow status in DynamoDB.

    Args:
        table_name: DynamoDB table name
        workflow_id: Workflow identifier
        status: New status
        current_step: Current step name
        additional_fields: Additional fields to update

    Raises:
        WorkflowStateError: If update fails
    """
    log = logger.bind(workflow_id=workflow_id, table_name=table_name, status=status)

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)

        now = datetime.now(timezone.utc).isoformat()

        # Build update expression
        update_expr = 'SET #status = :status, updated_at = :updated'
        expr_names = {'#status': 'status'}
        expr_values = {
            ':status': status,
            ':updated': now
        }

        if current_step:
            update_expr += ', current_step = :step'
            expr_values[':step'] = current_step

        # Add additional fields
        if additional_fields:
            for field, value in additional_fields.items():
                placeholder = f':field_{field}'
                update_expr += f', {field} = {placeholder}'
                expr_values[placeholder] = value

        table.update_item(
            Key={'workflow_id': workflow_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )

        log.info("workflow_status_updated", current_step=current_step)

    except ClientError as e:
        log.error("workflow_status_update_failed", error=str(e))
        raise WorkflowStateError(f"Failed to update workflow status: {e}") from e


def record_step_completion(
    table_name: str,
    workflow_id: str,
    step_name: str,
    result: Optional[Dict[str, Any]] = None
) -> None:
    """
    Record completion of a workflow step.

    Args:
        table_name: DynamoDB table name
        workflow_id: Workflow identifier
        step_name: Name of completed step
        result: Optional step result metadata

    Raises:
        WorkflowStateError: If recording fails
    """
    log = logger.bind(workflow_id=workflow_id, step_name=step_name)

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)

        now = datetime.now(timezone.utc).isoformat()

        step_record = {
            'step_name': step_name,
            'completed_at': now
        }

        if result:
            step_record['result_summary'] = result

        table.update_item(
            Key={'workflow_id': workflow_id},
            UpdateExpression='SET steps_completed = list_append(if_not_exists(steps_completed, :empty_list), :step), updated_at = :updated',
            ExpressionAttributeValues={
                ':step': [step_record],
                ':updated': now,
                ':empty_list': []
            }
        )

        log.info("step_completion_recorded")

    except ClientError as e:
        log.error("step_completion_recording_failed", error=str(e))
        raise WorkflowStateError(f"Failed to record step completion: {e}") from e


def get_workflow_state(table_name: str, workflow_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve workflow state from DynamoDB.

    Args:
        table_name: DynamoDB table name
        workflow_id: Workflow identifier

    Returns:
        Workflow item or None if not found

    Raises:
        WorkflowStateError: If retrieval fails
    """
    log = logger.bind(workflow_id=workflow_id, table_name=table_name)

    try:
        dynamodb = get_dynamodb_resource()
        table = dynamodb.Table(table_name)

        response = table.get_item(Key={'workflow_id': workflow_id})
        item = response.get('Item')

        if item:
            log.info("workflow_state_retrieved", status=item.get('status'))
        else:
            log.warning("workflow_not_found")

        return item

    except ClientError as e:
        log.error("workflow_state_retrieval_failed", error=str(e))
        raise WorkflowStateError(f"Failed to retrieve workflow state: {e}") from e


# Utility functions
def generate_workflow_id() -> str:
    """Generate unique workflow ID."""
    return str(uuid.uuid4())


def generate_callback_token() -> str:
    """Generate secure callback token."""
    return str(uuid.uuid4())


def is_large_payload(payload: Any, threshold: int = 200000) -> bool:
    """
    Check if payload exceeds size threshold.

    Args:
        payload: Payload to check
        threshold: Size threshold in bytes (default: ~200KB)

    Returns:
        True if payload is large
    """
    if isinstance(payload, (dict, list)):
        serialized = json.dumps(payload)
    elif isinstance(payload, str):
        serialized = payload
    else:
        serialized = str(payload)

    return len(serialized) > threshold


def sanitize_error(error: Exception) -> Dict[str, str]:
    """
    Sanitize error for logging and storage.

    Args:
        error: Exception to sanitize

    Returns:
        Dict with error details
    """
    return {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'error_module': error.__class__.__module__
    }


def validate_workflow_parameters(parameters: Dict[str, Any]) -> None:
    """
    Validate workflow parameters.

    Args:
        parameters: Parameters to validate

    Raises:
        ValueError: If parameters are invalid
    """
    # Add validation logic as needed
    if not isinstance(parameters, dict):
        raise ValueError("Parameters must be a dictionary")

    # Add more specific validations based on your requirements
    pass


def format_agent_payload(
    task: str,
    data: Any,
    workflow_id: str,
    callback_url: Optional[str] = None,
    callback_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format payload for agent invocation.

    Args:
        task: Task type
        data: Task data
        workflow_id: Workflow identifier
        callback_url: Optional callback URL for async execution
        callback_token: Optional callback token

    Returns:
        Formatted payload
    """
    payload = {
        'task': task,
        'data': data,
        'workflow_id': workflow_id,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

    if callback_url:
        payload['callback_url'] = callback_url
        payload['callback_token'] = callback_token

    return payload
