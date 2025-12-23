"""
Example usage of the Durable Lambda Controller.

This file demonstrates how to invoke and interact with the controller
in various scenarios.
"""

import json
import boto3
from datetime import datetime

# Initialize clients
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')


def start_workflow_example():
    """
    Example: Start a new research workflow.
    """
    payload = {
        'topic': 'Impact of quantum computing on cryptography',
        'parameters': {
            'depth': 'comprehensive',
            'sources': ['academic', 'industry', 'government'],
            'word_limit': 5000,
            'focus_areas': [
                'Post-quantum cryptography algorithms',
                'Current cryptographic vulnerabilities',
                'Timeline for quantum threats',
                'Migration strategies'
            ]
        }
    }

    print("Starting workflow...")
    print(f"Topic: {payload['topic']}")

    response = lambda_client.invoke(
        FunctionName='DurableControllerFunction',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    result = json.loads(response['Payload'].read())

    print(f"\nWorkflow started!")
    print(f"Workflow ID: {result.get('workflow_id')}")
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message', 'N/A')}")

    return result.get('workflow_id')


def check_workflow_status(workflow_id: str):
    """
    Example: Check the status of a running workflow.
    """
    table_name = 'agent-workflows'  # Replace with your table name
    table = dynamodb.Table(table_name)

    print(f"\nChecking workflow status: {workflow_id}")

    response = table.get_item(Key={'workflow_id': workflow_id})
    item = response.get('Item')

    if item:
        print(f"\nWorkflow Status:")
        print(f"  ID: {item['workflow_id']}")
        print(f"  Topic: {item['topic']}")
        print(f"  Status: {item['status']}")
        print(f"  Current Step: {item.get('current_step', 'N/A')}")
        print(f"  Created: {item['created_at']}")
        print(f"  Updated: {item['updated_at']}")

        if item.get('steps_completed'):
            print(f"\n  Steps Completed:")
            for step in item['steps_completed']:
                print(f"    - {step['step_name']} at {step['completed_at']}")

        return item
    else:
        print(f"Workflow not found: {workflow_id}")
        return None


def approve_workflow(workflow_id: str, approved: bool = True, feedback: str = ""):
    """
    Example: Approve or reject a workflow awaiting approval.
    """
    payload = {
        'workflow_id': workflow_id,
        'callback_name': 'human_approval',
        'callback_token': 'token-from-approval-request',  # Would come from notification
        'callback_result': {
            'approved': approved,
            'feedback': feedback,
            'approved_by': 'user@example.com',
            'approved_at': datetime.utcnow().isoformat()
        }
    }

    print(f"\nSending approval decision for workflow: {workflow_id}")
    print(f"Approved: {approved}")

    response = lambda_client.invoke(
        FunctionName='DurableControllerFunction',
        InvocationType='RequestResponse',
        Payload=json.dumps(payload)
    )

    result = json.loads(response['Payload'].read())

    print(f"\nApproval processed!")
    print(f"Status: {result.get('status')}")

    return result


def simulate_agent_callback(workflow_id: str, step_name: str, result_data: dict):
    """
    Example: Simulate an agent callback (normally done by the agent itself).
    """
    callback_url = f"https://api-id.execute-api.region.amazonaws.com/v1/callbacks/{workflow_id}"

    # In production, this would be called by the agent via HTTP POST
    payload = {
        'workflow_id': workflow_id,
        'callback_name': f'{step_name}_await',
        'callback_token': 'token-from-dispatch',  # Would be provided to agent
        'callback_result': result_data
    }

    print(f"\nSimulating agent callback for: {step_name}")

    # Call the callback handler Lambda
    response = lambda_client.invoke(
        FunctionName='CallbackHandlerFunction',
        InvocationType='RequestResponse',
        Payload=json.dumps({
            'body': json.dumps(payload),
            'httpMethod': 'POST'
        })
    )

    result = json.loads(response['Payload'].read())

    print(f"Callback delivered: {result.get('status')}")

    return result


def get_workflow_report(workflow_id: str):
    """
    Example: Retrieve the final report URL for a completed workflow.
    """
    table_name = 'agent-workflows'
    table = dynamodb.Table(table_name)

    print(f"\nRetrieving report for workflow: {workflow_id}")

    response = table.get_item(Key={'workflow_id': workflow_id})
    item = response.get('Item')

    if item and item.get('status') == 'COMPLETED':
        report_url = item.get('report_url')
        print(f"\nWorkflow completed!")
        print(f"Report URL: {report_url}")
        print(f"Completed at: {item.get('completed_at')}")
        return report_url
    else:
        status = item.get('status') if item else 'NOT_FOUND'
        print(f"\nWorkflow not completed. Current status: {status}")
        return None


def api_gateway_example():
    """
    Example: Using the API Gateway endpoint directly.
    """
    import requests  # Would need to be added to requirements

    api_url = "https://api-id.execute-api.region.amazonaws.com/v1"

    # Start workflow via REST API
    payload = {
        'topic': 'Serverless architecture best practices',
        'parameters': {
            'depth': 'intermediate',
            'focus': 'cost optimization'
        }
    }

    print("\nStarting workflow via API Gateway...")

    # In production, would use AWS SigV4 signing
    response = requests.post(
        f"{api_url}/workflows",
        json=payload,
        headers={'Content-Type': 'application/json'}
    )

    if response.status_code == 200:
        result = response.json()
        workflow_id = result['workflow_id']

        print(f"Workflow started: {workflow_id}")

        # Check status
        status_response = requests.get(f"{api_url}/workflows/{workflow_id}")

        if status_response.status_code == 200:
            status = status_response.json()
            print(f"Current status: {status['status']}")

        return workflow_id
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None


def monitor_workflow_progress(workflow_id: str, interval: int = 30):
    """
    Example: Monitor workflow progress with polling.
    """
    import time

    print(f"\nMonitoring workflow: {workflow_id}")
    print("Press Ctrl+C to stop monitoring\n")

    previous_status = None
    previous_step = None

    try:
        while True:
            state = check_workflow_status(workflow_id)

            if state:
                current_status = state.get('status')
                current_step = state.get('current_step')

                # Only print updates when something changes
                if current_status != previous_status or current_step != previous_step:
                    print(f"\n[{datetime.now().isoformat()}]")
                    print(f"Status: {current_status}")
                    print(f"Current Step: {current_step}")

                    previous_status = current_status
                    previous_step = current_step

                # Check for completion
                if current_status in ['COMPLETED', 'REJECTED', 'FAILED']:
                    print(f"\nWorkflow finished with status: {current_status}")
                    break

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")


def full_workflow_example():
    """
    Example: Complete workflow from start to finish.
    """
    print("=" * 60)
    print("Full Workflow Example")
    print("=" * 60)

    # 1. Start workflow
    workflow_id = start_workflow_example()

    print("\n" + "-" * 60)
    print("Workflow started. In a real scenario:")
    print("  1. Research agent would be invoked (async)")
    print("  2. Agent would callback when research is complete")
    print("  3. Analysis agent would be invoked")
    print("  4. Agent would callback when analysis is complete")
    print("  5. Approval request would be sent to human")
    print("  6. Human would approve/reject via callback")
    print("  7. Writer agent would generate final report")
    print("  8. Report would be stored and URL returned")
    print("-" * 60)

    # 2. Simulate waiting and checking status
    print("\nSimulating workflow progress...")

    # Normally you would wait for actual agent callbacks
    # For this example, we'll just check the initial status
    check_workflow_status(workflow_id)

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)

    return workflow_id


if __name__ == '__main__':
    # Run the full example
    workflow_id = full_workflow_example()

    print(f"\nWorkflow ID for reference: {workflow_id}")
    print("\nTo check status later, run:")
    print(f"  check_workflow_status('{workflow_id}')")
