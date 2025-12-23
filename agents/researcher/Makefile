.PHONY: help build run stop test clean logs shell deploy

# Variables
IMAGE_NAME := researcher-agent
IMAGE_TAG := latest
CONTAINER_NAME := researcher-agent
DOCKER_REGISTRY :=
AWS_ACCOUNT_ID :=
AWS_REGION := us-east-1

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build the Docker image
	@echo "Building Docker image..."
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "Build complete!"

run: ## Run the agent using docker-compose
	@echo "Starting agent..."
	docker-compose up -d
	@echo "Agent started! Waiting for health check..."
	@sleep 5
	@curl -s http://localhost:8080/ping | jq '.' || echo "Agent not ready yet"

stop: ## Stop the running agent
	@echo "Stopping agent..."
	docker-compose down
	@echo "Agent stopped!"

restart: stop run ## Restart the agent

logs: ## Show agent logs
	docker-compose logs -f researcher-agent

test: ## Run tests against the agent
	@echo "Running tests..."
	./test.sh all

test-health: ## Test health endpoint only
	./test.sh health

test-sync: ## Test synchronous invocation
	./test.sh sync

test-async: ## Test asynchronous invocation
	./test.sh async

shell: ## Open a shell in the running container
	docker exec -it $(CONTAINER_NAME) /bin/bash

clean: ## Clean up containers, images, and volumes
	@echo "Cleaning up..."
	docker-compose down -v
	docker rmi $(IMAGE_NAME):$(IMAGE_TAG) 2>/dev/null || true
	@echo "Cleanup complete!"

dev: ## Run in development mode with live reload
	@echo "Starting in development mode..."
	pip install -r requirements.txt
	export ARTIFACT_BUCKET=aegis-artifacts && \
	export MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0 && \
	python -m src.main

install: ## Install Python dependencies
	pip install -r requirements.txt

lint: ## Run linting checks
	@echo "Running linting..."
	pip install flake8 black isort
	flake8 src/ --max-line-length=120 --ignore=E501,W503
	black --check src/
	isort --check-only src/

format: ## Format code
	@echo "Formatting code..."
	pip install black isort
	black src/
	isort src/

# Docker Registry / ECR Commands

login-ecr: ## Login to AWS ECR
	@echo "Logging into ECR..."
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin \
		$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

tag-ecr: build ## Tag image for ECR
	@echo "Tagging image for ECR..."
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) \
		$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME):$(IMAGE_TAG)

push-ecr: login-ecr tag-ecr ## Push image to ECR
	@echo "Pushing to ECR..."
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME):$(IMAGE_TAG)
	@echo "Push complete!"

deploy-agentcore: push-ecr ## Deploy to AgentCore (requires agentcore CLI)
	@echo "Deploying to AgentCore..."
	agentcore deploy \
		--name researcher-agent \
		--image $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(IMAGE_NAME):$(IMAGE_TAG) \
		--port 8080 \
		--health-check /ping
	@echo "Deployment complete!"

# Quick commands

quick-test: build run ## Build, run, and test
	@sleep 5
	@make test
	@make stop

all: build test ## Build and test

# Documentation

docs: ## Generate documentation
	@echo "Agent documentation available at:"
	@echo "  - README.md"
	@echo "  - Agent card: http://localhost:8080/.well-known/agent-card.json"

status: ## Show agent status
	@echo "Checking agent status..."
	@docker-compose ps
	@echo ""
	@curl -s http://localhost:8080/health 2>/dev/null | jq '.' || echo "Agent not running"
