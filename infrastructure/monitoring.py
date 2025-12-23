"""
CloudWatch Dashboard and Monitoring Configuration

This module defines observability resources for the serverless durable agent
orchestration platform including CloudWatch dashboards, alarms, and log groups.
"""

from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_logs as logs,
    Duration,
)
from constructs import Construct


class MonitoringConstruct(Construct):
    """
    Creates CloudWatch dashboard and alarms for the orchestration platform.
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        controller_function_name: str,
        callback_function_name: str,
        workflow_table_name: str,
        artifact_bucket_name: str,
        api_name: str,
        **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        # Create SNS topic for alerts
        self.alert_topic = sns.Topic(
            self, "AlertTopic",
            display_name="Agent Orchestration Alerts"
        )

        # Create CloudWatch Dashboard
        self.dashboard = cloudwatch.Dashboard(
            self, "Dashboard",
            dashboard_name="AgentOrchestrationDashboard",
            default_interval=Duration.hours(3)
        )

        # Lambda Metrics - Controller
        controller_invocations = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Invocations",
            dimensions_map={"FunctionName": controller_function_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        controller_errors = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": controller_function_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        controller_duration = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Duration",
            dimensions_map={"FunctionName": controller_function_name},
            statistic="p99",
            period=Duration.minutes(1)
        )

        controller_concurrent = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="ConcurrentExecutions",
            dimensions_map={"FunctionName": controller_function_name},
            statistic="Maximum",
            period=Duration.minutes(1)
        )

        # Lambda Metrics - Callback
        callback_invocations = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Invocations",
            dimensions_map={"FunctionName": callback_function_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        callback_errors = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": callback_function_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        # DynamoDB Metrics
        dynamo_read_capacity = cloudwatch.Metric(
            namespace="AWS/DynamoDB",
            metric_name="ConsumedReadCapacityUnits",
            dimensions_map={"TableName": workflow_table_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        dynamo_write_capacity = cloudwatch.Metric(
            namespace="AWS/DynamoDB",
            metric_name="ConsumedWriteCapacityUnits",
            dimensions_map={"TableName": workflow_table_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        dynamo_throttled = cloudwatch.Metric(
            namespace="AWS/DynamoDB",
            metric_name="ThrottledRequests",
            dimensions_map={"TableName": workflow_table_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        # API Gateway Metrics
        api_requests = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="Count",
            dimensions_map={"ApiName": api_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        api_latency = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="Latency",
            dimensions_map={"ApiName": api_name},
            statistic="p99",
            period=Duration.minutes(1)
        )

        api_4xx_errors = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="4XXError",
            dimensions_map={"ApiName": api_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        api_5xx_errors = cloudwatch.Metric(
            namespace="AWS/ApiGateway",
            metric_name="5XXError",
            dimensions_map={"ApiName": api_name},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        # Add widgets to dashboard
        self.dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown="# Agent Orchestration Platform\n\nReal-time monitoring for the serverless durable agent orchestration system.",
                width=24,
                height=2
            )
        )

        # Controller Lambda Row
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Controller Lambda - Invocations & Errors",
                left=[controller_invocations],
                right=[controller_errors],
                width=8,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Controller Lambda - Duration (p99)",
                left=[controller_duration],
                width=8,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="Controller Lambda - Concurrent Executions",
                left=[controller_concurrent],
                width=8,
                height=6
            )
        )

        # Callback Lambda Row
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Callback Lambda - Invocations & Errors",
                left=[callback_invocations],
                right=[callback_errors],
                width=12,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Total Callbacks (24h)",
                metrics=[callback_invocations],
                width=6,
                height=6
            ),
            cloudwatch.SingleValueWidget(
                title="Callback Errors (24h)",
                metrics=[callback_errors],
                width=6,
                height=6
            )
        )

        # DynamoDB Row
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="DynamoDB - Read/Write Capacity",
                left=[dynamo_read_capacity],
                right=[dynamo_write_capacity],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="DynamoDB - Throttled Requests",
                left=[dynamo_throttled],
                width=12,
                height=6
            )
        )

        # API Gateway Row
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Gateway - Requests & Latency",
                left=[api_requests],
                right=[api_latency],
                width=12,
                height=6
            ),
            cloudwatch.GraphWidget(
                title="API Gateway - Errors (4XX/5XX)",
                left=[api_4xx_errors, api_5xx_errors],
                width=12,
                height=6
            )
        )

        # Create Alarms
        self._create_alarms(
            controller_errors=controller_errors,
            callback_errors=callback_errors,
            dynamo_throttled=dynamo_throttled,
            api_5xx_errors=api_5xx_errors
        )

    def _create_alarms(
        self,
        controller_errors: cloudwatch.Metric,
        callback_errors: cloudwatch.Metric,
        dynamo_throttled: cloudwatch.Metric,
        api_5xx_errors: cloudwatch.Metric
    ):
        """Create CloudWatch alarms for critical metrics."""

        # Controller Lambda Error Alarm
        controller_error_alarm = cloudwatch.Alarm(
            self, "ControllerErrorAlarm",
            metric=controller_errors,
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Controller Lambda errors exceeded threshold",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        controller_error_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alert_topic)
        )

        # Callback Lambda Error Alarm
        callback_error_alarm = cloudwatch.Alarm(
            self, "CallbackErrorAlarm",
            metric=callback_errors,
            threshold=10,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="Callback Lambda errors exceeded threshold",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        callback_error_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alert_topic)
        )

        # DynamoDB Throttling Alarm
        dynamo_throttle_alarm = cloudwatch.Alarm(
            self, "DynamoThrottleAlarm",
            metric=dynamo_throttled,
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="DynamoDB throttling detected",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        dynamo_throttle_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alert_topic)
        )

        # API 5XX Error Alarm
        api_error_alarm = cloudwatch.Alarm(
            self, "Api5xxErrorAlarm",
            metric=api_5xx_errors,
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description="API Gateway 5XX errors exceeded threshold",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        api_error_alarm.add_alarm_action(
            cw_actions.SnsAction(self.alert_topic)
        )


# CloudWatch Log Insights Queries for troubleshooting
LOG_INSIGHTS_QUERIES = {
    "workflow_errors": """
        fields @timestamp, @message, workflow_id, error
        | filter @message like /ERROR/
        | sort @timestamp desc
        | limit 100
    """,

    "workflow_duration": """
        fields @timestamp, workflow_id, step_name, duration_ms
        | filter step_name in ['research_phase', 'analysis_phase', 'writing_phase']
        | stats avg(duration_ms) as avg_duration, max(duration_ms) as max_duration by step_name
    """,

    "callback_status": """
        fields @timestamp, token, status, workflow_id
        | filter @message like /callback/
        | stats count(*) as callback_count by status
    """,

    "agent_invocations": """
        fields @timestamp, workflow_id, agent_type, status
        | filter @message like /invoke_agent/
        | stats count(*) as invocation_count by agent_type, status
    """,

    "approval_wait_times": """
        fields @timestamp, workflow_id, wait_duration_hours
        | filter step_name = 'human_approval'
        | stats avg(wait_duration_hours) as avg_wait, max(wait_duration_hours) as max_wait
    """
}


# X-Ray Tracing Configuration
XRAY_SAMPLING_RULES = {
    "version": 2,
    "rules": [
        {
            "description": "Sample all workflow starts",
            "host": "*",
            "http_method": "POST",
            "url_path": "/workflows",
            "fixed_target": 1,
            "rate": 1.0
        },
        {
            "description": "Sample callbacks at 50%",
            "host": "*",
            "http_method": "POST",
            "url_path": "/callbacks",
            "fixed_target": 1,
            "rate": 0.5
        },
        {
            "description": "Default rule",
            "host": "*",
            "http_method": "*",
            "url_path": "*",
            "fixed_target": 1,
            "rate": 0.1
        }
    ],
    "default": {
        "fixed_target": 1,
        "rate": 0.1
    }
}
