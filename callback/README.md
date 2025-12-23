# Callback Handler Lambda

The Callback Handler Lambda is a critical component of the serverless durable agent orchestration platform. It receives callbacks from AgentCore agents when they complete their tasks (successfully or with errors) and processes these callbacks to update the workflow state.

## Overview

When AgentCore agents execute long-running tasks (up to 8 hours), they need a way to notify the Durable Lambda controller when they complete. This handler provides that endpoint, accepting callbacks and managing the state updates.

## Architecture

```
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│  AgentCore      │          │   API Gateway   │          │   Callback      │
│  Agent          │─────────>│   /callbacks    │─────────>│   Handler       │
│  (Researcher/   │  HTTP    │                 │  Lambda  │   Lambda        │
│   Analyst/      │  POST    │                 │  Invoke  │                 │
│   Writer)       │          │                 │          │                 │
└─────────────────┘          └─────────────────┘          └────────┬────────┘
                                                                    │
                                                                    │ Store
                                                                    ▼
                                                          ┌──────────────────┐
                                                          │   DynamoDB       │
                                                          │   - Callback     │
                                                          │     Results      │
                                                          │   - Workflow     │
                                                          │     Status       │
                                                          └──────────────────┘
```

## Functionality

### 1. Request Parsing
- Validates incoming JSON payload from API Gateway
- Extracts callback token, status, result/error data

### 2. Payload Validation
- Ensures all required fields are present:
  - `token`: Unique callback identifier
  - `status`: Either "SUCCESS" or "FAILURE"
  - `result`: Required for SUCCESS status
  - `error`: Required for FAILURE status

### 3. Result Storage
- Stores callback results in DynamoDB keyed by token
- For large results (>256KB), automatically stores in S3 and saves reference
- Adds 14-day TTL for automatic cleanup

### 4. Workflow Status Update
- Queries DynamoDB to find associated workflow
- Updates workflow status to COMPLETED or FAILED
- Updates timestamp for tracking

### 5. Structured Logging
- All operations logged with structured JSON format
- Includes timestamp, event type, and contextual data
- Facilitates debugging and monitoring via CloudWatch

## API Contract

### Request Format

**Endpoint:** `POST /callbacks`

**Headers:**
```
Content-Type: application/json
```

**Body (SUCCESS):**
```json
{
  "token": "unique-callback-token-from-durable-lambda",
  "status": "SUCCESS",
  "result": {
    "summary": "Research findings...",
    "key_findings": [...],
    "sources": [...],
    "data_points": {...}
  }
}
```

**Body (FAILURE):**
```json
{
  "token": "unique-callback-token-from-durable-lambda",
  "status": "FAILURE",
  "error": "Detailed error message explaining what went wrong"
}
```

### Response Format

**Success (200):**
```json
{
  "status": "callback_delivered",
  "token": "unique-callback-token-from-durable-lambda",
  "timestamp": "2025-12-23T10:30:00.000Z"
}
```

**Bad Request (400):**
```json
{
  "error": "Missing required field: token"
}
```

**Internal Error (500):**
```json
{
  "error": "Failed to store callback result"
}
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WORKFLOW_TABLE` | Yes | DynamoDB table name for workflow metadata |
| `ARTIFACT_BUCKET` | Yes | S3 bucket name for large artifacts |

## Error Handling

The handler implements comprehensive error handling:

1. **JSON Parse Errors**: Returns 400 with descriptive message
2. **Validation Errors**: Returns 400 with specific field error
3. **DynamoDB Errors**: Logged and returns 500
4. **S3 Errors**: Logged and returns 500
5. **Workflow Not Found**: Logs warning but returns 200 (callback still stored)

## Logging

All logs are structured JSON for easy querying in CloudWatch Logs Insights:

```json
{
  "timestamp": "2025-12-23T10:30:00.000Z",
  "event_type": "callback_received",
  "request_id": "abc123",
  "token": "callback-token-xyz",
  "status": "SUCCESS"
}
```

### Example CloudWatch Logs Insights Queries

**Find all failed callbacks:**
```
fields @timestamp, token, error
| filter event_type = "callback_processing" and status = "FAILURE"
| sort @timestamp desc
```

**Track callback processing time:**
```
fields @timestamp, token
| filter event_type in ["callback_received", "callback_completed"]
| stats count() by token
```

**Find storage errors:**
```
fields @timestamp, token, error
| filter event_type = "storage_error"
| sort @timestamp desc
```

## Testing

### Unit Tests

Run the unit tests:

```bash
cd callback
pip install -r requirements.txt
python -m pytest test_handler.py -v
```

### Integration Testing

Test with a real event payload:

```python
import json
from handler import handler

# Mock Lambda context
class Context:
    request_id = "test-request-123"

# Test event
event = {
    "body": json.dumps({
        "token": "test-token-123",
        "status": "SUCCESS",
        "result": {"data": "test"}
    }),
    "requestContext": {
        "identity": {"sourceIp": "127.0.0.1"}
    }
}

# Invoke handler
response = handler(event, Context())
print(json.dumps(response, indent=2))
```

### Manual Testing with curl

```bash
# Success callback
curl -X POST https://your-api-gateway-url/v1/callbacks \
  -H "Content-Type: application/json" \
  -d '{
    "token": "test-token-123",
    "status": "SUCCESS",
    "result": {
      "summary": "Test research completed",
      "findings": ["Finding 1", "Finding 2"]
    }
  }'

# Failure callback
curl -X POST https://your-api-gateway-url/v1/callbacks \
  -H "Content-Type: application/json" \
  -d '{
    "token": "test-token-456",
    "status": "FAILURE",
    "error": "Agent timeout after 8 hours"
  }'
```

## Security Considerations

1. **Authentication**: Currently uses API Gateway without authentication for ease of agent integration. Consider adding:
   - API key authentication
   - AWS SigV4 signing
   - Custom authorizer

2. **Token Validation**: Tokens should be cryptographically secure random values

3. **Input Sanitization**: All inputs are parsed as JSON and not executed as code

4. **Rate Limiting**: Consider API Gateway throttling to prevent abuse

5. **Encryption**:
   - Data in transit: HTTPS enforced
   - Data at rest: DynamoDB and S3 use AWS encryption

## Monitoring and Alerts

### Key Metrics to Monitor

1. **Invocation Count**: Track total callbacks received
2. **Error Rate**: 4xx and 5xx responses
3. **Storage Failures**: Failed DynamoDB/S3 writes
4. **Latency**: p50, p99, p99.9 response times
5. **Workflow Update Failures**: Callbacks stored but workflow not updated

### Recommended CloudWatch Alarms

```yaml
- Alarm: CallbackErrorRate
  Threshold: > 5% over 5 minutes
  Action: SNS notification

- Alarm: CallbackLatency
  Threshold: p99 > 3000ms
  Action: SNS notification

- Alarm: StorageFailures
  Threshold: > 10 failures in 15 minutes
  Action: SNS notification + PagerDuty
```

## Performance Characteristics

- **Cold Start**: ~200-400ms (Python 3.12, 256MB memory)
- **Warm Execution**: ~50-150ms
- **Concurrent Executions**: Scales automatically with API Gateway
- **Throughput**: Can handle 1000+ callbacks/second with proper DynamoDB capacity

## Troubleshooting

### Common Issues

**Issue**: "Missing required field: token"
- **Cause**: Agent not including callback token in request
- **Fix**: Ensure agent receives callback URL and token from durable lambda

**Issue**: "Failed to store callback result"
- **Cause**: DynamoDB or S3 permission issues
- **Fix**: Verify Lambda execution role has necessary permissions

**Issue**: Workflow not updating after callback
- **Cause**: Workflow record doesn't contain callback_token field
- **Fix**: Ensure durable lambda stores callback_token when creating workflow

**Issue**: Large payloads timing out
- **Cause**: S3 upload taking too long
- **Fix**: Increase Lambda timeout and optimize S3 settings

## Future Enhancements

1. **Retry Logic**: Implement exponential backoff for failed DynamoDB/S3 operations
2. **Dead Letter Queue**: Route failed callbacks to DLQ for manual review
3. **Callback Deduplication**: Prevent duplicate processing of same callback
4. **Metrics Emission**: Publish custom CloudWatch metrics for better monitoring
5. **Webhook Notifications**: Send notifications when callbacks are processed
6. **Callback History**: Maintain history of all callbacks for workflow audit trail

## Related Components

- **Controller Lambda** (`/controller/handler.py`): Main orchestration logic
- **Agent Workers** (`/agents/*/`): Agents that send callbacks
- **Infrastructure** (`/infrastructure/app.py`): CDK deployment code

## Contributing

When modifying this handler:

1. Run unit tests: `pytest test_handler.py`
2. Update this README if changing API contract
3. Add structured logging for new code paths
4. Consider backward compatibility for deployed workflows
5. Test with both small and large payloads (>256KB)

## License

This component is part of the Serverless Durable Agent Orchestration Platform.
