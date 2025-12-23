"""
Analyst Agent for Amazon Bedrock AgentCore Runtime

This agent receives research data and produces structured analysis with:
- Key insights
- Patterns identified
- Recommendations
- Confidence scores
"""
import os
import json
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, BackgroundTasks
import uvicorn
import boto3

# Import custom tools
from .tools import (
    save_artifact,
    analyze_data,
    calculate_confidence_scores,
    identify_patterns,
    generate_recommendations
)

# Configuration
MODEL_ID = os.environ.get('MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
ARTIFACT_BUCKET = os.environ.get('ARTIFACT_BUCKET')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Initialize AWS clients
bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)

# Create FastAPI app
app = FastAPI(
    title="Analyst Agent",
    description="Analysis specialist for synthesizing research and producing insights",
    version="1.0.0"
)


@app.get("/ping")
async def ping():
    """
    Health endpoint - returns HealthyBusy to prevent idle timeout.
    This is critical for AgentCore Runtime to prevent session termination.
    """
    return {"status": "HealthyBusy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """
    Agent discovery endpoint.
    Returns metadata about the agent's capabilities and communication protocol.
    """
    # Load agent card from file
    try:
        with open('/app/.well-known/agent-card.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback to inline definition
        return {
            "name": "analyst-agent",
            "version": "1.0.0",
            "description": "Analysis specialist agent for synthesizing research data",
            "capabilities": {
                "analyze": {
                    "description": "Analyze research data and produce structured insights",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "research_data": {"type": "object"},
                            "workflow_id": {"type": "string"}
                        },
                        "required": ["research_data", "workflow_id"]
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
    Main invocation endpoint for A2A protocol (JSON-RPC 2.0).
    Handles both sync and async execution patterns.
    """
    try:
        body = await request.json()

        # Extract task details from JSON-RPC structure
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
                    payload = {'query': part['text']}
                break

        if not payload:
            return {
                "jsonrpc": "2.0",
                "id": body.get('id'),
                "error": {
                    "code": -32600,
                    "message": "No valid payload found"
                }
            }

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
                    "message": "Analysis task queued for async execution"
                }
            }
        else:
            # Sync execution - wait for result
            result = await execute_analysis(payload)
            return {
                "jsonrpc": "2.0",
                "id": body.get('id'),
                "result": result
            }

    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": body.get('id', 'unknown'),
            "error": {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
        }


async def execute_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute analysis task on research data.

    Args:
        payload: Contains research_data and workflow_id

    Returns:
        Structured analysis results with insights, patterns, and recommendations
    """
    research_data = payload.get('research_data', {})
    workflow_id = payload.get('workflow_id', 'unknown')
    task_type = payload.get('task', 'analyze')

    # If research_data is an S3 reference, fetch it
    if isinstance(research_data, dict) and research_data.get('artifact_type') == 's3_reference':
        research_data = await fetch_s3_artifact(research_data['s3_uri'])

    # Perform multi-stage analysis

    # Stage 1: Basic data analysis
    basic_analysis = analyze_data(research_data)

    # Stage 2: Calculate confidence scores
    confidence_scores = calculate_confidence_scores(research_data)

    # Stage 3: Identify patterns
    patterns = identify_patterns(research_data)

    # Stage 4: Generate recommendations
    recommendations = generate_recommendations(
        basic_analysis,
        patterns,
        confidence_scores
    )

    # Stage 5: Use LLM for deep insights
    llm_insights = await generate_llm_insights(research_data, basic_analysis, patterns)

    # Compile final analysis
    analysis_result = {
        'metadata': {
            'workflow_id': workflow_id,
            'analyzed_at': datetime.utcnow().isoformat(),
            'task_type': task_type,
            'agent': 'analyst-agent',
            'version': '1.0.0'
        },
        'summary': llm_insights.get('summary', 'Analysis completed'),
        'key_insights': llm_insights.get('insights', []),
        'patterns_identified': patterns,
        'confidence_scores': confidence_scores,
        'recommendations': recommendations,
        'statistics': basic_analysis.get('statistics', {}),
        'detailed_analysis': llm_insights.get('detailed_analysis', {})
    }

    # If result is large, save to S3
    analysis_str = json.dumps(analysis_result, indent=2)
    if len(analysis_str) > 200000:  # ~200KB threshold
        artifact = save_artifact(
            content=analysis_str,
            artifact_type='analysis_results',
            workflow_id=workflow_id
        )
        return artifact

    return analysis_result


async def generate_llm_insights(
    research_data: Dict[str, Any],
    basic_analysis: Dict[str, Any],
    patterns: list
) -> Dict[str, Any]:
    """
    Use Bedrock Claude to generate deep insights from research data.

    Args:
        research_data: The research findings
        basic_analysis: Preliminary analysis results
        patterns: Identified patterns

    Returns:
        LLM-generated insights and analysis
    """
    # Build the analysis prompt
    prompt = f"""You are an expert analyst reviewing research findings. Your task is to provide deep, actionable insights.

Research Data:
{json.dumps(research_data, indent=2)}

Preliminary Analysis:
{json.dumps(basic_analysis, indent=2)}

Identified Patterns:
{json.dumps(patterns, indent=2)}

Please provide:
1. A concise executive summary (2-3 sentences)
2. 3-5 key insights with explanations
3. Detailed analysis of the most important findings
4. Any critical observations or concerns

Format your response as JSON with the following structure:
{{
  "summary": "Executive summary here",
  "insights": [
    {{"insight": "Key insight 1", "explanation": "Why this matters", "confidence": 0.9}},
    {{"insight": "Key insight 2", "explanation": "Why this matters", "confidence": 0.85}}
  ],
  "detailed_analysis": {{
    "strengths": ["strength 1", "strength 2"],
    "weaknesses": ["weakness 1", "weakness 2"],
    "opportunities": ["opportunity 1"],
    "threats": ["threat 1"]
  }}
}}"""

    try:
        # Call Bedrock Claude
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'temperature': 0.7,
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            })
        )

        response_body = json.loads(response['body'].read())
        llm_output = response_body['content'][0]['text']

        # Try to parse as JSON
        try:
            # Extract JSON from markdown code blocks if present
            if '```json' in llm_output:
                json_start = llm_output.find('```json') + 7
                json_end = llm_output.find('```', json_start)
                llm_output = llm_output[json_start:json_end].strip()
            elif '```' in llm_output:
                json_start = llm_output.find('```') + 3
                json_end = llm_output.find('```', json_start)
                llm_output = llm_output[json_start:json_end].strip()

            return json.loads(llm_output)
        except json.JSONDecodeError:
            # If not valid JSON, return as plain text
            return {
                'summary': llm_output[:200],
                'insights': [{'insight': llm_output, 'confidence': 0.5}],
                'detailed_analysis': {}
            }

    except Exception as e:
        print(f"Error calling Bedrock: {e}")
        return {
            'summary': 'Analysis completed with preliminary results',
            'insights': [
                {
                    'insight': 'Unable to generate LLM insights',
                    'explanation': str(e),
                    'confidence': 0.3
                }
            ],
            'detailed_analysis': {}
        }


async def fetch_s3_artifact(s3_uri: str) -> Dict[str, Any]:
    """
    Fetch artifact from S3.

    Args:
        s3_uri: S3 URI in format s3://bucket/key

    Returns:
        Parsed JSON content from S3
    """
    try:
        bucket, key = s3_uri.replace('s3://', '').split('/', 1)
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
    except Exception as e:
        print(f"Error fetching S3 artifact: {e}")
        return {}


async def execute_and_callback(
    payload: Dict[str, Any],
    callback_url: str,
    callback_token: str
):
    """
    Execute analysis task and send callback to Durable Lambda.

    Args:
        payload: Task payload
        callback_url: URL to send callback to
        callback_token: Authentication token for callback
    """
    try:
        # Execute the analysis
        result = await execute_analysis(payload)

        # Send success callback
        async with httpx.AsyncClient() as client:
            await client.post(
                callback_url,
                json={
                    'token': callback_token,
                    'status': 'SUCCESS',
                    'result': result
                },
                headers={
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )
            print(f"Success callback sent for workflow {payload.get('workflow_id')}")

    except Exception as e:
        # Send failure callback
        print(f"Error in analysis execution: {e}")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    callback_url,
                    json={
                        'token': callback_token,
                        'status': 'FAILURE',
                        'error': str(e)
                    },
                    headers={
                        'Content-Type': 'application/json'
                    },
                    timeout=30.0
                )
                print(f"Failure callback sent for workflow {payload.get('workflow_id')}")
        except Exception as callback_error:
            print(f"Failed to send callback: {callback_error}")


if __name__ == "__main__":
    """
    Run the agent server.

    Note: In production, A2A server on port 9000 would also be started.
    For now, we use the HTTP endpoint on port 8080.
    """
    print(f"Starting Analyst Agent...")
    print(f"Model ID: {MODEL_ID}")
    print(f"Artifact Bucket: {ARTIFACT_BUCKET}")
    print(f"AWS Region: {AWS_REGION}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
