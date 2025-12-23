# Quick Reference - Durable Lambda Controller

## File Structure
```
controller/
├── handler.py              # Main workflow orchestration (870 lines)
├── utils.py                # Utility functions (549 lines)
├── example_usage.py        # Usage examples and tests
├── requirements.txt        # Python dependencies
├── README.md              # Comprehensive documentation
├── IMPLEMENTATION_SUMMARY.md  # Implementation details
└── QUICK_REFERENCE.md     # This file
```

## Import Patterns

```python
# Main handler
from controller.handler import handler, api_handler

# Direct function imports
from controller.handler import (
    init_workflow,
    invoke_agent_with_callback,
    request_approval,
    finalize_workflow,
    dispatch_agent_task
)

# Utilities
from controller.utils import (
    store_artifact,
    fetch_artifact,
    generate_presigned_url,
    create_workflow_record,
    update_workflow_status,
    get_workflow_state
)

# Exceptions
from controller.utils import (
    WorkflowError,
    AgentInvocationError,
    ArtifactStorageError,
    WorkflowStateError
)
```

## Common Code Snippets

### Start a Workflow
```python
import boto3
import json

lambda_client = boto3.client('lambda')

response = lambda_client.invoke(
    FunctionName='DurableControllerFunction',
    Payload=json.dumps({
        'topic': 'Your research topic',
        'parameters': {
            'depth': 'comprehensive',
            'sources': ['academic', 'industry']
        }
    })
)

result = json.loads(response['Payload'].read())
workflow_id = result['workflow_id']
```

### Check Workflow Status
```python
from controller.utils import get_workflow_state

state = get_workflow_state('workflow-table-name', workflow_id)
print(f"Status: {state['status']}")
print(f"Current step: {state['current_step']}")
```

### Store Large Artifact
```python
from controller.utils import store_artifact, is_large_payload

data = {"key": "value", ...}

if is_large_payload(data):
    artifact = store_artifact(
        bucket='artifact-bucket',
        key=f'artifacts/{workflow_id}/data.json',
        content=data,
        workflow_id=workflow_id
    )
    # Use S3 reference
    reference = artifact['s3_uri']
else:
    # Pass directly
    reference = data
```

### Fetch Artifact
```python
from controller.utils import fetch_artifact

data = fetch_artifact(
    s3_uri='s3://bucket/key',
    workflow_id=workflow_id
)
```

### Update Workflow Status
```python
from controller.utils import update_workflow_status

update_workflow_status(
    table_name='workflow-table',
    workflow_id=workflow_id,
    status='PROCESSING',
    current_step='analysis_phase',
    additional_fields={
        'progress': 50,
        'message': 'Halfway complete'
    }
)
```

### Invoke Agent
```python
from controller.handler import dispatch_agent_task

result = dispatch_agent_task(
    agent_arn='arn:aws:bedrock-agentcore:...',
    payload={
        'task': 'research',
        'topic': 'AI ethics',
        'workflow_id': workflow_id,
        'callback_url': 'https://...',
        'callback_token': 'token-123'
    }
)
```

## Environment Variables

```bash
# Required
export ARTIFACT_BUCKET=my-artifacts-bucket
export WORKFLOW_TABLE=agent-workflows
export RESEARCHER_AGENT_ARN=arn:aws:bedrock-agentcore:region:account:agent-runtime/researcher
export ANALYST_AGENT_ARN=arn:aws:bedrock-agentcore:region:account:agent-runtime/analyst
export WRITER_AGENT_ARN=arn:aws:bedrock-agentcore:region:account:agent-runtime/writer
export CALLBACK_API_URL=https://api-id.execute-api.region.amazonaws.com/v1

# Optional
export APPROVAL_TIMEOUT_HOURS=24
export APPROVAL_SNS_TOPIC_ARN=arn:aws:sns:region:account:topic-name
```

## Workflow States

| State | Description |
|-------|-------------|
| `INITIALIZING` | Workflow record created |
| `RUNNING` | Workflow executing |
| `AWAITING_APPROVAL` | Paused for human approval |
| `REJECTED` | Human rejected |
| `COMPLETED` | Successfully finished |
| `FAILED` | Error occurred |
| `PENDING` | Waiting for agent callback |

## Workflow Steps

1. **init_workflow** - Create DynamoDB record
2. **research_phase_dispatch** - Send task to researcher
3. **research_phase_await** - Wait for research completion
4. **research_phase_fetch_artifact** - Get S3 artifact if needed
5. **analysis_phase_dispatch** - Send task to analyst
6. **analysis_phase_await** - Wait for analysis completion
7. **analysis_phase_fetch_artifact** - Get S3 artifact if needed
8. **request_approval** - Send approval request
9. **human_approval** - Wait for approval callback
10. **writing_phase_dispatch** - Send task to writer
11. **writing_phase_await** - Wait for report completion
12. **writing_phase_fetch_artifact** - Get S3 artifact if needed
13. **finalize_workflow** - Store report and generate URL

## Agent Callback Format

```json
POST {callback_url}
Content-Type: application/json

{
  "token": "callback-token-from-dispatch",
  "status": "SUCCESS",
  "result": {
    "summary": "Result summary",
    "data": {...}
  }
}

# OR for S3 reference
{
  "token": "callback-token",
  "status": "SUCCESS",
  "result": {
    "artifact_type": "s3_reference",
    "s3_uri": "s3://bucket/key"
  }
}

# OR for failure
{
  "token": "callback-token",
  "status": "FAILURE",
  "error": "Error message"
}
```

## Error Handling

```python
from controller.utils import (
    WorkflowError,
    AgentInvocationError,
    ArtifactStorageError
)

try:
    # Your code
    result = dispatch_agent_task(...)
except AgentInvocationError as e:
    # Handle agent errors
    logger.error("Agent failed", error=str(e))
except ArtifactStorageError as e:
    # Handle storage errors
    logger.error("Storage failed", error=str(e))
except WorkflowError as e:
    # Handle general workflow errors
    logger.error("Workflow failed", error=str(e))
```

## Logging

```python
import structlog

logger = structlog.get_logger(__name__)

# Bind context
log = logger.bind(workflow_id=workflow_id, step='research')

# Log events
log.info("step_starting", agent_arn=agent_arn)
log.warning("retry_needed", attempt=2)
log.error("step_failed", error=str(e))
```

## Testing Locally

```python
# Mock event
event = {
    'topic': 'Test topic',
    'parameters': {'depth': 'basic'}
}

# Mock context
class MockContext:
    request_id = 'test-123'
    function_name = 'test-function'

# Call handler
from controller.handler import handler
result = handler(event, MockContext())
```

## Common Patterns

### Retry with Backoff
```python
import time
from botocore.exceptions import ClientError

max_retries = 3
for attempt in range(max_retries):
    try:
        result = dispatch_agent_task(...)
        break
    except ClientError as e:
        if attempt == max_retries - 1:
            raise
        wait_time = 2 ** attempt
        time.sleep(wait_time)
```

### Conditional S3 Storage
```python
from controller.utils import is_large_payload, store_artifact

if is_large_payload(data):
    artifact = store_artifact(bucket, key, data)
    return {'type': 's3_ref', 'uri': artifact['s3_uri']}
else:
    return {'type': 'inline', 'data': data}
```

### Progress Tracking
```python
steps = ['step1', 'step2', 'step3']
total = len(steps)

for i, step in enumerate(steps):
    progress = int((i / total) * 100)
    update_workflow_status(
        table, workflow_id, 'RUNNING',
        current_step=step,
        additional_fields={'progress_percent': progress}
    )
    # Execute step
    ...
```

## Performance Tips

1. **Lazy Client Loading**: Clients initialized on first use
2. **Batch Operations**: Use DynamoDB batch operations when possible
3. **S3 Multipart**: Use multipart upload for files >5MB
4. **Connection Pooling**: boto3 handles this automatically
5. **Memory Management**: Clean up large objects after use

## Security Checklist

- [ ] IAM roles have minimum required permissions
- [ ] S3 buckets have encryption enabled
- [ ] Callback tokens are unique per request
- [ ] Presigned URLs have appropriate expiration
- [ ] Secrets in AWS Secrets Manager (not env vars)
- [ ] Input validation on all parameters
- [ ] Error messages don't leak sensitive data

## Debugging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check workflow state
from controller.utils import get_workflow_state
state = get_workflow_state(table, workflow_id)
print(json.dumps(state, indent=2))

# Verify S3 artifact
from controller.utils import fetch_artifact
data = fetch_artifact(s3_uri, workflow_id)
print(f"Artifact size: {len(json.dumps(data))} bytes")
```

## Useful AWS CLI Commands

```bash
# Invoke function
aws lambda invoke \
  --function-name DurableControllerFunction \
  --payload '{"topic":"Test"}' \
  response.json

# Check logs
aws logs tail /aws/lambda/DurableControllerFunction --follow

# Get workflow from DynamoDB
aws dynamodb get-item \
  --table-name agent-workflows \
  --key '{"workflow_id":{"S":"uuid"}}'

# List S3 artifacts
aws s3 ls s3://artifact-bucket/artifacts/ --recursive

# Check function config
aws lambda get-function-configuration \
  --function-name DurableControllerFunction
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Workflow stuck in PENDING | Check agent callback logs, verify callback URL |
| S3 access denied | Verify IAM role has s3:GetObject, s3:PutObject |
| DynamoDB access denied | Verify IAM role has dynamodb:PutItem, etc. |
| Agent timeout | Increase timeout in invoke_agent_with_callback |
| Large payload error | Ensure is_large_payload() threshold is appropriate |
| Callback not received | Verify callback URL is accessible from agent |

## Resources

- Full Documentation: `README.md`
- Implementation Details: `IMPLEMENTATION_SUMMARY.md`
- Usage Examples: `example_usage.py`
- Specification: `/home/user/aegis/serverless_durable_agent_orchestration_spec.md`
