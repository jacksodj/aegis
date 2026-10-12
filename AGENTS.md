# aegis: agent instructions

aegis is an MVP of serverless, durable multi-agent orchestration on AWS. A controller Lambda runs a research-report workflow (researcher, then analyst, then a human approval gate, then writer) and dispatches each step to an agent container on Amazon Bedrock AgentCore Runtime. Agents post results to a callback Lambda. State lives in DynamoDB (workflow records) and S3 (artifacts and any payload over about 200 KB). The design is `docs/serverless_durable_agent_orchestration_spec.md`; the build plan is `docs/IMPLEMENTATION_PLAN.md`. `README.md` has the architecture walk-through.

This repo is **public**. Never commit AWS account IDs (use `123456789012` in examples), email addresses, local paths, private repo names, or `.tfvars`/`.env` files.

## Layout

- `controller/`: orchestrator Lambda. `handler.py` holds the workflow, the HTTP entry point `api_handler`, and a simulated `DurableContext` (`step`, `wait`, `wait_for_callback`) standing in for the AWS Lambda durable execution SDK; `utils.py` holds the S3, DynamoDB and AgentCore helpers. `example_usage.py` shows the flow.
- `callback/`: Lambda that validates agent results and records them (`handler.handler`). Tests: `callback/test_handler.py`.
- `agents/researcher`, `agents/analyst`, `agents/writer`: FastAPI services (`src/main.py`, tools in `src/tools.py`, `agent-card.json`, `Dockerfile`, own `requirements.txt`). Port 8080 serves `/ping` and `/invocations`; images build for `linux/arm64`. The researcher also has a Makefile, Docker Compose file and `test.sh` for local runs.
- `terraform/`: OpenTofu/Terraform root module (`main.tf`, `variables.tf`, `locals.tf`, `outputs.tf`, `versions.tf`), the `deploy.sh` helper, `modules/agent` and `modules/lambda`, and `examples/complete-deployment.tf` (uses the modules; not wired to the root module).
- `infrastructure/`: a pointer to `terraform/` from when the plan was CDK.
- `docs/`: spec, implementation plan, and `docs/agents/` (issue tracker, triage labels, domain notes).
- `agent-tasks/`: empty placeholder.

## Build, test, run

- **Tests (what CI runs):**
  ```bash
  cd callback && pip install -r requirements.txt
  WORKFLOW_TABLE=test ARTIFACT_BUCKET=test AWS_DEFAULT_REGION=us-east-1 python -m pytest test_handler.py
  ```
  The handler reads `WORKFLOW_TABLE` and `ARTIFACT_BUCKET` at import time, so the tests need them set; boto3 is mocked, so no AWS access is needed.
- **Infra checks:** `tofu fmt -check -recursive` from the root, and `tofu -chdir=<dir> init -backend=false && tofu -chdir=<dir> validate` for each directory with `.tf` files.
- **One agent locally:** `cd agents/researcher && cp .env.example .env`, then `make build`, `make run`, `make test`.
- **Deploy:** owner-run only, from `terraform/` with `./deploy.sh deploy` or `tofu init/plan/apply`. There is no remote state backend and no CI deploy pipeline. Do not run `apply` or `destroy` from a session.

## Conventions

- Python 3.12 for Lambdas (`lambda_runtime`) and CI; the agent images use `python:3.11-slim`. Lambdas and images target ARM64.
- Each component keeps its own `requirements.txt`. CI runs `pip-audit` on every `requirements*.txt` and `bandit` on all Python, so add dependencies to the component that uses them.
- Lambda configuration comes from environment variables set in `terraform/main.tf`. When a handler reads a new variable, add it there too.
- New tests sit beside the code they cover (like `callback/test_handler.py`) and get a step in the `tests` job of `.github/workflows/pr-checks.yml`.
- Run `tofu fmt -recursive` on any `.tf` change. Stateful resources (the artifact bucket, the workflow and agent-state tables, the ECR repositories, SQS queues) need `prevent_destroy = true` before this holds real data.
- Specs and plans go in `docs/`; component READMEs live beside their code. The root holds only `README.md`, `AGENTS.md`, `CLAUDE.md` and tool config.

## Known gaps

- Durable execution is simulated, not the AWS SDK.
- As packaged by `terraform/main.tf`, the controller Lambda would not import: `handler.py` uses a relative import (`from .utils import ...`) but is zipped as a top-level module, and the zips carry no dependencies (`structlog`, `aws-lambda-powertools`).
- The `.tf` files fail `tofu fmt` (5 files) and `tofu validate` (`terraform/modules/agent` passes a list to `fileset()`, which also breaks `examples/`). CI runs these steps with `continue-on-error` until they are fixed; remove it then.
- AgentCore runtimes are not created by the Terraform; the agent ARNs in `terraform/locals.tf` are placeholders.

## Guardrails

The same controls as the owner's other repos. Work with them, not around them.

- After cloning, run `scripts/setup-hooks.sh`. It points git at `.githooks/` (gitleaks scans every commit and push) and installs the pinned gitleaks. The Claude Code hook in `.claude/settings.json` runs it automatically before any commit or push.
- For a gitleaks false positive, add a targeted allowlist entry to `.gitleaks.toml`; commits always go through the hooks (no `--no-verify`).
- Work in a worktree. The main checkout stays on `main`, clean, and read-only for sessions. Before your first edit, call `EnterWorktree` with a name for the work: it cuts a branch from `origin/main` under `.claude/worktrees/` (gitignored). Push that branch and open the PR from it; to rename the branch, use `git branch -m`, never `git switch -c`, which leaves an orphaned branch behind. After the merge, GitHub deletes the remote branch, the Code tab's auto-archive removes a session's worktree, and the next session in the repo sweeps the merged local branch; never use `--force`, `-D`, `reset --hard` or `clean -f` to tidy up.
- `main` is protected: the `tests`, `secrets`, and `vulnerabilities` jobs in `.github/workflows/pr-checks.yml` must pass. Push a branch, open a PR, and merge with `gh pr merge --auto --squash`, including tracker and docs edits. No `--admin`, no force-push to `main`.
- The workflow uses no repository secrets and never `pull_request_target`. Keep the three job names stable; add the project's build and test steps to `tests` with the first build work. The vulnerability steps switch on by themselves when Python requirements, Python code, or npm lockfiles appear; add an audit for any other package manager the project adopts.
- OpenTofu/Terraform: CI runs `tofu fmt`, `tofu validate`, and tflint on any `.tf` files. Destroys and state surgery (`destroy`, `-destroy`, `state rm/push`) never run locally; stateful resources carry `prevent_destroy = true`; real infrastructure with state adopts a reusable deploy workflow (plan, destroy-guard, and the `allow-destroy` label that only the owner adds).
- Anything the owner must do is a `needs-human` issue with a `**Next:**` line, filed when it comes up rather than left in a reply, and closed or rewritten when the Next goes stale (see `docs/agents/issue-tracker.md`). If the effort spans repos, every repo is linked to the effort's private GitHub Project so the band shows the siblings' items. Give each one a Priority (`scripts/issue-field.sh <n> Priority High`). Decisions go to the owner one at a time through AskUserQuestion.
- Roadmap data lives on each issue as organization issue fields: set Horizon (`scripts/issue-field.sh <n> Horizon Now`) when charting a map or triaging a report, file tickets with `--parent` and `--blocked-by`, and leave Start date and Target date to the `roadmap-dates` workflow (see `docs/agents/issue-tracker.md`).
