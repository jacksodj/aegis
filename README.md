# aegis

Serverless agent orchestration on native AWS using durable Lambda functions and the AgentCore runtime.

aegis is an MVP of a serverless, durable multi-agent platform. A controller Lambda runs a research-report workflow as a series of checkpointed steps and hands the work to three specialist agents (researcher, analyst, writer) that run as containers on Amazon Bedrock AgentCore Runtime. Agents report back through a callback Lambda, and a human approval gate sits between analysis and writing. There are no servers to manage: state lives in DynamoDB and S3.

The full design is in [docs/serverless_durable_agent_orchestration_spec.md](docs/serverless_durable_agent_orchestration_spec.md), and the build plan is in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Setup

After cloning, run `scripts/setup-hooks.sh` to turn on the secret-scanning git hooks.

## How it works

1. A client calls `POST /workflows` on the HTTP API with a research topic.
2. The **controller** (`controller/`) records the workflow in DynamoDB and dispatches the researcher agent with a callback token.
3. Each **agent** (`agents/<name>/`) does its part with a Bedrock model and posts its result to `POST /callbacks/{workflow_id}`.
4. The **callback** Lambda (`callback/`) validates the result, stores it, and lets the workflow continue: researcher, then analyst.
5. The workflow pauses for a person to approve the analysis at `POST /approve/{workflow_id}` (24-hour timeout by default).
6. The writer agent produces the report, which lands in the S3 artifact bucket. `GET /workflows/{workflow_id}` reports progress at any point.

Payloads over about 200 KB travel between steps as S3 references rather than inline.

### Components

| Piece | What it is |
|---|---|
| `controller/` | The orchestrator Lambda (`handler.api_handler`). Its `DurableContext` (`step`, `wait`, `wait_for_callback`) simulates the AWS Lambda durable execution SDK so the workflow code is written the way the real SDK expects; swap in the SDK when it is available. |
| `callback/` | The Lambda that receives agent results (`handler.handler`), with unit tests in `test_handler.py`. |
| `agents/researcher`, `agents/analyst`, `agents/writer` | FastAPI services on port 8080 (`/ping`, `/invocations`, an agent card at `/.well-known/agent-card.json`), built as ARM64 containers for AgentCore Runtime. |
| `terraform/` | OpenTofu/Terraform for the AWS side: S3 artifact bucket, DynamoDB workflow table, ECR repositories, both Lambdas, the HTTP API, IAM, CloudWatch logs, and an EventBridge rule for workflow events. It also builds and pushes the agent images with a local Docker step. |
| `terraform/modules/`, `terraform/examples/` | Reusable `agent` and `lambda` modules and a larger example deployment that uses them. The root module does not use them. |
| `infrastructure/` | A pointer to `terraform/` (an earlier CDK plan was replaced). |
| `docs/` | The specification, the implementation plan, and `docs/agents/` (how issues and triage work in this repo). |

The Terraform does not create the AgentCore runtimes themselves: the agent ARNs in `terraform/locals.tf` are placeholders until the agents are deployed to AgentCore separately.

## Running it

**Tests.** The callback Lambda has unit tests that mock AWS:

```bash
cd callback
pip install -r requirements.txt
WORKFLOW_TABLE=test ARTIFACT_BUCKET=test AWS_DEFAULT_REGION=us-east-1 python -m pytest test_handler.py
```

**An agent, locally.** `agents/researcher` has a Makefile and Docker Compose file: copy `.env.example` to `.env`, then `make build`, `make run`, and `make test` (which calls the running container on `localhost:8080`).

**Deploy.** From `terraform/`, copy `terraform.tfvars.example` to `terraform.tfvars`, then run `./deploy.sh deploy` (it checks prerequisites and runs init, validate, plan, and apply) or the equivalent `tofu init`, `tofu plan`, `tofu apply`. It needs AWS credentials, the AWS CLI, and Docker. The configuration has no remote state backend, so state stays on the machine that applies it.

## Status

This is an MVP. Known gaps:

- Durable execution is simulated in `controller/handler.py` rather than using the AWS SDK.
- The `.tf` files do not pass `tofu fmt` or `tofu validate` yet. CI reports both on every PR without blocking.
- There is no remote state, no `prevent_destroy` on the bucket or table, and no CI deploy pipeline.
