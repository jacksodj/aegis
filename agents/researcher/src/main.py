"""
Researcher Agent - Main Application
FastAPI-based agent for Amazon Bedrock AgentCore Runtime

Implements:
- A2A protocol endpoints
- Agent discovery (agent-card.json)
- Asynchronous task execution with callbacks
- Research capabilities with simulated LLM
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
import httpx
import boto3

from .tools import (
    save_artifact,
    search_web,
    search_documents,
    synthesize_research
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
MODEL_ID = os.environ.get('MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
ARTIFACT_BUCKET = os.environ.get('ARTIFACT_BUCKET', 'aegis-artifacts')
CALLBACK_API_URL = os.environ.get('CALLBACK_API_URL', 'http://localhost:8000/callbacks')

# Initialize AWS clients
try:
    bedrock_runtime = boto3.client('bedrock-runtime')
    logger.info("Initialized Bedrock Runtime client")
except Exception as e:
    logger.warning(f"Could not initialize Bedrock client: {e}. Using simulated mode.")
    bedrock_runtime = None

# Application state
app_state = {
    'tasks_completed': 0,
    'tasks_failed': 0,
    'startup_time': datetime.utcnow().isoformat()
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Researcher Agent starting up...")
    logger.info(f"Model ID: {MODEL_ID}")
    logger.info(f"Artifact Bucket: {ARTIFACT_BUCKET}")
    logger.info(f"Callback API URL: {CALLBACK_API_URL}")
    yield
    logger.info("Researcher Agent shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Researcher Agent",
    description="Research specialist agent for gathering and synthesizing information",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "researcher-agent",
        "version": "1.0.0",
        "status": "operational",
        "stats": app_state
    }


@app.get("/ping")
async def ping():
    """
    Health endpoint - returns HealthyBusy to prevent idle timeout.
    AgentCore uses this to determine if the agent is still active.
    """
    return {
        "status": "HealthyBusy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_id": MODEL_ID,
        "artifact_bucket": ARTIFACT_BUCKET,
        "bedrock_available": bedrock_runtime is not None,
        "stats": app_state,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """
    Agent discovery endpoint.
    Returns metadata about the agent's capabilities and protocols.
    """
    return {
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
                            "description": "Additional parameters like depth, sources, constraints",
                            "properties": {
                                "depth": {
                                    "type": "string",
                                    "enum": ["basic", "comprehensive", "deep"],
                                    "default": "comprehensive"
                                },
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Source types to search (academic, industry, etc.)"
                                },
                                "max_results": {
                                    "type": "integer",
                                    "default": 10,
                                    "minimum": 1,
                                    "maximum": 50
                                }
                            }
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
                    "url": "/invocations",
                    "port": 8080,
                    "methods": ["POST"]
                },
                {
                    "url": "/",
                    "port": 9000,
                    "methods": ["POST"]
                }
            ]
        },
        "authentication": {
            "type": "AWS_SigV4",
            "service": "bedrock-agentcore"
        },
        "tools": [
            "web_search",
            "search_documents",
            "save_artifact",
            "synthesize_research"
        ]
    }


@app.post("/invocations")
async def invoke(request: Request, background_tasks: BackgroundTasks):
    """
    Main invocation endpoint for AgentCore.
    Handles both synchronous and asynchronous task execution.

    Expected payload format (JSON-RPC 2.0):
    {
        "jsonrpc": "2.0",
        "id": "request-id",
        "method": "tasks/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "{...payload...}"}]
            }
        }
    }
    """
    try:
        body = await request.json()
        logger.info(f"Received invocation request: {json.dumps(body, indent=2)[:500]}")

        # Extract task details from JSON-RPC format
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
                    # If not JSON, treat as plain text query
                    payload = {'topic': part['text'], 'workflow_id': 'unknown'}
                break

        if not payload:
            raise HTTPException(status_code=400, detail="No valid payload found in request")

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
                    "message": "Task queued for async execution",
                    "workflow_id": payload.get('workflow_id')
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in invocation: {str(e)}", exc_info=True)
        app_state['tasks_failed'] += 1
        raise HTTPException(status_code=500, detail=str(e))


async def execute_research(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute research task using simulated LLM reasoning.

    Args:
        payload: Task payload containing topic, parameters, and workflow_id

    Returns:
        Structured research results
    """
    logger.info(f"Executing research task: {json.dumps(payload, indent=2)[:300]}")

    # Extract parameters
    topic = payload.get('topic', payload.get('query', ''))
    parameters = payload.get('parameters', {})
    workflow_id = payload.get('workflow_id', 'unknown')

    depth = parameters.get('depth', 'comprehensive')
    sources = parameters.get('sources')
    max_results = parameters.get('max_results', 10)

    # Adjust max_results based on depth
    if depth == 'basic':
        max_results = min(max_results, 5)
    elif depth == 'deep':
        max_results = max(max_results, 20)

    try:
        # Step 1: Perform web search
        logger.info(f"Searching for: {topic}")
        search_results = search_web(topic, max_results=max_results, sources=sources)

        # Step 2: Search documents if sources specified
        if sources:
            doc_results = search_documents(topic, document_sources=sources, max_results=5)
            search_results.extend(doc_results)

        # Step 3: Synthesize research findings
        synthesis = synthesize_research(search_results, topic)

        # Step 4: Generate research report using simulated LLM
        # In production, this would call Bedrock
        research_report = await generate_research_report(
            topic=topic,
            synthesis=synthesis,
            depth=depth
        )

        # Step 5: Check if result is large enough to need S3 storage
        result_str = json.dumps(research_report)
        if len(result_str) > 200000:  # ~200KB
            logger.info(f"Result size ({len(result_str)} bytes) exceeds threshold, saving to S3")
            artifact = save_artifact(
                content=research_report,
                artifact_type='research_results',
                workflow_id=workflow_id,
                metadata={'topic': topic, 'depth': depth}
            )
            app_state['tasks_completed'] += 1
            return artifact
        else:
            # Return result directly
            app_state['tasks_completed'] += 1
            return research_report

    except Exception as e:
        logger.error(f"Error executing research: {str(e)}", exc_info=True)
        app_state['tasks_failed'] += 1
        raise


async def generate_research_report(
    topic: str,
    synthesis: Dict[str, Any],
    depth: str = 'comprehensive'
) -> Dict[str, Any]:
    """
    Generate research report using LLM (simulated).
    In production, this would call Amazon Bedrock.

    Args:
        topic: Research topic
        synthesis: Synthesized research findings
        depth: Depth of research (basic, comprehensive, deep)

    Returns:
        Structured research report
    """
    # Simulated LLM response
    # In production, this would be replaced with actual Bedrock API call

    if bedrock_runtime:
        # Attempt to use real Bedrock (if available)
        try:
            report = await call_bedrock_llm(topic, synthesis, depth)
            if report:
                return report
        except Exception as e:
            logger.warning(f"Bedrock call failed, using simulated response: {e}")

    # Simulated response
    logger.info(f"Generating simulated research report for: {topic}")

    report = {
        "topic": topic,
        "research_type": depth,
        "executive_summary": f"This {depth} research on '{topic}' has identified {len(synthesis['sources']['citations'])} relevant sources across {len(synthesis['sources']['by_type'])} source types. The findings indicate significant developments and ongoing research in this area.",

        "key_findings": [
            {
                "finding": f"Current state of {topic}",
                "description": f"Analysis of {topic} reveals a mature field with ongoing developments and innovations.",
                "confidence": "high",
                "sources": synthesis['sources']['citations'][:2]
            },
            {
                "finding": f"Recent developments in {topic}",
                "description": f"Recent research has shown significant progress in understanding and applying {topic}.",
                "confidence": "high",
                "sources": synthesis['sources']['citations'][2:4]
            },
            {
                "finding": f"Future implications of {topic}",
                "description": f"The future of {topic} appears promising with potential applications across multiple domains.",
                "confidence": "medium",
                "sources": synthesis['sources']['citations'][4:6]
            }
        ],

        "detailed_analysis": {
            "overview": synthesis['summary'],
            "methodology": f"This research utilized {synthesis['sources']['total']} sources, employing web search and document analysis techniques. Sources were evaluated for relevance, credibility, and recency.",
            "findings_by_source_type": synthesis['sources']['by_type'],
            "data_quality": {
                "average_confidence": synthesis['data_points']['average_confidence'],
                "source_diversity": len(synthesis['sources']['by_type']),
                "temporal_coverage": synthesis['data_points']['date_range']
            }
        },

        "recommendations": [
            f"Continue monitoring developments in {topic} as the field evolves",
            "Consider conducting primary research to fill identified gaps",
            "Engage with subject matter experts for deeper insights",
            "Review emerging publications and recent findings regularly"
        ],

        "sources_cited": synthesis['sources']['citations'],

        "research_gaps": synthesis['gaps'],

        "metadata": {
            "workflow_id": synthesis.get('workflow_id', 'unknown'),
            "agent": "researcher-agent",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "search_stats": synthesis['data_points']
        }
    }

    return report


async def call_bedrock_llm(
    topic: str,
    synthesis: Dict[str, Any],
    depth: str
) -> Optional[Dict[str, Any]]:
    """
    Call Amazon Bedrock for LLM-based research synthesis.

    Args:
        topic: Research topic
        synthesis: Synthesized research data
        depth: Research depth

    Returns:
        LLM-generated research report or None if unavailable
    """
    if not bedrock_runtime:
        return None

    try:
        # Build prompt for Claude
        prompt = f"""You are a research specialist. Analyze the following research data and generate a comprehensive research report.

Topic: {topic}
Research Depth: {depth}

Source Data:
{json.dumps(synthesis, indent=2)}

Please generate a structured research report with:
1. Executive summary
2. Key findings (at least 3)
3. Detailed analysis
4. Recommendations
5. Research gaps

Format the response as JSON."""

        # Call Bedrock
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.7
            })
        )

        result = json.loads(response['body'].read())
        content = result['content'][0]['text']

        # Try to parse as JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # If not JSON, wrap in structure
            return {
                "topic": topic,
                "analysis": content,
                "metadata": {
                    "model": MODEL_ID,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

    except Exception as e:
        logger.error(f"Error calling Bedrock: {e}")
        return None


async def execute_and_callback(
    payload: Dict[str, Any],
    callback_url: str,
    callback_token: str
):
    """
    Execute task asynchronously and send callback to Durable Lambda.

    Args:
        payload: Task payload
        callback_url: URL to send callback to
        callback_token: Authentication token for callback
    """
    logger.info(f"Starting async execution for workflow: {payload.get('workflow_id')}")

    try:
        # Execute the research task
        result = await execute_research(payload)

        # Send success callback
        async with httpx.AsyncClient(timeout=30.0) as client:
            callback_payload = {
                'token': callback_token,
                'status': 'SUCCESS',
                'result': result
            }

            logger.info(f"Sending success callback to: {callback_url}")
            response = await client.post(
                callback_url,
                json=callback_payload,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            logger.info(f"Callback sent successfully: {response.status_code}")

    except Exception as e:
        logger.error(f"Error in async execution: {str(e)}", exc_info=True)

        # Send failure callback
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                callback_payload = {
                    'token': callback_token,
                    'status': 'FAILURE',
                    'error': str(e),
                    'error_type': type(e).__name__
                }

                logger.info(f"Sending failure callback to: {callback_url}")
                response = await client.post(
                    callback_url,
                    json=callback_payload,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                logger.info(f"Failure callback sent: {response.status_code}")

        except Exception as callback_error:
            logger.error(f"Failed to send error callback: {str(callback_error)}")


# A2A Protocol endpoint (port 9000)
@app.post("/")
async def a2a_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    A2A protocol endpoint (alternative to /invocations).
    This runs on port 9000 as per AgentCore specification.
    """
    # Same logic as /invocations
    return await invoke(request, background_tasks)


if __name__ == "__main__":
    import uvicorn

    # Run on port 8080 (main HTTP endpoint)
    logger.info("Starting Researcher Agent on port 8080...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info",
        access_log=True
    )
