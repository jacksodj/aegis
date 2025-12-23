# Serverless Durable Agent Orchestration Platform
## Technical Specification & Implementation Guide

**Version:** 1.0  
**Date:** December 2025  
**Status:** MVP Specification  
**Target:** Claude Code Implementation

---

## 1. Executive Summary

This specification defines an MVP for a serverless, durable agent orchestration platform combining AWS Lambda Durable Functions (controller) with Amazon Bedrock AgentCore Runtime (workers). The system enables long-running, fault-tolerant multi-agent workflows with zero infrastructure management.

**Key Innovation:** Code-first workflow orchestration using Python with automatic state persistence, controlling specialized AI agents that can run for up to 8 hours per task.

**MVP Scope:** A research workflow demonstrating durable orchestration of multiple Strands Agents—a coordinator agent dispatching tasks to specialist agents (researcher, analyst, writer) with human-in-the-loop approval gates.

---

## 2. Architecture Overview

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  API Gateway    │  │  EventBridge    │  │  S3 (Document Upload)       │  │
│  │  (REST/WebSocket)│  │  (Async Trigger)│  │                             │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘  │
└───────────┼─────────────────────┼──────────────────────────┼────────────────┘
            │                     │                          │
            ▼                     ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATION LAYER                                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              AWS Lambda Durable Function (Controller)                  │  │
│  │                                                                        │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │  │
│  │  │   step()    │  │   wait()    │  │ wait_for_   │  │  parallel()  │  │  │
│  │  │ (checkpoint)│  │ (zero-cost) │  │ callback()  │  │  (fan-out)   │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └──────────────┘  │  │
│  │                                                                        │  │
│  │  State Backend: Managed (S3 + DynamoDB internally)                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
            │                     │                          │
            │  A2A (JSON-RPC 2.0) │  Callback API            │ S3 References
            ▼                     ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AGENT WORKER LAYER                                 │
│                     (Amazon Bedrock AgentCore Runtime)                       │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Researcher     │  │  Analyst        │  │  Writer                     │  │
│  │  Agent          │  │  Agent          │  │  Agent                      │  │
│  │  (Strands)      │  │  (Strands)      │  │  (Strands)                  │  │
│  │                 │  │                 │  │                             │  │
│  │  Port 9000/A2A  │  │  Port 9000/A2A  │  │  Port 9000/A2A              │  │
│  │  Port 8000/MCP  │  │  Port 8000/MCP  │  │  Port 8000/MCP              │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
│                                                                              │
│  Session Isolation: MicroVM per session | Max Duration: 8 hours             │
│  Architecture: ARM64 (Graviton) required                                    │
└─────────────────────────────────────────────────────────────────────────────┘
            │                     │                          │
            ▼                     ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SERVICES LAYER                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Bedrock        │  │  MCP Servers    │  │  Observability              │  │
│  │  (Claude 3.5)   │  │  (Web Search,   │  │  (X-Ray, CloudWatch,        │  │
│  │                 │  │   File Access)  │  │   EventBridge)              │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
            │                     │                          │
            ▼                     ▼                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PERSISTENCE LAYER                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  DynamoDB       │  │  S3             │  │  Secrets Manager            │  │
│  │  (Workflow      │  │  (Artifacts,    │  │  (API Keys, OAuth)          │  │
│  │   Metadata)     │  │   Documents)    │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow Sequence

```
┌────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│ Client │     │   Durable    │     │  AgentCore  │     │   Bedrock   │
│        │     │   Lambda     │     │   Runtime   │     │   (LLM)     │
└───┬────┘     └──────┬───────┘     └──────┬──────┘     └──────┬──────┘
    │                 │                    │                   │
    │ 1. Start Workflow                    │                   │
    │────────────────>│                    │                   │
    │                 │                    │                   │
    │                 │ 2. step(): Invoke Researcher           │
    │                 │───────────────────>│                   │
    │                 │    (A2A JSON-RPC)  │                   │
    │                 │                    │ 3. Query LLM      │
    │                 │                    │──────────────────>│
    │                 │                    │                   │
    │                 │                    │<──────────────────│
    │                 │                    │   4. Response     │
    │                 │<───────────────────│                   │
    │                 │   5. Checkpoint result                 │
    │                 │                    │                   │
    │                 │ 6. wait_for_callback() [SUSPENDED]     │
    │<────────────────│                    │                   │
    │  7. Request approval (notification)  │                   │
    │                 │                    │                   │
    │ 8. Human approves                    │                   │
    │────────────────>│                    │                   │
    │                 │ [RESUMED]          │                   │
    │                 │                    │                   │
    │                 │ 9. step(): Invoke Writer               │
    │                 │───────────────────>│                   │
    │                 │                    │──────────────────>│
    │                 │                    │<──────────────────│
    │                 │<───────────────────│                   │
    │                 │                    │                   │
    │<────────────────│                    │                   │
    │ 10. Final result                     │                   │
    │                 │                    │                   │
```

---

## 3. MVP Functional Requirements

### 3.1 Workflow Engine (Durable Lambda Controller)

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| WF-01 | Execute workflows up to 365 days duration | P0 | Core durable capability |
| WF-02 | Checkpoint state after each step() operation | P0 | Max 256KB per operation |
| WF-03 | Resume from checkpoint after failure/timeout | P0 | Replay-based recovery |
| WF-04 | Support wait() with zero compute cost | P0 | For delays between steps |
| WF-05 | Support wait_for_callback() for human approval | P0 | External signal pattern |
| WF-06 | Support parallel() for concurrent agent invocation | P1 | Fan-out/fan-in |
| WF-07 | Store large payloads (>256KB) in S3 with reference | P0 | Artifact pattern |
| WF-08 | Emit EventBridge events for workflow state changes | P1 | Observability |
| WF-09 | Propagate X-Ray trace context to agents | P1 | Distributed tracing |
| WF-10 | Handle agent timeout (>15min) via async callback | P0 | Critical for long tasks |

### 3.2 Agent Workers (AgentCore Runtime)

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| AG-01 | Deploy Strands agents to AgentCore Runtime | P0 | ARM64 containers |
| AG-02 | Expose A2A protocol on port 9000 | P0 | JSON-RPC 2.0 |
| AG-03 | Publish agent-card.json at /.well-known/ | P0 | Discovery |
| AG-04 | Support session duration up to 8 hours | P0 | Deep research |
| AG-05 | Implement /ping endpoint for health (HealthyBusy) | P0 | Prevent idle timeout |
| AG-06 | Connect to MCP tools on port 8000 | P1 | Web search, file access |
| AG-07 | Use Bedrock Claude 3.5 Sonnet for inference | P0 | Primary model |
| AG-08 | Send callback to Durable Lambda on completion | P0 | Async pattern |
| AG-09 | Store artifacts in S3, return references | P0 | Large output handling |
| AG-10 | Support SigV4 authentication for controller calls | P0 | Security |

### 3.3 MVP Demo Workflow: Research Report Generation

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| DM-01 | Accept research topic and parameters via API | P0 | Entry point |
| DM-02 | Researcher agent gathers information (web + docs) | P0 | MCP tools |
| DM-03 | Analyst agent synthesizes findings | P0 | Second stage |
| DM-04 | Human approval gate before final writing | P0 | HITL demo |
| DM-05 | Writer agent produces formatted report | P0 | Final output |
| DM-06 | Return report as S3 presigned URL | P0 | Delivery |
| DM-07 | Track workflow status via API | P1 | Monitoring |
| DM-08 | Support workflow cancellation | P1 | Control |

---

## 4. Technical Specifications

### 4.1 Durable Lambda Controller

**Runtime Configuration:**
```yaml
Runtime: python3.12
Architecture: arm64
MemorySize: 1024  # MB
Timeout: 900  # 15 minutes (max per invocation)
DurableExecution:
  Enabled: true
  StateRetentionDays: 14
  MaxOperations: 3000
  MaxDataSize: 104857600  # 100 MB
```

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DurableExecutionPermissions",
      "Effect": "Allow",
      "Action": [
        "lambda:CheckpointDurableExecution",
        "lambda:GetDurableExecutionState",
        "lambda:ListDurableExecutions"
      ],
      "Resource": "arn:aws:lambda:${Region}:${Account}:function:${FunctionName}:*"
    },
    {
      "Sid": "AgentCoreInvocation",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:InvokeAgentRuntime",
        "bedrock-agentcore:GetAgentRuntime"
      ],
      "Resource": "arn:aws:bedrock-agentcore:${Region}:${Account}:agent-runtime/*"
    },
    {
      "Sid": "ArtifactStorage",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::${ArtifactBucket}/*"
    },
    {
      "Sid": "WorkflowMetadata",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:${Region}:${Account}:table/${WorkflowTable}"
    },
    {
      "Sid": "Observability",
      "Effect": "Allow",
      "Action": [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "events:PutEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

**Controller Implementation Pattern:**
```python
# controller/handler.py
import json
import boto3
import uuid
from datetime import timedelta
from aws_durable_execution_sdk_python import (
    durable_execution,
    DurableContext,
    WaitForCallbackConfig,
    Duration
)

# Clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
agentcore = boto3.client('bedrock-agentcore')

ARTIFACT_BUCKET = os.environ['ARTIFACT_BUCKET']
WORKFLOW_TABLE = os.environ['WORKFLOW_TABLE']
RESEARCHER_ARN = os.environ['RESEARCHER_AGENT_ARN']
ANALYST_ARN = os.environ['ANALYST_AGENT_ARN']
WRITER_ARN = os.environ['WRITER_AGENT_ARN']
APPROVAL_TIMEOUT_HOURS = 24


@durable_execution
def handler(event: dict, context: DurableContext):
    """
    Main orchestration workflow for research report generation.
    
    Workflow Steps:
    1. Initialize workflow metadata
    2. Invoke Researcher agent (sync or async based on expected duration)
    3. Invoke Analyst agent with research results
    4. Wait for human approval
    5. Invoke Writer agent to produce final report
    6. Store and return results
    """
    workflow_id = event.get('workflow_id', str(uuid.uuid4()))
    topic = event['topic']
    parameters = event.get('parameters', {})
    
    # Step 1: Initialize workflow record
    context.step(
        lambda: init_workflow(workflow_id, topic, parameters),
        name='init_workflow'
    )
    
    # Step 2: Research phase
    # Use async pattern for potentially long-running research
    research_results = invoke_agent_with_callback(
        context=context,
        step_name='research_phase',
        agent_arn=RESEARCHER_ARN,
        payload={
            'task': 'research',
            'topic': topic,
            'parameters': parameters,
            'workflow_id': workflow_id
        },
        timeout_hours=4
    )
    
    # Step 3: Analysis phase
    analysis_results = invoke_agent_with_callback(
        context=context,
        step_name='analysis_phase',
        agent_arn=ANALYST_ARN,
        payload={
            'task': 'analyze',
            'research_data': research_results,
            'workflow_id': workflow_id
        },
        timeout_hours=2
    )
    
    # Step 4: Human approval gate
    context.step(
        lambda: send_approval_request(workflow_id, analysis_results),
        name='send_approval_request'
    )
    
    approval = context.wait_for_callback(
        name='await_human_approval',
        config=WaitForCallbackConfig(
            timeout=Duration.from_hours(APPROVAL_TIMEOUT_HOURS)
        )
    )
    
    if not approval.get('approved', False):
        context.step(
            lambda: update_workflow_status(workflow_id, 'REJECTED'),
            name='mark_rejected'
        )
        return {'status': 'rejected', 'workflow_id': workflow_id}
    
    # Step 5: Writing phase
    report = invoke_agent_with_callback(
        context=context,
        step_name='writing_phase',
        agent_arn=WRITER_ARN,
        payload={
            'task': 'write_report',
            'analysis': analysis_results,
            'feedback': approval.get('feedback', ''),
            'workflow_id': workflow_id
        },
        timeout_hours=1
    )
    
    # Step 6: Finalize and return
    result = context.step(
        lambda: finalize_workflow(workflow_id, report),
        name='finalize_workflow'
    )
    
    return {
        'status': 'completed',
        'workflow_id': workflow_id,
        'report_url': result['presigned_url']
    }


def invoke_agent_with_callback(
    context: DurableContext,
    step_name: str,
    agent_arn: str,
    payload: dict,
    timeout_hours: int
) -> dict:
    """
    Invoke an AgentCore agent using the async callback pattern.
    
    This handles the timeout mismatch between Lambda (15min) and AgentCore (8hr)
    by using wait_for_callback() to suspend until the agent completes.
    """
    # Get callback URL from durable context
    callback_config = context.get_callback_config()
    
    # Dispatch task to agent (quick operation)
    context.step(
        lambda: dispatch_agent_task(
            agent_arn=agent_arn,
            payload={
                **payload,
                'callback_url': callback_config['url'],
                'callback_token': callback_config['token']
            }
        ),
        name=f'{step_name}_dispatch'
    )
    
    # Wait for agent to complete and callback
    result = context.wait_for_callback(
        name=f'{step_name}_await',
        config=WaitForCallbackConfig(
            timeout=Duration.from_hours(timeout_hours)
        )
    )
    
    # If result is an S3 reference, fetch the actual data
    if result.get('artifact_type') == 's3_reference':
        result = context.step(
            lambda: fetch_s3_artifact(result['s3_uri']),
            name=f'{step_name}_fetch_artifact'
        )
    
    return result


def dispatch_agent_task(agent_arn: str, payload: dict) -> dict:
    """Send task to AgentCore via A2A protocol."""
    response = agentcore.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'jsonrpc': '2.0',
            'id': str(uuid.uuid4()),
            'method': 'tasks/send',
            'params': {
                'message': {
                    'role': 'user',
                    'parts': [{'kind': 'text', 'text': json.dumps(payload)}]
                }
            }
        }).encode()
    )
    return json.loads(response['body'].read())


def init_workflow(workflow_id: str, topic: str, parameters: dict) -> dict:
    """Initialize workflow record in DynamoDB."""
    table = dynamodb.Table(WORKFLOW_TABLE)
    item = {
        'workflow_id': workflow_id,
        'topic': topic,
        'parameters': parameters,
        'status': 'RUNNING',
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }
    table.put_item(Item=item)
    return item


def update_workflow_status(workflow_id: str, status: str) -> None:
    """Update workflow status in DynamoDB."""
    table = dynamodb.Table(WORKFLOW_TABLE)
    table.update_item(
        Key={'workflow_id': workflow_id},
        UpdateExpression='SET #status = :status, updated_at = :updated',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':status': status,
            ':updated': datetime.utcnow().isoformat()
        }
    )


def send_approval_request(workflow_id: str, analysis: dict) -> dict:
    """Send approval request notification (SNS, Slack, etc.)."""
    # Implementation depends on notification channel
    # For MVP, could be SNS -> Email or API Gateway WebSocket
    pass


def fetch_s3_artifact(s3_uri: str) -> dict:
    """Fetch artifact from S3."""
    bucket, key = s3_uri.replace('s3://', '').split('/', 1)
    response = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(response['Body'].read())


def finalize_workflow(workflow_id: str, report: dict) -> dict:
    """Store final report and generate presigned URL."""
    key = f'reports/{workflow_id}/final_report.json'
    s3.put_object(
        Bucket=ARTIFACT_BUCKET,
        Key=key,
        Body=json.dumps(report),
        ContentType='application/json'
    )
    
    presigned_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': ARTIFACT_BUCKET, 'Key': key},
        ExpiresIn=86400  # 24 hours
    )
    
    update_workflow_status(workflow_id, 'COMPLETED')
    
    return {'presigned_url': presigned_url}
```

### 4.2 Agent Worker (Strands on AgentCore)

**Container Specification:**
```dockerfile
# agents/researcher/Dockerfile
FROM arm64v8/python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY src/ /app/src/
COPY agent-card.json /app/.well-known/agent-card.json

# Expose protocol ports
EXPOSE 8080  # HTTP invocations
EXPOSE 9000  # A2A protocol
EXPOSE 8000  # MCP tools

# Health check for idle timeout prevention
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Run agent server
CMD ["python", "-m", "src.main"]
```

**Requirements:**
```txt
# agents/researcher/requirements.txt
strands-agents>=1.0.0
strands-agents-tools>=1.0.0
bedrock-agentcore-sdk>=1.0.0
boto3>=1.34.0
httpx>=0.27.0
uvicorn>=0.30.0
fastapi>=0.111.0
```

**Agent Implementation:**
```python
# agents/researcher/src/main.py
import os
import json
import asyncio
import httpx
from datetime import datetime
from strands import Agent
from strands.tools import tool
from strands_tools import web_search, file_read
from bedrock_agentcore import BedrockAgentCoreApp, A2AServer
from fastapi import FastAPI, Request, BackgroundTasks
import boto3

# Configuration
MODEL_ID = os.environ.get('MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
ARTIFACT_BUCKET = os.environ['ARTIFACT_BUCKET']

# Initialize clients
s3 = boto3.client('s3')
bedrock = boto3.client('bedrock-runtime')

# Custom tools for research
@tool
def save_artifact(content: str, artifact_type: str, workflow_id: str) -> dict:
    """Save large content to S3 and return reference."""
    key = f'artifacts/{workflow_id}/{artifact_type}_{datetime.utcnow().isoformat()}.json'
    s3.put_object(
        Bucket=ARTIFACT_BUCKET,
        Key=key,
        Body=content,
        ContentType='application/json'
    )
    return {
        'artifact_type': 's3_reference',
        's3_uri': f's3://{ARTIFACT_BUCKET}/{key}'
    }


@tool
def search_documents(query: str, sources: list[str] = None) -> list[dict]:
    """Search internal documents and web sources."""
    # Combine web search with any configured document sources
    results = []
    
    # Web search via MCP
    web_results = web_search(query, max_results=10)
    results.extend(web_results)
    
    # Add document search if sources configured
    # (Implementation depends on document store)
    
    return results


# Define the Researcher Agent
researcher_agent = Agent(
    name="Researcher",
    description="Gathers and synthesizes information from multiple sources on a given topic.",
    model=MODEL_ID,
    tools=[web_search, file_read, search_documents, save_artifact],
    system_prompt="""You are a research specialist. Your task is to:
1. Understand the research topic and parameters
2. Search multiple sources for relevant information
3. Extract key facts, data, and insights
4. Organize findings into a structured format
5. Save large outputs as artifacts

Always cite sources and note confidence levels for each finding.
When research is complete, format results as JSON with sections:
- summary: Brief overview of findings
- key_findings: List of main discoveries
- sources: Citations and references
- data_points: Any quantitative information
- gaps: Areas needing more research
"""
)


# Create FastAPI app for HTTP endpoints
app = FastAPI()

# Wrap with AgentCore
agentcore_app = BedrockAgentCoreApp()


@app.get("/ping")
async def ping():
    """Health endpoint - returns HealthyBusy to prevent idle timeout."""
    return {"status": "HealthyBusy"}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """Agent discovery endpoint."""
    return {
        "name": "researcher-agent",
        "version": "1.0.0",
        "description": "Research specialist agent for gathering and synthesizing information",
        "capabilities": {
            "research": {
                "description": "Gather information on a topic from multiple sources",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "parameters": {"type": "object"},
                        "workflow_id": {"type": "string"}
                    },
                    "required": ["topic", "workflow_id"]
                }
            }
        },
        "communication": {
            "protocol": "A2A",
            "transport": "HTTP-JSON-RPC",
            "endpoints": [{"port": 9000, "path": "/"}]
        },
        "authentication": {
            "type": "AWS_SigV4",
            "service": "bedrock-agentcore"
        }
    }


@app.post("/invocations")
async def invoke(request: Request, background_tasks: BackgroundTasks):
    """Main invocation endpoint."""
    body = await request.json()
    
    # Extract task details
    params = body.get('params', {})
    message = params.get('message', {})
    parts = message.get('parts', [])
    
    # Parse the payload from text part
    payload = None
    for part in parts:
        if part.get('kind') == 'text':
            try:
                payload = json.loads(part['text'])
            except json.JSONDecodeError:
                payload = {'query': part['text']}
            break
    
    if not payload:
        return {"error": "No valid payload found"}
    
    # Check for callback URL (async pattern)
    callback_url = payload.get('callback_url')
    callback_token = payload.get('callback_token')
    
    if callback_url:
        # Async execution - run in background and callback when done
        background_tasks.add_task(
            execute_and_callback,
            payload,
            callback_url,
            callback_token
        )
        return {
            "jsonrpc": "2.0",
            "id": body.get('id'),
            "result": {
                "status": "accepted",
                "message": "Task queued for async execution"
            }
        }
    else:
        # Sync execution - wait for result
        result = await execute_research(payload)
        return {
            "jsonrpc": "2.0",
            "id": body.get('id'),
            "result": result
        }


async def execute_research(payload: dict) -> dict:
    """Execute research task."""
    topic = payload.get('topic', payload.get('query', ''))
    parameters = payload.get('parameters', {})
    workflow_id = payload.get('workflow_id', 'unknown')
    
    # Build the research prompt
    prompt = f"""Research the following topic: {topic}

Parameters and constraints:
{json.dumps(parameters, indent=2)}

Gather comprehensive information, cite all sources, and organize findings."""

    # Run the agent
    response = researcher_agent(prompt)
    
    # If response is large, save to S3
    response_str = str(response)
    if len(response_str) > 200000:  # ~200KB
        artifact = save_artifact(
            content=response_str,
            artifact_type='research_results',
            workflow_id=workflow_id
        )
        return artifact
    
    # Parse and return structured response
    try:
        return json.loads(response_str)
    except json.JSONDecodeError:
        return {"raw_response": response_str}


async def execute_and_callback(
    payload: dict,
    callback_url: str,
    callback_token: str
):
    """Execute task and send callback to Durable Lambda."""
    try:
        result = await execute_research(payload)
        
        # Send success callback
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json={
                    'token': callback_token,
                    'status': 'SUCCESS',
                    'result': result
                },
                headers={
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )
    except Exception as e:
        # Send failure callback
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json={
                    'token': callback_token,
                    'status': 'FAILURE',
                    'error': str(e)
                },
                headers={
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )


# A2A server on port 9000
a2a_server = A2AServer(researcher_agent, port=9000)


if __name__ == "__main__":
    import uvicorn
    from threading import Thread
    
    # Start A2A server in background thread
    a2a_thread = Thread(target=a2a_server.run, daemon=True)
    a2a_thread.start()
    
    # Run main HTTP server
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

**Agent Card (/.well-known/agent-card.json):**
```json
{
  "name": "researcher-agent",
  "version": "1.0.0",
  "description": "Research specialist agent for gathering and synthesizing information from multiple sources",
  "author": "AgentOrchestration",
  "capabilities": {
    "research": {
      "description": "Gather comprehensive information on a topic",
      "inputSchema": {
        "type": "object",
        "properties": {
          "topic": {
            "type": "string",
            "description": "The research topic or question"
          },
          "parameters": {
            "type": "object",
            "description": "Additional parameters like depth, sources, constraints"
          },
          "workflow_id": {
            "type": "string",
            "description": "Parent workflow identifier for artifact tracking"
          },
          "callback_url": {
            "type": "string",
            "description": "URL to callback when async task completes"
          },
          "callback_token": {
            "type": "string",
            "description": "Token for callback authentication"
          }
        },
        "required": ["topic", "workflow_id"]
      }
    }
  },
  "communication": {
    "protocol": "A2A",
    "transport": "HTTP-JSON-RPC",
    "encoding": "json",
    "endpoints": [
      {
        "url": "/",
        "port": 9000
      }
    ]
  },
  "authentication": {
    "type": "AWS_SigV4",
    "service": "bedrock-agentcore"
  },
  "tools": [
    "web_search",
    "file_read",
    "search_documents",
    "save_artifact"
  ]
}
```

### 4.3 Callback Handler Lambda

The Durable Lambda callback mechanism requires an API Gateway endpoint to receive callbacks from AgentCore agents.

```python
# callback/handler.py
import json
import boto3
import os

lambda_client = boto3.client('lambda')

CONTROLLER_FUNCTION = os.environ['CONTROLLER_FUNCTION_NAME']


def handler(event, context):
    """
    Receive callbacks from AgentCore agents and forward to Durable Lambda.
    
    Expects POST with:
    {
        "token": "<callback_token>",
        "status": "SUCCESS" | "FAILURE",
        "result": { ... } | null,
        "error": "<error_message>" | null
    }
    """
    body = json.loads(event.get('body', '{}'))
    
    token = body.get('token')
    status = body.get('status', 'SUCCESS')
    result = body.get('result')
    error = body.get('error')
    
    if not token:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing callback token'})
        }
    
    try:
        if status == 'SUCCESS':
            lambda_client.send_durable_execution_callback_success(
                functionName=CONTROLLER_FUNCTION,
                callbackToken=token,
                output=json.dumps(result)
            )
        else:
            lambda_client.send_durable_execution_callback_failure(
                functionName=CONTROLLER_FUNCTION,
                callbackToken=token,
                error={
                    'errorCode': 'AgentExecutionError',
                    'errorMessage': error or 'Unknown error'
                }
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'callback_delivered'})
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

---

## 5. Infrastructure (CDK)

```python
# infrastructure/app.py
from aws_cdk import (
    App, Stack, Duration, RemovalPolicy,
    aws_lambda as lambda_,
    aws_lambda_python_alpha as lambda_python,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    aws_logs as logs,
)
from constructs import Construct


class AgentOrchestrationStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        # S3 bucket for artifacts
        artifact_bucket = s3.Bucket(
            self, "ArtifactBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )
        
        # DynamoDB table for workflow metadata
        workflow_table = dynamodb.Table(
            self, "WorkflowTable",
            partition_key=dynamodb.Attribute(
                name="workflow_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )
        
        # Add GSI for status queries
        workflow_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            ),
        )
        
        # Build agent container images
        researcher_image = ecr_assets.DockerImageAsset(
            self, "ResearcherImage",
            directory="agents/researcher",
            platform=ecr_assets.Platform.LINUX_ARM64,
        )
        
        analyst_image = ecr_assets.DockerImageAsset(
            self, "AnalystImage",
            directory="agents/analyst",
            platform=ecr_assets.Platform.LINUX_ARM64,
        )
        
        writer_image = ecr_assets.DockerImageAsset(
            self, "WriterImage",
            directory="agents/writer",
            platform=ecr_assets.Platform.LINUX_ARM64,
        )
        
        # Note: AgentCore Runtime resources would be created via 
        # bedrock-agentcore CLI or custom resource, as CDK L2 constructs
        # may not exist yet. Placeholder ARNs shown.
        
        # Durable Lambda Controller
        controller_role = iam.Role(
            self, "ControllerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )
        
        # Add durable execution permissions
        controller_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "lambda:CheckpointDurableExecution",
                "lambda:GetDurableExecutionState",
                "lambda:ListDurableExecutions",
            ],
            resources=[f"arn:aws:lambda:{self.region}:{self.account}:function:*"],
        ))
        
        # Add AgentCore invocation permissions
        controller_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock-agentcore:InvokeAgentRuntime",
                "bedrock-agentcore:GetAgentRuntime",
            ],
            resources=["*"],  # Scope to specific ARNs in production
        ))
        
        # Add S3 and DynamoDB permissions
        artifact_bucket.grant_read_write(controller_role)
        workflow_table.grant_read_write_data(controller_role)
        
        # Add X-Ray permissions
        controller_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "xray:PutTraceSegments",
                "xray:PutTelemetryRecords",
            ],
            resources=["*"],
        ))
        
        controller_fn = lambda_python.PythonFunction(
            self, "ControllerFunction",
            entry="controller",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            memory_size=1024,
            timeout=Duration.minutes(15),
            role=controller_role,
            environment={
                "ARTIFACT_BUCKET": artifact_bucket.bucket_name,
                "WORKFLOW_TABLE": workflow_table.table_name,
                "RESEARCHER_AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:agent-runtime/researcher",
                "ANALYST_AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:agent-runtime/analyst",
                "WRITER_AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:agent-runtime/writer",
            },
            tracing=lambda_.Tracing.ACTIVE,
            # Enable durable execution (syntax TBD based on actual CDK support)
            # durable_execution=lambda_.DurableExecutionConfig(
            #     enabled=True,
            #     state_retention_days=14
            # ),
        )
        
        # Callback Handler Lambda
        callback_fn = lambda_python.PythonFunction(
            self, "CallbackFunction",
            entry="callback",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={
                "CONTROLLER_FUNCTION_NAME": controller_fn.function_name,
            },
        )
        
        # Grant callback permissions
        callback_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "lambda:SendDurableExecutionCallbackSuccess",
                "lambda:SendDurableExecutionCallbackFailure",
            ],
            resources=[controller_fn.function_arn + ":*"],
        ))
        
        # API Gateway
        api = apigw.RestApi(
            self, "OrchestrationApi",
            rest_api_name="Agent Orchestration API",
            deploy_options=apigw.StageOptions(
                stage_name="v1",
                tracing_enabled=True,
                logging_level=apigw.MethodLoggingLevel.INFO,
            ),
        )
        
        # POST /workflows - Start new workflow
        workflows = api.root.add_resource("workflows")
        workflows.add_method(
            "POST",
            apigw.LambdaIntegration(controller_fn),
            authorization_type=apigw.AuthorizationType.IAM,
        )
        
        # GET /workflows/{id} - Get workflow status
        workflow = workflows.add_resource("{workflow_id}")
        workflow.add_method(
            "GET",
            apigw.LambdaIntegration(controller_fn),
            authorization_type=apigw.AuthorizationType.IAM,
        )
        
        # POST /callbacks - Receive agent callbacks
        callbacks = api.root.add_resource("callbacks")
        callbacks.add_method(
            "POST",
            apigw.LambdaIntegration(callback_fn),
            # Less restrictive auth for agent callbacks
            authorization_type=apigw.AuthorizationType.NONE,
        )


app = App()
AgentOrchestrationStack(app, "AgentOrchestrationStack")
app.synth()
```

---

## 6. Deployment Procedure

### 6.1 Prerequisites

```bash
# Required tools
node --version  # v18+
python --version  # 3.11+
docker --version  # For container builds
aws --version  # AWS CLI v2

# Required AWS access
aws sts get-caller-identity  # Verify credentials

# Install CDK
npm install -g aws-cdk

# Install AgentCore CLI
pip install bedrock-agentcore-starter-toolkit
```

### 6.2 Deployment Steps

```bash
# 1. Clone and setup
git clone <repo>
cd serverless-durable-agents

# 2. Install dependencies
pip install -r requirements.txt
npm install

# 3. Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT/REGION

# 4. Deploy AgentCore agents (manual step until CDK support)
cd agents/researcher
agentcore configure -e src/main.py
agentcore deploy --name researcher-agent

cd ../analyst
agentcore configure -e src/main.py
agentcore deploy --name analyst-agent

cd ../writer
agentcore configure -e src/main.py
agentcore deploy --name writer-agent

# 5. Update CDK with agent ARNs
# Edit infrastructure/app.py with actual ARNs from step 4

# 6. Deploy infrastructure
cd infrastructure
cdk deploy

# 7. Note outputs
# API endpoint, bucket name, table name
```

### 6.3 Testing

```bash
# Start a workflow
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Impact of quantum computing on cryptography",
    "parameters": {
      "depth": "comprehensive",
      "sources": ["academic", "industry"],
      "word_limit": 5000
    }
  }'

# Response: {"workflow_id": "abc-123", "status": "accepted"}

# Check status
curl https://API_ID.execute-api.REGION.amazonaws.com/v1/workflows/abc-123

# Response: {"workflow_id": "abc-123", "status": "awaiting_approval", ...}

# Approve (via callback endpoint or direct Lambda invocation)
aws lambda invoke \
  --function-name ControllerFunction \
  --cli-binary-format raw-in-base64-out \
  --payload '{"action": "approve", "workflow_id": "abc-123", "approved": true}' \
  response.json
```

---

## 7. Observability

### 7.1 CloudWatch Dashboard

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "title": "Workflow Executions",
        "metrics": [
          ["AWS/Lambda", "Invocations", "FunctionName", "ControllerFunction"],
          [".", "Errors", ".", "."],
          [".", "Duration", ".", ".", {"stat": "p99"}]
        ]
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "Durable Operations",
        "metrics": [
          ["AWS/Lambda", "DurableCheckpoints", "FunctionName", "ControllerFunction"],
          [".", "DurableWaits", ".", "."],
          [".", "DurableCallbacks", ".", "."]
        ]
      }
    },
    {
      "type": "log",
      "properties": {
        "title": "Workflow Logs",
        "query": "SOURCE '/aws/lambda/ControllerFunction' | filter @message like /workflow_id/ | limit 100"
      }
    }
  ]
}
```

### 7.2 X-Ray Tracing

Enable trace propagation in all components:

```python
# In controller
import aws_xray_sdk.core as xray
from aws_xray_sdk.core import patch_all

patch_all()

# When invoking AgentCore
xray.begin_subsegment('invoke_agent')
# ... invoke ...
xray.end_subsegment()
```

### 7.3 Structured Logging

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "workflow_step_completed",
    workflow_id=workflow_id,
    step_name="research_phase",
    duration_ms=elapsed,
    artifact_size=len(result)
)
```

---

## 8. Security Considerations

| Concern | Mitigation |
|---------|------------|
| Agent-to-controller auth | SigV4 signing for all AgentCore invocations |
| Callback spoofing | Unique tokens per callback, validated by Lambda |
| Data in transit | TLS 1.2+ enforced on all endpoints |
| Data at rest | S3 server-side encryption, DynamoDB encryption |
| Secrets | Secrets Manager for API keys, OAuth tokens |
| Agent isolation | MicroVM per session in AgentCore |
| Privilege escalation | Least-privilege IAM roles per component |
| Input validation | JSON Schema validation at API Gateway |

---

## 9. MVP Milestones

| Phase | Deliverable | Duration | Dependencies |
|-------|-------------|----------|--------------|
| 1 | Core infrastructure (S3, DynamoDB, API GW) | 2 days | CDK setup |
| 2 | Durable Lambda controller (basic flow) | 3 days | Phase 1 |
| 3 | Researcher agent on AgentCore | 2 days | Phase 1 |
| 4 | Analyst agent on AgentCore | 1 day | Phase 3 |
| 5 | Writer agent on AgentCore | 1 day | Phase 3 |
| 6 | Callback integration | 2 days | Phases 2-5 |
| 7 | Human approval flow | 2 days | Phase 6 |
| 8 | Observability & testing | 2 days | Phase 7 |
| **Total** | **MVP Complete** | **~15 days** | |

---

## 10. Open Questions for Implementation

1. **Durable Lambda CDK Support**: Is there an L2 construct for durable execution configuration, or do we need escape hatches?

2. **AgentCore CDK/CloudFormation**: Are there CDK constructs for AgentCore Runtime, or is CLI the only deployment path?

3. **Callback URL Generation**: How does the Durable SDK expose the callback URL/token for external systems?

4. **Regional Availability**: Confirm us-east-1 has both Durable Lambda and AgentCore GA.

5. **Cold Start Budget**: What's acceptable latency for the demo? May need provisioned concurrency.

---

## Appendix A: Project Structure

```
serverless-durable-agents/
├── README.md
├── requirements.txt
├── package.json
├── cdk.json
│
├── controller/
│   ├── __init__.py
│   ├── handler.py
│   ├── utils.py
│   └── requirements.txt
│
├── callback/
│   ├── __init__.py
│   ├── handler.py
│   └── requirements.txt
│
├── agents/
│   ├── researcher/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── agent-card.json
│   │   └── src/
│   │       ├── __init__.py
│   │       ├── main.py
│   │       └── tools.py
│   │
│   ├── analyst/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── agent-card.json
│   │   └── src/
│   │       └── main.py
│   │
│   └── writer/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── agent-card.json
│       └── src/
│           └── main.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── app.py
│   └── requirements.txt
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── docs/
    ├── architecture.md
    └── runbook.md
```

---

## Appendix B: Environment Variables

| Variable | Component | Description |
|----------|-----------|-------------|
| `ARTIFACT_BUCKET` | Controller, Agents | S3 bucket for large artifacts |
| `WORKFLOW_TABLE` | Controller | DynamoDB table name |
| `RESEARCHER_AGENT_ARN` | Controller | AgentCore runtime ARN |
| `ANALYST_AGENT_ARN` | Controller | AgentCore runtime ARN |
| `WRITER_AGENT_ARN` | Controller | AgentCore runtime ARN |
| `MODEL_ID` | Agents | Bedrock model ID |
| `CALLBACK_API_URL` | Agents | API Gateway callback endpoint |

---

*Document generated for Claude Code implementation. All code patterns are illustrative and should be validated against current SDK documentation.*
