#!/usr/bin/env python3
"""
AWS CDK Infrastructure for Serverless Durable Agent Orchestration Platform

This stack provisions the core infrastructure for a durable, fault-tolerant
multi-agent workflow orchestration system combining AWS Lambda with Amazon
Bedrock AgentCore Runtime.
"""

from aws_cdk import (
    App,
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class AgentOrchestrationStack(Stack):
    """
    Main CDK stack for the Agent Orchestration Platform.

    Components:
    - S3 Bucket for artifact storage
    - DynamoDB Table for workflow metadata
    - Controller Lambda for durable workflow orchestration
    - Callback Lambda for agent completion callbacks
    - API Gateway for HTTP endpoints
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =====================================================================
        # S3 BUCKET - Artifact Storage
        # =====================================================================

        artifact_bucket = s3.Bucket(
            self,
            "ArtifactBucket",
            # Versioning for data durability and recovery
            versioned=True,
            # S3-managed encryption (SSE-S3)
            encryption=s3.BucketEncryption.S3_MANAGED,
            # Block all public access for security
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            # Development settings - destroy on stack deletion
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            # Enable intelligent tiering for cost optimization (optional)
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="TransitionToIA",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30)
                        )
                    ]
                )
            ]
        )

        # =====================================================================
        # DYNAMODB TABLE - Workflow Metadata
        # =====================================================================

        workflow_table = dynamodb.Table(
            self,
            "WorkflowTable",
            # Partition key for workflow identification
            partition_key=dynamodb.Attribute(
                name="workflow_id",
                type=dynamodb.AttributeType.STRING
            ),
            # Pay-per-request billing for unpredictable workloads
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            # TTL for automatic cleanup of old workflows
            time_to_live_attribute="ttl",
            # Point-in-time recovery for data protection
            point_in_time_recovery=True,
            # Development settings - destroy on stack deletion
            removal_policy=RemovalPolicy.DESTROY,
            # CloudWatch contributor insights for monitoring
            contributor_insights_enabled=True,
        )

        # Global Secondary Index for querying workflows by status
        workflow_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            ),
            # Inherit billing mode from table
        )

        # =====================================================================
        # CONTROLLER LAMBDA - Durable Workflow Orchestration
        # =====================================================================

        # IAM Role for Controller Lambda
        controller_role = iam.Role(
            self,
            "ControllerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for durable workflow controller Lambda",
            managed_policies=[
                # Basic Lambda execution permissions
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant S3 read/write permissions on artifact bucket
        artifact_bucket.grant_read_write(controller_role)

        # Grant DynamoDB read/write permissions on workflow table
        workflow_table.grant_read_write_data(controller_role)

        # Add X-Ray tracing permissions
        controller_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayTracing",
                effect=iam.Effect.ALLOW,
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords"
                ],
                resources=["*"]
            )
        )

        # Add EventBridge permissions for workflow events
        controller_role.add_to_policy(
            iam.PolicyStatement(
                sid="EventBridgeEvents",
                effect=iam.Effect.ALLOW,
                actions=["events:PutEvents"],
                resources=[
                    f"arn:aws:events:{self.region}:{self.account}:event-bus/default"
                ]
            )
        )

        # Add Durable Execution permissions (for future Lambda durable features)
        controller_role.add_to_policy(
            iam.PolicyStatement(
                sid="DurableExecutionPermissions",
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:CheckpointDurableExecution",
                    "lambda:GetDurableExecutionState",
                    "lambda:ListDurableExecutions"
                ],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account}:function:*"
                ]
            )
        )

        # Add Bedrock AgentCore permissions (for agent invocation)
        controller_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockAgentCoreInvocation",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime"
                ],
                # Scope to specific ARNs in production
                resources=["*"]
            )
        )

        # Controller Lambda Function
        controller_function = lambda_.Function(
            self,
            "ControllerFunction",
            # Python 3.12 runtime on ARM64 architecture (Graviton)
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            # Handler function
            handler="handler.handler",
            # Code from controller directory
            code=lambda_.Code.from_asset("controller"),
            # Memory and timeout settings
            memory_size=1024,  # 1 GB
            timeout=Duration.minutes(15),  # Maximum Lambda timeout
            # IAM role
            role=controller_role,
            # Environment variables
            environment={
                "ARTIFACT_BUCKET": artifact_bucket.bucket_name,
                "WORKFLOW_TABLE": workflow_table.table_name,
                # Placeholder ARNs - replace with actual values after AgentCore deployment
                "RESEARCHER_AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:agent-runtime/researcher",
                "ANALYST_AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:agent-runtime/analyst",
                "WRITER_AGENT_ARN": "arn:aws:bedrock-agentcore:REGION:ACCOUNT:agent-runtime/writer",
            },
            # Enable X-Ray tracing
            tracing=lambda_.Tracing.ACTIVE,
            # Log retention
            log_retention=logs.RetentionDays.ONE_WEEK,
            # Description
            description="Durable workflow orchestration controller for multi-agent research pipeline",
            # Reserved concurrent executions (optional - uncomment for production)
            # reserved_concurrent_executions=10,
        )

        # =====================================================================
        # CALLBACK LAMBDA - Agent Completion Callbacks
        # =====================================================================

        # IAM Role for Callback Lambda
        callback_role = iam.Role(
            self,
            "CallbackRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for agent callback handler Lambda",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Grant permission to send durable execution callbacks
        callback_role.add_to_policy(
            iam.PolicyStatement(
                sid="DurableExecutionCallbacks",
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:SendDurableExecutionCallbackSuccess",
                    "lambda:SendDurableExecutionCallbackFailure"
                ],
                resources=[
                    f"{controller_function.function_arn}:*",
                    controller_function.function_arn
                ]
            )
        )

        # Callback Lambda Function
        callback_function = lambda_.Function(
            self,
            "CallbackFunction",
            # Python 3.12 runtime on ARM64 architecture
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            # Handler function
            handler="handler.handler",
            # Code from callback directory
            code=lambda_.Code.from_asset("callback"),
            # Memory and timeout settings
            memory_size=256,  # 256 MB
            timeout=Duration.seconds(30),
            # IAM role
            role=callback_role,
            # Environment variables
            environment={
                "CONTROLLER_FUNCTION_NAME": controller_function.function_name
            },
            # Log retention
            log_retention=logs.RetentionDays.ONE_WEEK,
            # Description
            description="Receives callbacks from AgentCore agents and forwards to controller",
        )

        # =====================================================================
        # API GATEWAY - REST API
        # =====================================================================

        # Create CloudWatch Log Group for API Gateway
        api_log_group = logs.LogGroup(
            self,
            "ApiGatewayLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        # REST API
        api = apigw.RestApi(
            self,
            "OrchestrationApi",
            rest_api_name="Agent Orchestration API",
            description="API for managing durable multi-agent workflows",
            # Deploy to 'v1' stage with X-Ray tracing
            deploy_options=apigw.StageOptions(
                stage_name="v1",
                # Enable X-Ray tracing
                tracing_enabled=True,
                # CloudWatch logging
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=True,
                metrics_enabled=True,
                # Access logs
                access_log_destination=apigw.LogGroupLogDestination(api_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                )
            ),
            # CORS configuration (adjust for production)
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            ),
            # Enable CloudWatch role for logging
            cloud_watch_role=True,
        )

        # Lambda integration for controller
        controller_integration = apigw.LambdaIntegration(
            controller_function,
            proxy=True,
            allow_test_invoke=True
        )

        # Lambda integration for callback
        callback_integration = apigw.LambdaIntegration(
            callback_function,
            proxy=True,
            allow_test_invoke=True
        )

        # =====================================================================
        # API ROUTES
        # =====================================================================

        # /workflows resource
        workflows_resource = api.root.add_resource("workflows")

        # POST /workflows - Start new workflow (IAM auth)
        workflows_resource.add_method(
            "POST",
            controller_integration,
            authorization_type=apigw.AuthorizationType.IAM,
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_models={
                        "application/json": apigw.Model.EMPTY_MODEL
                    }
                ),
                apigw.MethodResponse(status_code="400"),
                apigw.MethodResponse(status_code="500")
            ]
        )

        # /workflows/{workflow_id} resource
        workflow_id_resource = workflows_resource.add_resource("{workflow_id}")

        # GET /workflows/{workflow_id} - Get workflow status (IAM auth)
        workflow_id_resource.add_method(
            "GET",
            controller_integration,
            authorization_type=apigw.AuthorizationType.IAM,
            method_responses=[
                apigw.MethodResponse(status_code="200"),
                apigw.MethodResponse(status_code="404"),
                apigw.MethodResponse(status_code="500")
            ]
        )

        # /callbacks resource
        callbacks_resource = api.root.add_resource("callbacks")

        # POST /callbacks - Receive agent callbacks (no auth for simplicity)
        # Note: In production, use API key, custom authorizer, or SigV4
        callbacks_resource.add_method(
            "POST",
            callback_integration,
            authorization_type=apigw.AuthorizationType.NONE,
            method_responses=[
                apigw.MethodResponse(status_code="200"),
                apigw.MethodResponse(status_code="400"),
                apigw.MethodResponse(status_code="500")
            ]
        )

        # =====================================================================
        # STACK OUTPUTS
        # =====================================================================

        # API Gateway URL
        CfnOutput(
            self,
            "ApiUrl",
            value=api.url,
            description="API Gateway endpoint URL",
            export_name=f"{self.stack_name}-ApiUrl"
        )

        # S3 Bucket Name
        CfnOutput(
            self,
            "ArtifactBucketName",
            value=artifact_bucket.bucket_name,
            description="S3 bucket for workflow artifacts",
            export_name=f"{self.stack_name}-ArtifactBucket"
        )

        # DynamoDB Table Name
        CfnOutput(
            self,
            "WorkflowTableName",
            value=workflow_table.table_name,
            description="DynamoDB table for workflow metadata",
            export_name=f"{self.stack_name}-WorkflowTable"
        )

        # Controller Function Name
        CfnOutput(
            self,
            "ControllerFunctionName",
            value=controller_function.function_name,
            description="Controller Lambda function name",
            export_name=f"{self.stack_name}-ControllerFunction"
        )

        # Callback Function Name
        CfnOutput(
            self,
            "CallbackFunctionName",
            value=callback_function.function_name,
            description="Callback Lambda function name",
            export_name=f"{self.stack_name}-CallbackFunction"
        )


# =========================================================================
# CDK APP
# =========================================================================

app = App()

AgentOrchestrationStack(
    app,
    "AgentOrchestrationStack",
    description="Serverless Durable Agent Orchestration Platform - MVP Infrastructure",
    # Uncomment and set for specific environment
    # env=cdk.Environment(
    #     account=os.environ["CDK_DEFAULT_ACCOUNT"],
    #     region=os.environ["CDK_DEFAULT_REGION"]
    # )
)

app.synth()
