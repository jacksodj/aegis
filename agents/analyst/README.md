# Analyst Agent for Amazon Bedrock AgentCore Runtime

## Overview

The Analyst Agent is a specialized AI agent designed for the serverless durable agent orchestration platform. It receives research data from the Researcher agent and produces structured analysis with key insights, patterns, recommendations, and confidence scores.

## Architecture

This agent is built to run on **Amazon Bedrock AgentCore Runtime**, which provides:
- **Session isolation** via MicroVM per session
- **Long-running sessions** up to 8 hours
- **A2A protocol** support (JSON-RPC 2.0)
- **ARM64 (Graviton)** architecture for cost-efficiency

## Features

### Core Capabilities

1. **Multi-Stage Analysis**
   - Basic data analysis and statistics
   - Confidence score calculation
   - Pattern identification
   - Recommendation generation
   - LLM-powered deep insights using Claude

2. **Structured Output**
   - Key insights with explanations and confidence scores
   - Identified patterns (temporal, quantitative, research gaps)
   - SWOT-style detailed analysis
   - Actionable recommendations prioritized by importance

3. **Artifact Management**
   - Automatic S3 storage for large outputs (>200KB)
   - S3 reference resolution for large inputs
   - Workflow tracking with metadata

4. **Async Callback Pattern**
   - Supports both sync and async execution
   - Automatic callback to Durable Lambda controller
   - Error handling with failure callbacks

## File Structure

```
analyst/
├── Dockerfile              # Container configuration for AgentCore
├── agent-card.json        # Agent metadata and capabilities
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── src/
    ├── __init__.py       # Package initialization
    ├── main.py          # FastAPI application and core logic
    └── tools.py         # Analysis tools and utilities
```

## Components

### 1. Dockerfile

- **Base Image**: `python:3.11-slim`
- **Exposed Ports**:
  - `8080`: HTTP invocations endpoint
  - `9000`: A2A protocol endpoint
  - `8000`: MCP tools endpoint
- **Health Check**: Prevents idle timeout with `/ping` endpoint

### 2. src/main.py

FastAPI application with the following endpoints:

- **GET /ping**: Health check endpoint (returns "HealthyBusy")
- **GET /.well-known/agent-card.json**: Agent discovery metadata
- **POST /invocations**: Main A2A invocation endpoint (JSON-RPC 2.0)

Key functions:
- `execute_analysis()`: Main analysis orchestration
- `generate_llm_insights()`: Claude-powered deep analysis
- `execute_and_callback()`: Async execution with callback
- `fetch_s3_artifact()`: Retrieve large artifacts from S3

### 3. src/tools.py

Analysis utility functions:

- `save_artifact()`: Store large content to S3
- `analyze_data()`: Perform structured data analysis
- `calculate_confidence_scores()`: Compute confidence metrics
- `identify_patterns()`: Detect patterns in research data
- `generate_recommendations()`: Create actionable recommendations

### 4. agent-card.json

Agent metadata following A2A protocol specification:
- Capabilities definition
- Input schema for `analyze` capability
- Communication protocol details
- Authentication requirements

## Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `ARTIFACT_BUCKET` | Yes | S3 bucket name for storing artifacts | - |
| `MODEL_ID` | No | Bedrock model ID for LLM insights | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `AWS_REGION` | No | AWS region for Bedrock | `us-east-1` |

## Input Schema

The agent expects the following input structure:

```json
{
  "task": "analyze",
  "research_data": {
    "summary": "Brief overview",
    "key_findings": [...],
    "sources": [...],
    "data_points": [...],
    "gaps": [...]
  },
  "workflow_id": "workflow-123",
  "callback_url": "https://api.example.com/callbacks",
  "callback_token": "secure-token"
}
```

**Note**: `research_data` can also be an S3 reference:
```json
{
  "research_data": {
    "artifact_type": "s3_reference",
    "s3_uri": "s3://bucket/key"
  }
}
```

## Output Schema

The agent produces the following output structure:

```json
{
  "metadata": {
    "workflow_id": "workflow-123",
    "analyzed_at": "2025-12-23T10:30:00Z",
    "task_type": "analyze",
    "agent": "analyst-agent",
    "version": "1.0.0"
  },
  "summary": "Executive summary of analysis",
  "key_insights": [
    {
      "insight": "Key finding",
      "explanation": "Why this matters",
      "confidence": 0.9
    }
  ],
  "patterns_identified": [
    {
      "type": "temporal|quantitative|research_gaps",
      "description": "Pattern description",
      "confidence": 0.8
    }
  ],
  "confidence_scores": {
    "data_completeness": 0.85,
    "source_reliability": 0.75,
    "finding_consistency": 0.90,
    "overall": 0.83
  },
  "recommendations": [
    {
      "priority": "high|medium|low",
      "category": "research_quality|research_gaps|analysis_depth|proceed",
      "action": "Specific action to take",
      "rationale": "Why this is recommended"
    }
  ],
  "statistics": {
    "total_findings": 10,
    "total_sources": 8,
    "total_data_points": 25
  },
  "detailed_analysis": {
    "strengths": [...],
    "weaknesses": [...],
    "opportunities": [...],
    "threats": [...]
  }
}
```

## Analysis Workflow

1. **Receive Research Data**: Parse input from Durable Lambda controller
2. **Fetch S3 Artifacts**: If data is an S3 reference, retrieve it
3. **Basic Analysis**: Extract statistics and metadata
4. **Confidence Scoring**: Calculate reliability metrics
5. **Pattern Detection**: Identify temporal, quantitative, and gap patterns
6. **Recommendation Generation**: Create prioritized action items
7. **LLM Insights**: Use Claude for deep analysis and synthesis
8. **Output Assembly**: Compile structured analysis results
9. **Artifact Storage**: Save to S3 if output exceeds 200KB
10. **Callback**: Send results to Durable Lambda controller

## Building and Deploying

### Build Docker Image

```bash
cd /home/user/aegis/agents/analyst
docker build -t analyst-agent:latest --platform linux/arm64 .
```

### Deploy to AgentCore Runtime

```bash
# Using AgentCore CLI (when available)
agentcore configure -e src/main.py
agentcore deploy --name analyst-agent

# Or deploy via CDK/CloudFormation with container registry
```

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ARTIFACT_BUCKET=my-bucket
export MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
export AWS_REGION=us-east-1

# Run locally
python -m src.main
```

Then test with:

```bash
# Health check
curl http://localhost:8080/ping

# Agent card
curl http://localhost:8080/.well-known/agent-card.json

# Invoke analysis (example)
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
          "text": "{\"task\":\"analyze\",\"research_data\":{\"summary\":\"Test\",\"key_findings\":[\"Finding 1\"]},\"workflow_id\":\"test-123\"}"
        }]
      }
    }
  }'
```

## Integration with Orchestration Platform

The Analyst Agent is designed to work within the broader serverless durable agent orchestration platform:

```
┌─────────────────┐
│ Durable Lambda  │
│   Controller    │
└────────┬────────┘
         │ 1. Invoke with research data
         ▼
┌─────────────────┐
│   Researcher    │
│     Agent       │
└────────┬────────┘
         │ 2. Research results
         ▼
┌─────────────────┐
│    Analyst      │◄── You are here
│     Agent       │
└────────┬────────┘
         │ 3. Analysis results
         ▼
┌─────────────────┐
│  Human Approval │
│      Gate       │
└────────┬────────┘
         │ 4. Approved analysis
         ▼
┌─────────────────┐
│     Writer      │
│      Agent      │
└─────────────────┘
```

## IAM Permissions Required

The agent requires the following AWS permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::${ArtifactBucket}/*"
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

## Monitoring and Observability

The agent includes:
- Structured logging with timestamps and workflow IDs
- Health check endpoint to prevent idle timeouts
- Error handling with detailed error messages
- Callback success/failure reporting

## Security Considerations

- **SigV4 Authentication**: Required for A2A protocol
- **TLS Encryption**: All data in transit is encrypted
- **S3 Server-Side Encryption**: Artifacts encrypted at rest
- **MicroVM Isolation**: Each session runs in isolated environment
- **Token-based Callbacks**: Secure callback authentication

## Version History

- **1.0.0** (2025-12-23): Initial implementation
  - Multi-stage analysis pipeline
  - Claude-powered insights
  - Async callback support
  - S3 artifact management

## License

Part of the Serverless Durable Agent Orchestration Platform.

## Support

For issues or questions, refer to the main project documentation at `/home/user/aegis/serverless_durable_agent_orchestration_spec.md`.
