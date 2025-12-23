# Researcher Agent for Amazon Bedrock AgentCore Runtime
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ /app/src/

# Create .well-known directory for agent metadata
RUN mkdir -p /app/.well-known
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
