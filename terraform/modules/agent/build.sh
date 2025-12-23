#!/bin/bash
# Docker Build and Push Script for Agent Module
# This script builds Docker images and pushes them to Amazon ECR
# Supports ARM64 builds for AWS Graviton processors

set -e  # Exit on error
set -o pipefail  # Catch errors in pipes

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
SOURCE_DIR="${1:?Source directory is required}"
REPOSITORY_URL="${2:?Repository URL is required}"
IMAGE_TAG="${3:-latest}"
AWS_REGION="${4:-us-east-1}"
PLATFORM="${5:-linux/amd64}"
BUILD_ARGS_JSON="${6:-{}}"
DOCKERFILE_PATH="${7:-Dockerfile}"
ADDITIONAL_TAGS="${8:-}"

log_info "Starting Docker build process..."
log_info "Source Directory: $SOURCE_DIR"
log_info "Repository URL: $REPOSITORY_URL"
log_info "Image Tag: $IMAGE_TAG"
log_info "AWS Region: $AWS_REGION"
log_info "Platform: $PLATFORM"
log_info "Dockerfile: $DOCKERFILE_PATH"

# Validate source directory
if [[ ! -d "$SOURCE_DIR" ]]; then
    log_error "Source directory does not exist: $SOURCE_DIR"
    exit 1
fi

# Validate Dockerfile exists
DOCKERFILE_FULL_PATH="$SOURCE_DIR/$DOCKERFILE_PATH"
if [[ ! -f "$DOCKERFILE_FULL_PATH" ]]; then
    log_error "Dockerfile not found: $DOCKERFILE_FULL_PATH"
    exit 1
fi

# Change to source directory
cd "$SOURCE_DIR"
log_info "Changed to directory: $(pwd)"

# Parse build args from JSON
BUILD_ARGS=""
if [[ "$BUILD_ARGS_JSON" != "{}" ]]; then
    log_info "Parsing build arguments..."
    while IFS= read -r line; do
        key=$(echo "$line" | jq -r '.key')
        value=$(echo "$line" | jq -r '.value')
        BUILD_ARGS="$BUILD_ARGS --build-arg $key=$value"
        log_info "  Build arg: $key=$value"
    done < <(echo "$BUILD_ARGS_JSON" | jq -c 'to_entries[] | {key: .key, value: .value}')
fi

# Determine architecture from platform
ARCH="amd64"
if [[ "$PLATFORM" == *"arm64"* ]]; then
    ARCH="arm64"
    log_info "Building for ARM64 (AWS Graviton)"
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed or not in PATH"
    exit 1
fi

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed or not in PATH"
    exit 1
fi

# Login to ECR
log_info "Logging in to Amazon ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$(echo "$REPOSITORY_URL" | cut -d'/' -f1)" || {
    log_error "Failed to login to ECR"
    exit 1
}
log_success "Successfully logged in to ECR"

# Check if buildx is available for multi-platform builds
BUILDX_AVAILABLE=false
if docker buildx version &> /dev/null; then
    BUILDX_AVAILABLE=true
    log_info "Docker buildx is available - enabling multi-platform builds"

    # Create or use existing builder
    if ! docker buildx inspect aegis-builder &> /dev/null; then
        log_info "Creating buildx builder instance..."
        docker buildx create --name aegis-builder --use || true
    else
        log_info "Using existing buildx builder..."
        docker buildx use aegis-builder || docker buildx use default
    fi

    # Bootstrap builder
    docker buildx inspect --bootstrap
fi

# Build image
log_info "Building Docker image..."
IMAGE_URI="$REPOSITORY_URL:$IMAGE_TAG"

if [[ "$BUILDX_AVAILABLE" == true ]]; then
    # Use buildx for multi-platform builds
    log_info "Using Docker buildx for platform: $PLATFORM"
    docker buildx build \
        --platform "$PLATFORM" \
        --file "$DOCKERFILE_PATH" \
        --tag "$IMAGE_URI" \
        $BUILD_ARGS \
        --load \
        . || {
        log_error "Docker build failed"
        exit 1
    }
else
    # Use standard docker build
    log_info "Using standard Docker build"
    docker build \
        --file "$DOCKERFILE_PATH" \
        --tag "$IMAGE_URI" \
        $BUILD_ARGS \
        . || {
        log_error "Docker build failed"
        exit 1
    }
fi

log_success "Docker image built successfully: $IMAGE_URI"

# Tag additional tags if provided
if [[ -n "$ADDITIONAL_TAGS" ]]; then
    log_info "Applying additional tags..."
    IFS=',' read -ra TAGS <<< "$ADDITIONAL_TAGS"
    for tag in "${TAGS[@]}"; do
        tag=$(echo "$tag" | xargs)  # Trim whitespace
        if [[ -n "$tag" ]]; then
            ADDITIONAL_IMAGE_URI="$REPOSITORY_URL:$tag"
            log_info "Tagging as: $ADDITIONAL_IMAGE_URI"
            docker tag "$IMAGE_URI" "$ADDITIONAL_IMAGE_URI"
        fi
    done
fi

# Push primary image
log_info "Pushing Docker image to ECR: $IMAGE_URI"
docker push "$IMAGE_URI" || {
    log_error "Failed to push image to ECR"
    exit 1
}
log_success "Successfully pushed image: $IMAGE_URI"

# Push additional tags
if [[ -n "$ADDITIONAL_TAGS" ]]; then
    log_info "Pushing additional tagged images..."
    IFS=',' read -ra TAGS <<< "$ADDITIONAL_TAGS"
    for tag in "${TAGS[@]}"; do
        tag=$(echo "$tag" | xargs)
        if [[ -n "$tag" ]]; then
            ADDITIONAL_IMAGE_URI="$REPOSITORY_URL:$tag"
            log_info "Pushing: $ADDITIONAL_IMAGE_URI"
            docker push "$ADDITIONAL_IMAGE_URI" || {
                log_warning "Failed to push additional tag: $tag"
            }
        fi
    done
fi

# Get image digest
IMAGE_DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE_URI" 2>/dev/null || echo "N/A")
log_info "Image Digest: $IMAGE_DIGEST"

# Get image size
IMAGE_SIZE=$(docker inspect --format='{{.Size}}' "$IMAGE_URI" 2>/dev/null || echo "0")
IMAGE_SIZE_MB=$((IMAGE_SIZE / 1024 / 1024))
log_info "Image Size: ${IMAGE_SIZE_MB}MB"

# Clean up old images locally (optional)
log_info "Cleaning up dangling images..."
docker image prune -f > /dev/null 2>&1 || true

# Summary
log_success "======================================"
log_success "Docker Build and Push Complete"
log_success "======================================"
log_success "Repository: $REPOSITORY_URL"
log_success "Tag: $IMAGE_TAG"
log_success "Platform: $PLATFORM"
log_success "Size: ${IMAGE_SIZE_MB}MB"
log_success "======================================"

exit 0
