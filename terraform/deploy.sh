#!/bin/bash
# ============================================================================
# Terraform Deployment Helper Script
# ============================================================================
# This script provides a guided deployment experience for the serverless
# durable agent orchestration platform.
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        print_error "Terraform is not installed. Please install Terraform >= 1.5"
        exit 1
    fi

    TERRAFORM_VERSION=$(terraform version -json | jq -r '.terraform_version')
    print_success "Terraform $TERRAFORM_VERSION found"

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install AWS CLI v2"
        exit 1
    fi

    AWS_VERSION=$(aws --version 2>&1 | awk '{print $1}')
    print_success "$AWS_VERSION found"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_warning "Docker is not installed. Agent image builds will fail."
        print_warning "Install Docker to enable automatic image building."
    else
        if docker ps &> /dev/null; then
            print_success "Docker daemon is running"
        else
            print_warning "Docker daemon is not running. Please start Docker."
            print_warning "Agent image builds will fail without Docker."
        fi
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured or invalid"
        print_error "Please run 'aws configure' or set AWS environment variables"
        exit 1
    fi

    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    CALLER_ARN=$(aws sts get-caller-identity --query Arn --output text)
    print_success "AWS credentials valid: $CALLER_ARN"
    print_info "Account ID: $ACCOUNT_ID"

    echo ""
}

# Function to validate Terraform configuration
validate_terraform() {
    print_info "Validating Terraform configuration..."

    if [ ! -f "versions.tf" ]; then
        print_error "versions.tf not found. Are you in the terraform directory?"
        exit 1
    fi

    # Initialize Terraform
    print_info "Running terraform init..."
    if terraform init -upgrade > /dev/null 2>&1; then
        print_success "Terraform initialized successfully"
    else
        print_error "Terraform initialization failed"
        terraform init -upgrade
        exit 1
    fi

    # Validate configuration
    print_info "Running terraform validate..."
    if terraform validate > /dev/null 2>&1; then
        print_success "Terraform configuration is valid"
    else
        print_error "Terraform validation failed"
        terraform validate
        exit 1
    fi

    echo ""
}

# Function to display plan summary
show_plan_summary() {
    print_info "Generating deployment plan..."

    terraform plan -out=tfplan > /dev/null 2>&1

    # Count resources
    TO_CREATE=$(terraform show -json tfplan | jq '[.resource_changes[] | select(.change.actions[] | contains("create"))] | length')
    TO_UPDATE=$(terraform show -json tfplan | jq '[.resource_changes[] | select(.change.actions[] | contains("update"))] | length')
    TO_DELETE=$(terraform show -json tfplan | jq '[.resource_changes[] | select(.change.actions[] | contains("delete"))] | length')

    echo ""
    print_info "Deployment Plan Summary:"
    echo "  Resources to create: $TO_CREATE"
    echo "  Resources to update: $TO_UPDATE"
    echo "  Resources to delete: $TO_DELETE"
    echo ""
}

# Function to deploy infrastructure
deploy() {
    print_info "Starting deployment..."

    # Apply configuration
    if terraform apply tfplan; then
        print_success "Deployment completed successfully!"
        echo ""
        show_outputs
    else
        print_error "Deployment failed"
        exit 1
    fi
}

# Function to show outputs
show_outputs() {
    print_info "Deployment Outputs:"
    echo ""

    API_ENDPOINT=$(terraform output -raw api_endpoint 2>/dev/null || echo "N/A")
    BUCKET_NAME=$(terraform output -raw artifact_bucket_name 2>/dev/null || echo "N/A")
    TABLE_NAME=$(terraform output -raw workflow_table_name 2>/dev/null || echo "N/A")
    CONTROLLER_NAME=$(terraform output -raw controller_function_name 2>/dev/null || echo "N/A")

    echo "API Endpoint:        $API_ENDPOINT"
    echo "Artifact Bucket:     $BUCKET_NAME"
    echo "Workflow Table:      $TABLE_NAME"
    echo "Controller Function: $CONTROLLER_NAME"
    echo ""

    print_info "Quick Start Commands:"
    echo ""
    echo "# Start a workflow:"
    echo "curl -X POST \"$API_ENDPOINT/workflows\" \\"
    echo "  -H \"Content-Type: application/json\" \\"
    echo "  -d '{\"topic\": \"Your research topic\", \"parameters\": {}}'"
    echo ""
    echo "# View controller logs:"
    echo "aws logs tail $(terraform output -raw controller_log_group_name 2>/dev/null || echo "/aws/lambda/controller") --follow"
    echo ""

    print_info "For all outputs, run: terraform output"
    print_info "For detailed output: terraform output -json | jq"
    echo ""
}

# Function to destroy infrastructure
destroy() {
    print_warning "This will destroy ALL infrastructure resources!"
    print_warning "This includes:"
    echo "  - All workflow data in DynamoDB"
    echo "  - All artifacts in S3"
    echo "  - All Docker images in ECR"
    echo "  - All Lambda functions and API Gateway"
    echo ""

    read -p "Are you sure you want to destroy? Type 'yes' to confirm: " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        print_info "Destroy cancelled"
        exit 0
    fi

    print_info "Destroying infrastructure..."

    if terraform destroy -auto-approve; then
        print_success "Infrastructure destroyed successfully"
    else
        print_error "Destroy failed"
        exit 1
    fi
}

# Main script
main() {
    echo "============================================================================"
    echo "  Serverless Durable Agent Orchestration - Terraform Deployment"
    echo "============================================================================"
    echo ""

    # Parse command line arguments
    ACTION=${1:-deploy}

    case $ACTION in
        check)
            check_prerequisites
            ;;
        validate)
            check_prerequisites
            validate_terraform
            ;;
        plan)
            check_prerequisites
            validate_terraform
            show_plan_summary
            print_info "Review the plan with: terraform show tfplan"
            ;;
        deploy)
            check_prerequisites
            validate_terraform
            show_plan_summary

            read -p "Proceed with deployment? (yes/no): " CONFIRM
            if [ "$CONFIRM" == "yes" ]; then
                deploy
            else
                print_info "Deployment cancelled"
            fi
            ;;
        outputs)
            show_outputs
            ;;
        destroy)
            destroy
            ;;
        *)
            echo "Usage: $0 {check|validate|plan|deploy|outputs|destroy}"
            echo ""
            echo "Commands:"
            echo "  check     - Check prerequisites only"
            echo "  validate  - Validate Terraform configuration"
            echo "  plan      - Generate and show deployment plan"
            echo "  deploy    - Deploy infrastructure (default)"
            echo "  outputs   - Show deployment outputs"
            echo "  destroy   - Destroy all infrastructure"
            echo ""
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
