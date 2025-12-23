# Analyst Agent for Amazon Bedrock AgentCore Runtime
FROM python:3.11-slim

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
