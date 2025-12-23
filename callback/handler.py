"""
Callback Handler Lambda for Serverless Durable Agent Orchestration

This handler receives callbacks from AgentCore agents and processes them:
- Stores callback results in DynamoDB
- Updates workflow status based on agent execution outcome
- Provides structured logging for observability
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Environment variables
WORKFLOW_TABLE = os.environ['WORKFLOW_TABLE']
ARTIFACT_BUCKET = os.environ['ARTIFACT_BUCKET']

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def log_event(event_type: str, **kwargs):
    """
    Structured logging helper for consistent log format.

    Args:
        event_type: Type of event being logged
        **kwargs: Additional context fields
    """
    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        **kwargs
    }
    logger.info(json.dumps(log_entry))


def parse_request_body(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse and validate the incoming request body.

    Args:
        event: Lambda event object

    Returns:
        Parsed body as dict, or None if parsing fails
    """
    try:
        body = event.get('body', '{}')
        if isinstance(body, str):
            return json.loads(body)
        return body
    except json.JSONDecodeError as e:
        log_event('parse_error', error=str(e), body=event.get('body', '')[:200])
        return None


def validate_callback_payload(body: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Validate required fields in the callback payload.

    Args:
        body: Parsed request body

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not body:
        return False, "Request body is empty or invalid JSON"

    if 'token' not in body or not body['token']:
        return False, "Missing required field: token"

    if 'status' not in body:
        return False, "Missing required field: status"

    status = body['status']
    if status not in ['SUCCESS', 'FAILURE']:
        return False, f"Invalid status value: {status}. Must be SUCCESS or FAILURE"

    # Validate status-specific requirements
    if status == 'SUCCESS' and 'result' not in body:
        return False, "SUCCESS status requires 'result' field"

    if status == 'FAILURE' and 'error' not in body:
        return False, "FAILURE status requires 'error' field"

    return True, None


def store_callback_result(token: str, status: str, result: Optional[Dict] = None,
                         error: Optional[str] = None) -> bool:
    """
    Store callback result in DynamoDB keyed by token.

    Args:
        token: Unique callback token
        status: Callback status (SUCCESS or FAILURE)
        result: Result data for successful callbacks
        error: Error message for failed callbacks

    Returns:
        True if stored successfully, False otherwise
    """
    try:
        table = dynamodb.Table(WORKFLOW_TABLE)

        item = {
            'callback_token': token,
            'status': status,
            'timestamp': datetime.utcnow().isoformat(),
            'ttl': int(datetime.utcnow().timestamp()) + 86400 * 14  # 14 days TTL
        }

        if status == 'SUCCESS':
            # Store result, handling large payloads
            result_str = json.dumps(result) if result else '{}'

            # If result is large (>256KB), store in S3
            if len(result_str) > 256000:
                s3_key = f'callbacks/{token}/result.json'
                s3_client.put_object(
                    Bucket=ARTIFACT_BUCKET,
                    Key=s3_key,
                    Body=result_str,
                    ContentType='application/json'
                )
                item['result_location'] = f's3://{ARTIFACT_BUCKET}/{s3_key}'
                log_event('result_stored_s3', token=token, s3_key=s3_key,
                         size=len(result_str))
            else:
                item['result'] = result
        else:
            item['error'] = error

        table.put_item(Item=item)

        log_event('callback_stored', token=token, status=status)
        return True

    except ClientError as e:
        log_event('storage_error',
                 token=token,
                 error=str(e),
                 error_code=e.response.get('Error', {}).get('Code'))
        return False
    except Exception as e:
        log_event('storage_error', token=token, error=str(e), error_type=type(e).__name__)
        return False


def update_workflow_status(token: str, status: str) -> bool:
    """
    Update workflow status based on callback result.

    This function attempts to find and update the workflow associated with
    the callback token.

    Args:
        token: Callback token
        status: New status to set

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        table = dynamodb.Table(WORKFLOW_TABLE)

        # Query for workflow by callback token
        # Note: This assumes the workflow record stores callback_token
        # In practice, you might need to use a GSI or different query strategy
        response = table.scan(
            FilterExpression='callback_token = :token',
            ExpressionAttributeValues={':token': token},
            Limit=1
        )

        if not response.get('Items'):
            log_event('workflow_not_found', token=token)
            # Not necessarily an error - token might be for intermediate step
            return True

        workflow = response['Items'][0]
        workflow_id = workflow.get('workflow_id')

        if not workflow_id:
            log_event('workflow_id_missing', token=token)
            return False

        # Update workflow status
        new_status = 'COMPLETED' if status == 'SUCCESS' else 'FAILED'

        table.update_item(
            Key={'workflow_id': workflow_id},
            UpdateExpression='SET #status = :status, updated_at = :updated',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': new_status,
                ':updated': datetime.utcnow().isoformat()
            }
        )

        log_event('workflow_updated',
                 workflow_id=workflow_id,
                 token=token,
                 new_status=new_status)
        return True

    except ClientError as e:
        log_event('workflow_update_error',
                 token=token,
                 error=str(e),
                 error_code=e.response.get('Error', {}).get('Code'))
        return False
    except Exception as e:
        log_event('workflow_update_error',
                 token=token,
                 error=str(e),
                 error_type=type(e).__name__)
        return False


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a formatted API Gateway response.

    Args:
        status_code: HTTP status code
        body: Response body dict

    Returns:
        Formatted API Gateway response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'  # Adjust for production
        },
        'body': json.dumps(body)
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for agent callbacks.

    Receives callbacks from AgentCore agents and processes them:
    1. Validates the callback payload
    2. Stores callback results in DynamoDB
    3. Updates workflow status
    4. Returns appropriate response

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Log incoming request
    log_event('callback_received',
             request_id=context.request_id,
             source_ip=event.get('requestContext', {}).get('identity', {}).get('sourceIp'))

    # Parse request body
    body = parse_request_body(event)
    if body is None:
        return create_response(400, {
            'error': 'Invalid JSON in request body'
        })

    # Validate payload
    is_valid, error_message = validate_callback_payload(body)
    if not is_valid:
        log_event('validation_error', error=error_message)
        return create_response(400, {
            'error': error_message
        })

    # Extract fields
    token = body['token']
    status = body['status']
    result = body.get('result')
    error = body.get('error')

    log_event('callback_processing',
             token=token,
             status=status,
             has_result=result is not None,
             has_error=error is not None)

    # Store callback result
    storage_success = store_callback_result(token, status, result, error)
    if not storage_success:
        log_event('callback_failed', token=token, reason='storage_failed')
        return create_response(500, {
            'error': 'Failed to store callback result'
        })

    # Update workflow status
    update_success = update_workflow_status(token, status)
    if not update_success:
        # Log warning but don't fail the request
        # Callback is already stored, workflow update is best-effort
        log_event('workflow_update_warning',
                 token=token,
                 message='Callback stored but workflow update failed')

    # Return success response
    log_event('callback_completed', token=token, status=status)

    return create_response(200, {
        'status': 'callback_delivered',
        'token': token,
        'timestamp': datetime.utcnow().isoformat()
    })
