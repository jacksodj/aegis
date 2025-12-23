# Researcher Agent

A specialized research agent designed for Amazon Bedrock AgentCore Runtime. This agent performs comprehensive information gathering and synthesis from multiple sources.

## Overview

The Researcher Agent is a containerized service that implements the A2A (Agent-to-Agent) protocol for seamless integration with AWS Lambda Durable Functions and other orchestration systems. It's designed to run long-running research tasks (up to 8 hours) with automatic state management and callback support.

## Features

- **Web Search Integration**: Simulated web search with realistic result synthesis
- **Document Analysis**: Internal document search capabilities
- **Artifact Storage**: Automatic S3 storage for large research outputs
- **Async Execution**: Support for callback-based asynchronous task execution
- **Health Monitoring**: HealthyBusy status to prevent idle timeouts
- **A2A Protocol**: Full JSON-RPC 2.0 implementation
- **Agent Discovery**: Metadata exposure via agent-card.json

## Architecture

```
researcher/
├── Dockerfile              # Container definition
├── requirements.txt        # Python dependencies
├── agent-card.json        # Agent metadata and capabilities
├── README.md              # This file
└── src/
    ├── __init__.py
    ├── main.py            # FastAPI application
    └── tools.py           # Research tools and utilities
```

## API Endpoints

### Health & Discovery

- **GET /ping** - Health check (returns `{"status": "HealthyBusy"}`)
- **GET /health** - Detailed health information
- **GET /.well-known/agent-card.json** - Agent metadata

### Task Execution

- **POST /invocations** - Primary task endpoint (port 8080)
- **POST /** - A2A protocol endpoint (port 9000)

## Request Format

### Synchronous Execution

```json
{
  "jsonrpc": "2.0",
  "id": "request-123",
  "method": "tasks/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "{\"topic\": \"quantum computing\", \"workflow_id\": \"wf-123\"}"
        }
      ]
    }
  }
}
```

### Asynchronous Execution (with callback)

```json
{
  "jsonrpc": "2.0",
  "id": "request-123",
  "method": "tasks/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "{\"topic\": \"quantum computing\", \"workflow_id\": \"wf-123\", \"callback_url\": \"https://api.example.com/callbacks\", \"callback_token\": \"secret-token\"}"
        }
      ]
    }
  }
}
```

## Task Payload Schema

```json
{
  "topic": "string (required)",
  "workflow_id": "string (required)",
  "parameters": {
    "depth": "basic|comprehensive|deep",
    "sources": ["academic", "industry", "technical"],
    "max_results": 10
  },
  "callback_url": "string (optional)",
  "callback_token": "string (optional if callback_url provided)"
}
```

## Response Format

### Synchronous Response

```json
{
  "jsonrpc": "2.0",
  "id": "request-123",
  "result": {
    "topic": "quantum computing",
    "research_type": "comprehensive",
    "executive_summary": "...",
    "key_findings": [...],
    "detailed_analysis": {...},
    "recommendations": [...],
    "sources_cited": [...],
    "research_gaps": [...],
    "metadata": {...}
  }
}
```

### Asynchronous Response (immediate)

```json
{
  "jsonrpc": "2.0",
  "id": "request-123",
  "result": {
    "status": "accepted",
    "message": "Task queued for async execution",
    "workflow_id": "wf-123"
  }
}
```

### Callback Payload (sent on completion)

```json
{
  "token": "secret-token",
  "status": "SUCCESS",
  "result": {
    "topic": "quantum computing",
    "executive_summary": "...",
    ...
  }
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MODEL_ID` | Amazon Bedrock model ID | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `ARTIFACT_BUCKET` | S3 bucket for large artifacts | `aegis-artifacts` |
| `CALLBACK_API_URL` | Base URL for callbacks | `http://localhost:8000/callbacks` |
| `AWS_REGION` | AWS region | `us-east-1` |

## Building the Container

```bash
cd /home/user/aegis/agents/researcher
docker build -t researcher-agent:latest .
```

## Running Locally

### Using Docker

```bash
docker run -p 8080:8080 -p 9000:9000 \
  -e ARTIFACT_BUCKET=my-bucket \
  -e MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0 \
  -e AWS_ACCESS_KEY_ID=your-key \
  -e AWS_SECRET_ACCESS_KEY=your-secret \
  -e AWS_REGION=us-east-1 \
  researcher-agent:latest
```

### Using Python directly

```bash
cd /home/user/aegis/agents/researcher
pip install -r requirements.txt
export ARTIFACT_BUCKET=my-bucket
python -m src.main
```

## Testing

### Health Check

```bash
curl http://localhost:8080/ping
```

### Agent Discovery

```bash
curl http://localhost:8080/.well-known/agent-card.json | jq
```

### Synchronous Research Task

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "tasks/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{
          "kind": "text",
          "text": "{\"topic\": \"artificial intelligence ethics\", \"workflow_id\": \"test-wf-1\"}"
        }]
      }
    }
  }' | jq
```

### Asynchronous Research Task

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-2",
    "method": "tasks/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{
          "kind": "text",
          "text": "{\"topic\": \"climate change mitigation\", \"workflow_id\": \"test-wf-2\", \"callback_url\": \"https://webhook.site/your-unique-id\", \"callback_token\": \"test-token-123\"}"
        }]
      }
    }
  }' | jq
```

## Deployment to AgentCore

### Prerequisites

```bash
# Install AgentCore CLI
pip install bedrock-agentcore-starter-toolkit

# Configure AWS credentials
aws configure
```

### Deploy Agent

```bash
# Build and push container
docker build -t researcher-agent:latest .
docker tag researcher-agent:latest ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/researcher-agent:latest
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com
docker push ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/researcher-agent:latest

# Deploy to AgentCore (command syntax may vary)
agentcore deploy \
  --name researcher-agent \
  --image ${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/researcher-agent:latest \
  --port 8080 \
  --health-check /ping
```

## Tools & Capabilities

### Web Search (`search_web`)

Simulated web search that returns realistic search results with:
- Multiple source types (academic, industry, technical, etc.)
- Confidence scores
- Publication dates
- Relevance ranking

### Document Search (`search_documents`)

Combines web search with internal document search for comprehensive coverage.

### Artifact Storage (`save_artifact`)

Automatically saves large research outputs (>200KB) to S3 and returns a reference:

```json
{
  "artifact_type": "s3_reference",
  "s3_uri": "s3://bucket/artifacts/workflow-id/research_results_timestamp.json",
  "bucket": "bucket-name",
  "key": "artifacts/...",
  "size_bytes": 500000,
  "timestamp": "2025-12-23T10:00:00Z"
}
```

### Research Synthesis (`synthesize_research`)

Combines multiple search results into structured findings with:
- Summary generation
- Key findings extraction
- Source categorization
- Data quality metrics
- Gap identification

## LLM Integration

The agent supports both simulated and real Amazon Bedrock integration:

### Simulated Mode (Default)

When Bedrock is not available or configured, the agent uses a simulated LLM that generates realistic research reports based on templates and search results.

### Bedrock Mode

When AWS credentials and Bedrock access are configured, the agent will attempt to use Claude via Bedrock for higher quality synthesis. Set environment variables:

```bash
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_REGION=us-east-1
export MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

## Monitoring & Observability

### Logging

All operations are logged with structured logging. Logs include:
- Request/response details
- Task execution metrics
- Error traces
- Callback status

### Metrics

The agent tracks:
- `tasks_completed`: Total successful tasks
- `tasks_failed`: Total failed tasks
- `startup_time`: Agent startup timestamp

Access via `/health` endpoint.

### Health Checks

AgentCore performs health checks every 30 seconds via `/ping`. The agent responds with `{"status": "HealthyBusy"}` to prevent idle timeout.

## Error Handling

### Retry Policy

- Max attempts: 3
- Backoff: Exponential (5s, 10s, 20s)
- Max backoff: 2 minutes

### Timeout Handling

- Default timeout: 15 minutes
- Max duration: 8 hours (AgentCore session limit)
- Callback on timeout: Yes

### Error Response Format

```json
{
  "token": "callback-token",
  "status": "FAILURE",
  "error": "Error message",
  "error_type": "ExceptionType"
}
```

## Security

- **AWS SigV4**: All AgentCore invocations use SigV4 authentication
- **Callback Tokens**: Unique tokens validate callbacks
- **IAM Permissions**: Agent requires S3 read/write and Bedrock invoke permissions

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::${ARTIFACT_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:*:*:model/*"
    }
  ]
}
```

## Troubleshooting

### Agent not responding

```bash
# Check health
curl http://localhost:8080/ping

# Check logs
docker logs <container-id>
```

### Callbacks not received

- Verify callback URL is accessible
- Check callback token matches
- Review agent logs for callback errors

### Large results causing timeouts

- Results >200KB are automatically saved to S3
- Increase `ARTIFACT_BUCKET` permissions if S3 errors occur

### Bedrock errors

- Verify IAM permissions
- Check MODEL_ID is valid
- Ensure region supports Bedrock
- Agent falls back to simulated mode on Bedrock errors

## Contributing

See the main project README for contribution guidelines.

## License

MIT

## Support

For issues or questions:
- GitHub Issues: [project-repo/issues]
- Email: support@example.com
- Slack: #agent-support
