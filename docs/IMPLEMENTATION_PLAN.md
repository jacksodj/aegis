# Serverless Durable Agent Orchestration - Implementation Plan

## Overview

This implementation plan outlines the steps to build an MVP for a serverless, durable agent orchestration platform that combines:
- **AWS Lambda Durable Functions** (controller/orchestrator)
- **Amazon Bedrock AgentCore Runtime** (worker agents)

The demo workflow enables a multi-agent research report generation pipeline with human-in-the-loop approval.

---

## Phase 1: Project Setup & Core Infrastructure

### 1.1 Project Initialization

Create the project structure:

```
serverless-durable-agents/
├── README.md
├── requirements.txt
├── package.json
├── cdk.json
├── controller/
├── callback/
├── agents/
│   ├── researcher/
│   ├── analyst/
│   └── writer/
├── infrastructure/
└── tests/
```

**Tasks:**
- [ ] Initialize git repository
- [ ] Create Python virtual environment
- [ ] Install CDK and dependencies (`npm install -g aws-cdk`)
- [ ] Install Python dependencies (`pip install aws-cdk-lib boto3 strands-agents`)
- [ ] Bootstrap CDK (`cdk bootstrap aws://ACCOUNT/REGION`)
- [ ] Create `cdk.json` configuration

### 1.2 Core Infrastructure (CDK Stack)

File: `infrastructure/app.py`

**Resources to create:**
- [ ] **S3 Bucket** (`ArtifactBucket`)
  - Versioned
  - S3-managed encryption
  - Block public access
  - Auto-delete objects for dev environment

- [ ] **DynamoDB Table** (`WorkflowTable`)
  - Partition key: `workflow_id` (String)
  - Billing: Pay-per-request
  - TTL attribute: `ttl`
  - GSI on `status` + `created_at` for status queries

- [ ] **API Gateway** (REST API)
  - `POST /workflows` - Start new workflow
  - `GET /workflows/{workflow_id}` - Get workflow status
  - `POST /callbacks` - Receive agent callbacks
  - Enable X-Ray tracing
  - IAM authorization for workflow endpoints

---

## Phase 2: Durable Lambda Controller

### 2.1 Controller Lambda Setup

File: `controller/handler.py`

**Dependencies (`controller/requirements.txt`):**
```
aws-durable-execution-sdk-python
boto3>=1.34.0
```

**IAM Permissions Required:**
- [ ] `lambda:CheckpointDurableExecution`
- [ ] `lambda:GetDurableExecutionState`
- [ ] `lambda:ListDurableExecutions`
- [ ] `bedrock-agentcore:InvokeAgentRuntime`
- [ ] `bedrock-agentcore:GetAgentRuntime`
- [ ] `s3:PutObject`, `s3:GetObject` on artifact bucket
- [ ] `dynamodb:PutItem`, `dynamodb:GetItem`, `dynamodb:UpdateItem`, `dynamodb:Query`
- [ ] `xray:PutTraceSegments`, `xray:PutTelemetryRecords`
- [ ] `events:PutEvents`

### 2.2 Controller Implementation

**Core workflow steps:**

1. **`init_workflow`** - Create DynamoDB record with workflow metadata
2. **`research_phase`** - Invoke Researcher agent via async callback pattern
3. **`analysis_phase`** - Invoke Analyst agent with research results
4. **`send_approval_request`** - Notify for human approval
5. **`await_human_approval`** - `wait_for_callback()` for approval
6. **`writing_phase`** - Invoke Writer agent (if approved)
7. **`finalize_workflow`** - Store final report, generate presigned URL

**Key functions to implement:**
- [ ] `handler()` - Main durable workflow decorated with `@durable_execution`
- [ ] `invoke_agent_with_callback()` - Async agent invocation pattern
- [ ] `dispatch_agent_task()` - A2A JSON-RPC invocation
- [ ] `init_workflow()` - DynamoDB record creation
- [ ] `update_workflow_status()` - Status updates
- [ ] `send_approval_request()` - Notification dispatch (SNS/Slack/Email)
- [ ] `fetch_s3_artifact()` - Retrieve large artifacts from S3
- [ ] `finalize_workflow()` - Report storage and URL generation

### 2.3 Callback Configuration

The durable context provides `get_callback_config()` which returns:
- `callback_url` - API Gateway endpoint for agent callbacks
- `callback_token` - Unique token for authentication

**Configuration:**
```yaml
Runtime: python3.12
Architecture: arm64
MemorySize: 1024 MB
Timeout: 15 minutes
DurableExecution:
  Enabled: true
  StateRetentionDays: 14
  MaxOperations: 3000
```

---

## Phase 3: Researcher Agent

### 3.1 Container Setup

File: `agents/researcher/Dockerfile`

**Base image:** `arm64v8/python:3.11-slim` (ARM64/Graviton required)

**Ports:**
- `8080` - HTTP invocations
- `9000` - A2A protocol
- `8000` - MCP tools

### 3.2 Agent Implementation

File: `agents/researcher/src/main.py`

**Components:**
- [ ] **Strands Agent** with system prompt for research tasks
- [ ] **FastAPI app** for HTTP endpoints
- [ ] **A2A Server** on port 9000
- [ ] **Health check** (`/ping` returning `HealthyBusy`)
- [ ] **Agent card** at `/.well-known/agent-card.json`

**Tools to implement:**
- [ ] `save_artifact()` - Save large content to S3
- [ ] `search_documents()` - Combined web + document search

**Endpoints:**
- [ ] `GET /ping` - Health check
- [ ] `GET /.well-known/agent-card.json` - Agent discovery
- [ ] `POST /invocations` - Main task handler

**Async execution pattern:**
- Check for `callback_url` in payload
- If present: queue task in background, return immediately
- Execute research, then POST results to callback URL

### 3.3 Agent Card

File: `agents/researcher/agent-card.json`

Define:
- Agent name, version, description
- Capabilities schema (research task input)
- Communication protocol (A2A, HTTP-JSON-RPC)
- Authentication (AWS_SigV4)
- Available tools

---

## Phase 4: Analyst Agent

### 4.1 Container Setup

File: `agents/analyst/Dockerfile`

Same structure as Researcher agent with ARM64 base.

### 4.2 Agent Implementation

File: `agents/analyst/src/main.py`

**Differences from Researcher:**
- System prompt focused on synthesis and analysis
- Input: Research results from Researcher agent
- Output: Structured analysis with key insights

**Tools:**
- [ ] `save_artifact()` - S3 artifact storage
- [ ] Analysis-specific tools as needed

---

## Phase 5: Writer Agent

### 5.1 Container Setup

File: `agents/writer/Dockerfile`

Same ARM64 container structure.

### 5.2 Agent Implementation

File: `agents/writer/src/main.py`

**Differences:**
- System prompt for report writing
- Input: Analysis results + approval feedback
- Output: Formatted final report

**Tools:**
- [ ] `save_artifact()` - Store final report to S3

---

## Phase 6: Callback Handler

### 6.1 Lambda Implementation

File: `callback/handler.py`

**Purpose:** Receive callbacks from AgentCore agents and forward to Durable Lambda.

**Input format:**
```json
{
  "token": "<callback_token>",
  "status": "SUCCESS" | "FAILURE",
  "result": { ... },
  "error": "<error_message>"
}
```

**Implementation:**
- [ ] Parse callback body
- [ ] Validate token exists
- [ ] Call `send_durable_execution_callback_success()` or `send_durable_execution_callback_failure()`
- [ ] Return appropriate HTTP response

**IAM Permissions:**
- [ ] `lambda:SendDurableExecutionCallbackSuccess`
- [ ] `lambda:SendDurableExecutionCallbackFailure`

### 6.2 API Gateway Integration

- Endpoint: `POST /callbacks`
- Authorization: None (agents use token-based auth)
- Lambda integration to Callback function

---

## Phase 7: Human Approval Flow

### 7.1 Approval Request

Implement `send_approval_request()` in controller:

**Options:**
- [ ] SNS → Email notification
- [ ] SNS → Lambda → Slack webhook
- [ ] WebSocket via API Gateway (real-time)

**Notification content:**
- Workflow ID
- Topic summary
- Analysis highlights
- Approval link/instructions

### 7.2 Approval Submission

**Option A: Direct Lambda invocation**
```bash
aws lambda invoke --function-name ControllerFunction \
  --payload '{"action": "approve", "workflow_id": "xxx", "approved": true}'
```

**Option B: API endpoint**
- `POST /workflows/{workflow_id}/approve`
- Body: `{"approved": true, "feedback": "..."}`

### 7.3 Durable Wait Configuration

```python
approval = context.wait_for_callback(
    name='await_human_approval',
    config=WaitForCallbackConfig(
        timeout=Duration.from_hours(24)
    )
)
```

---

## Phase 8: Observability & Testing

### 8.1 CloudWatch Setup

- [ ] Create CloudWatch dashboard
- [ ] Configure metrics widgets:
  - Lambda invocations, errors, p99 duration
  - Durable checkpoints, waits, callbacks
- [ ] Configure log insights queries

### 8.2 X-Ray Tracing

- [ ] Enable X-Ray in all Lambda functions
- [ ] Patch boto3 clients with X-Ray SDK
- [ ] Create subsegments for agent invocations

### 8.3 Structured Logging

- [ ] Install `structlog`
- [ ] Implement consistent log format with workflow_id, step_name, duration

### 8.4 Testing

**Unit tests (`tests/unit/`):**
- [ ] Controller workflow logic
- [ ] Agent task handling
- [ ] Callback processing

**Integration tests (`tests/integration/`):**
- [ ] Controller → AgentCore invocation
- [ ] Agent → Callback flow
- [ ] S3 artifact storage/retrieval

**E2E tests (`tests/e2e/`):**
- [ ] Full workflow execution
- [ ] Approval flow
- [ ] Error handling and recovery

---

## Deployment Steps

### Step 1: Deploy Core Infrastructure

```bash
cd infrastructure
cdk deploy --require-approval never
```

### Step 2: Deploy AgentCore Agents

```bash
# For each agent
cd agents/researcher
agentcore configure -e src/main.py
agentcore deploy --name researcher-agent

# Repeat for analyst and writer
```

### Step 3: Update Controller with Agent ARNs

Edit `infrastructure/app.py` with actual ARNs from AgentCore deployment.

### Step 4: Redeploy Stack

```bash
cd infrastructure
cdk deploy
```

### Step 5: Verify Deployment

```bash
# Test workflow creation
curl -X POST https://API_ID.execute-api.REGION.amazonaws.com/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"topic": "Test topic", "parameters": {}}'
```

---

## Open Questions to Resolve

1. **Durable Lambda CDK Support**: Verify L2 construct availability or implement escape hatches
2. **AgentCore CDK**: Confirm if CDK constructs exist or CLI-only deployment
3. **Callback URL Generation**: Test `context.get_callback_config()` behavior
4. **Regional Availability**: Confirm us-east-1 has both Durable Lambda and AgentCore
5. **Cold Start**: Evaluate need for provisioned concurrency

---

## Implementation Sequence Summary

| Step | Component | Files | Est. Effort |
|------|-----------|-------|-------------|
| 1 | Project setup | Root configs | Low |
| 2 | CDK infrastructure | `infrastructure/app.py` | Medium |
| 3 | Controller Lambda | `controller/handler.py` | High |
| 4 | Callback Lambda | `callback/handler.py` | Low |
| 5 | Researcher Agent | `agents/researcher/` | Medium |
| 6 | Analyst Agent | `agents/analyst/` | Low |
| 7 | Writer Agent | `agents/writer/` | Low |
| 8 | Integration testing | `tests/` | Medium |
| 9 | Observability | Dashboard, logging | Low |

---

## Environment Variables Reference

| Variable | Component | Description |
|----------|-----------|-------------|
| `ARTIFACT_BUCKET` | Controller, Agents | S3 bucket for large artifacts |
| `WORKFLOW_TABLE` | Controller | DynamoDB table name |
| `RESEARCHER_AGENT_ARN` | Controller | AgentCore runtime ARN |
| `ANALYST_AGENT_ARN` | Controller | AgentCore runtime ARN |
| `WRITER_AGENT_ARN` | Controller | AgentCore runtime ARN |
| `MODEL_ID` | Agents | Bedrock model ID (claude-3-5-sonnet) |
| `CALLBACK_API_URL` | Agents | API Gateway callback endpoint |
| `CONTROLLER_FUNCTION_NAME` | Callback | Target durable function name |
