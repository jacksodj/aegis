"""
Writer Agent - Amazon Bedrock AgentCore Runtime

Produces formatted research reports with executive summaries, detailed findings,
recommendations, and references. Saves reports to S3 and returns presigned URLs.
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, BackgroundTasks
import structlog
import boto3

# Local imports
from .tools import (
    save_artifact,
    format_report,
    generate_markdown_report
)

# Configuration
MODEL_ID = os.environ.get('MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
ARTIFACT_BUCKET = os.environ.get('ARTIFACT_BUCKET', 'agent-artifacts')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Initialize AWS clients
bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)
s3 = boto3.client('s3', region_name=AWS_REGION)

# Configure structured logging
logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="Writer Agent",
    description="Report writing specialist for research workflows",
    version="1.0.0"
)


@app.get("/ping")
async def ping():
    """
    Health endpoint - returns HealthyBusy to prevent idle timeout.

    AgentCore Runtime calls this periodically to ensure the agent is responsive.
    """
    return {"status": "HealthyBusy", "agent": "writer", "timestamp": datetime.utcnow().isoformat()}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """
    Agent discovery endpoint.

    Returns metadata about the agent's capabilities, protocols, and schemas.
    """
    return {
        "name": "writer-agent",
        "version": "1.0.0",
        "description": "Writer specialist agent for producing formatted research reports",
        "capabilities": {
            "write_report": {
                "description": "Generate comprehensive formatted report from analysis results",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "analysis": {"type": "object"},
                        "feedback": {"type": "string"},
                        "workflow_id": {"type": "string"}
                    },
                    "required": ["task", "analysis", "workflow_id"]
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
    """
    Main invocation endpoint for the Writer Agent.

    Handles both synchronous and asynchronous (callback-based) execution patterns.
    Parses JSON-RPC 2.0 requests and extracts task parameters.
    """
    body = await request.json()

    logger.info("writer_invocation_received", request_id=body.get('id'))

    # Extract task details from JSON-RPC params
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
                payload = {'query': part['text']}
            break

    if not payload:
        logger.error("no_valid_payload", request_id=body.get('id'))
        return {
            "jsonrpc": "2.0",
            "id": body.get('id'),
            "error": {
                "code": -32602,
                "message": "No valid payload found in request"
            }
        }

    # Check for callback URL (async pattern)
    callback_url = payload.get('callback_url')
    callback_token = payload.get('callback_token')

    if callback_url:
        # Async execution - run in background and callback when done
        logger.info(
            "async_execution_queued",
            workflow_id=payload.get('workflow_id'),
            callback_url=callback_url
        )

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
                "message": "Writing task queued for async execution"
            }
        }
    else:
        # Sync execution - wait for result
        logger.info(
            "sync_execution_started",
            workflow_id=payload.get('workflow_id')
        )

        result = await execute_writing_task(payload)

        return {
            "jsonrpc": "2.0",
            "id": body.get('id'),
            "result": result
        }


async def execute_writing_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the writing task: generate a formatted report from analysis data.

    Args:
        payload: Task parameters including analysis data, feedback, and workflow_id

    Returns:
        Report metadata including S3 reference and presigned URL
    """
    task = payload.get('task', 'write_report')
    analysis_data = payload.get('analysis', {})
    feedback = payload.get('feedback', '')
    workflow_id = payload.get('workflow_id', 'unknown')

    logger.info(
        "writing_task_started",
        task=task,
        workflow_id=workflow_id,
        has_feedback=bool(feedback)
    )

    try:
        # Step 1: Format the analysis data into structured report
        structured_report = format_report(
            analysis_data=analysis_data,
            feedback=feedback if feedback else None,
            title=analysis_data.get('title', 'Research Report')
        )

        logger.info(
            "report_structured",
            workflow_id=workflow_id,
            sections=list(structured_report.keys())
        )

        # Step 2: Use Claude to enhance and refine the report content
        enhanced_report = await enhance_report_with_llm(
            structured_report=structured_report,
            analysis_data=analysis_data,
            feedback=feedback
        )

        logger.info(
            "report_enhanced",
            workflow_id=workflow_id
        )

        # Step 3: Generate markdown version for human readability
        markdown_report = generate_markdown_report(enhanced_report)

        # Step 4: Save both JSON and Markdown versions to S3
        json_artifact = save_artifact(
            content=json.dumps(enhanced_report, indent=2),
            artifact_type='final_report_json',
            workflow_id=workflow_id,
            content_type='application/json'
        )

        markdown_artifact = save_artifact(
            content=markdown_report,
            artifact_type='final_report_md',
            workflow_id=workflow_id,
            content_type='text/markdown'
        )

        logger.info(
            "report_saved",
            workflow_id=workflow_id,
            json_uri=json_artifact['s3_uri'],
            markdown_uri=markdown_artifact['s3_uri']
        )

        # Return both artifacts
        return {
            'status': 'completed',
            'workflow_id': workflow_id,
            'report': {
                'json': json_artifact,
                'markdown': markdown_artifact,
                'title': enhanced_report['metadata']['title'],
                'generated_at': enhanced_report['metadata']['generated_at']
            },
            'summary': enhanced_report['executive_summary']['overview'][:500]
        }

    except Exception as e:
        logger.error(
            "writing_task_failed",
            workflow_id=workflow_id,
            error=str(e),
            exc_info=True
        )
        raise


async def enhance_report_with_llm(
    structured_report: Dict[str, Any],
    analysis_data: Dict[str, Any],
    feedback: Optional[str] = None
) -> Dict[str, Any]:
    """
    Use Claude via Bedrock to enhance and refine the report content.

    Args:
        structured_report: The initially formatted report structure
        analysis_data: Original analysis data for context
        feedback: Optional human feedback to incorporate

    Returns:
        Enhanced report with improved writing quality
    """
    # Build the prompt for Claude
    prompt = _build_enhancement_prompt(structured_report, analysis_data, feedback)

    # Prepare Bedrock request
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.7,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        # Call Bedrock
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())
        enhanced_content = response_body['content'][0]['text']

        # Parse the enhanced report from Claude's response
        # Claude should return JSON matching our report structure
        try:
            enhanced_report = json.loads(enhanced_content)
            # Merge with original structure to ensure all fields present
            return _merge_reports(structured_report, enhanced_report)
        except json.JSONDecodeError:
            # If Claude didn't return valid JSON, use structured report with enhanced summary
            logger.warning("llm_response_not_json", using_structured_report=True)
            structured_report['executive_summary']['overview'] = enhanced_content[:1000]
            return structured_report

    except Exception as e:
        logger.error("llm_enhancement_failed", error=str(e))
        # Fallback to original structured report
        return structured_report


def _build_enhancement_prompt(
    structured_report: Dict[str, Any],
    analysis_data: Dict[str, Any],
    feedback: Optional[str]
) -> str:
    """Build the prompt for Claude to enhance the report."""

    prompt_parts = [
        "You are a professional report writer. Your task is to refine and enhance a research report.",
        "",
        "# Original Analysis Data:",
        json.dumps(analysis_data, indent=2),
        "",
        "# Current Report Structure:",
        json.dumps(structured_report, indent=2),
    ]

    if feedback:
        prompt_parts.extend([
            "",
            "# Human Feedback to Incorporate:",
            feedback,
        ])

    prompt_parts.extend([
        "",
        "# Your Task:",
        "1. Review the current report structure and content",
        "2. Enhance the writing quality while maintaining accuracy",
        "3. Ensure the executive summary is compelling and concise",
        "4. Make recommendations actionable and specific",
        "5. Incorporate any human feedback provided",
        "",
        "Return the enhanced report as a JSON object matching the exact structure provided.",
        "Focus on improving clarity, coherence, and professional tone.",
        "Do not omit any sections - enhance all parts of the report.",
    ])

    return "\n".join(prompt_parts)


def _merge_reports(base: Dict[str, Any], enhanced: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge enhanced report content with base structure.

    Ensures all required fields are present even if LLM didn't return them.
    """
    merged = base.copy()

    for key, value in enhanced.items():
        if key in merged and isinstance(value, dict) and isinstance(merged[key], dict):
            # Deep merge dictionaries
            merged[key] = {**merged[key], **value}
        else:
            # Direct assignment for non-dict values
            merged[key] = value

    return merged


async def execute_and_callback(
    payload: Dict[str, Any],
    callback_url: str,
    callback_token: str
):
    """
    Execute writing task and send callback to Durable Lambda controller.

    Args:
        payload: Task parameters
        callback_url: Controller callback endpoint
        callback_token: Authentication token for callback
    """
    workflow_id = payload.get('workflow_id', 'unknown')

    try:
        result = await execute_writing_task(payload)

        logger.info(
            "sending_success_callback",
            workflow_id=workflow_id,
            callback_url=callback_url
        )

        # Send success callback
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                callback_url,
                json={
                    'token': callback_token,
                    'status': 'SUCCESS',
                    'result': result
                },
                headers={
                    'Content-Type': 'application/json'
                }
            )
            response.raise_for_status()

        logger.info(
            "callback_sent_successfully",
            workflow_id=workflow_id,
            status_code=response.status_code
        )

    except Exception as e:
        logger.error(
            "task_failed_sending_error_callback",
            workflow_id=workflow_id,
            error=str(e),
            exc_info=True
        )

        # Send failure callback
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    callback_url,
                    json={
                        'token': callback_token,
                        'status': 'FAILURE',
                        'error': str(e),
                        'error_type': type(e).__name__
                    },
                    headers={
                        'Content-Type': 'application/json'
                    }
                )
        except Exception as callback_error:
            logger.error(
                "callback_failed",
                workflow_id=workflow_id,
                callback_error=str(callback_error)
            )


if __name__ == "__main__":
    import uvicorn

    logger.info(
        "starting_writer_agent",
        model_id=MODEL_ID,
        artifact_bucket=ARTIFACT_BUCKET,
        region=AWS_REGION
    )

    # Run main HTTP server on port 8080
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
