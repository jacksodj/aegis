"""Tools for Writer Agent - Report formatting and artifact storage."""

import os
import json
import boto3
from datetime import datetime
from typing import Dict, Any, Optional

# Initialize AWS clients
s3 = boto3.client('s3')

# Configuration from environment
ARTIFACT_BUCKET = os.environ.get('ARTIFACT_BUCKET', 'agent-artifacts')


def save_artifact(
    content: str,
    artifact_type: str,
    workflow_id: str,
    content_type: str = 'application/json'
) -> Dict[str, Any]:
    """
    Save report artifact to S3 and return reference.

    Args:
        content: The content to save (report text, JSON, etc.)
        artifact_type: Type identifier (e.g., 'final_report', 'draft_report')
        workflow_id: Parent workflow ID for organizing artifacts
        content_type: MIME type of the content

    Returns:
        Dict containing S3 reference and presigned URL
    """
    timestamp = datetime.utcnow().isoformat()
    key = f'artifacts/{workflow_id}/{artifact_type}_{timestamp}.json'

    try:
        # Save to S3
        s3.put_object(
            Bucket=ARTIFACT_BUCKET,
            Key=key,
            Body=content.encode('utf-8') if isinstance(content, str) else content,
            ContentType=content_type,
            Metadata={
                'workflow_id': workflow_id,
                'artifact_type': artifact_type,
                'created_at': timestamp
            }
        )

        # Generate presigned URL for retrieval (24 hour expiry)
        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': ARTIFACT_BUCKET, 'Key': key},
            ExpiresIn=86400  # 24 hours
        )

        return {
            'artifact_type': 's3_reference',
            's3_uri': f's3://{ARTIFACT_BUCKET}/{key}',
            'presigned_url': presigned_url,
            'key': key,
            'bucket': ARTIFACT_BUCKET
        }

    except Exception as e:
        raise RuntimeError(f"Failed to save artifact to S3: {str(e)}")


def format_report(
    analysis_data: Dict[str, Any],
    feedback: Optional[str] = None,
    title: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format analysis data into a structured report template.

    Args:
        analysis_data: The analysis results to format
        feedback: Optional human feedback to incorporate
        title: Optional custom title for the report

    Returns:
        Structured report dictionary with all sections
    """
    # Extract data from analysis
    summary = analysis_data.get('summary', 'No summary available')
    key_findings = analysis_data.get('key_findings', [])
    insights = analysis_data.get('insights', [])
    data_points = analysis_data.get('data_points', [])
    trends = analysis_data.get('trends', [])
    recommendations = analysis_data.get('recommendations', [])
    sources = analysis_data.get('sources', [])

    # Build structured report
    report = {
        'metadata': {
            'title': title or analysis_data.get('title', 'Research Report'),
            'generated_at': datetime.utcnow().isoformat(),
            'version': '1.0',
            'feedback_incorporated': feedback is not None
        },
        'executive_summary': {
            'overview': summary,
            'key_takeaways': key_findings[:3] if key_findings else [],
            'human_feedback': feedback if feedback else None
        },
        'detailed_findings': {
            'primary_findings': key_findings,
            'insights': insights,
            'supporting_data': data_points,
            'observed_trends': trends
        },
        'recommendations': {
            'strategic_recommendations': recommendations,
            'next_steps': _generate_next_steps(recommendations),
            'considerations': _extract_considerations(analysis_data)
        },
        'references': {
            'sources': sources,
            'citations': _format_citations(sources),
            'data_sources': _extract_data_sources(data_points)
        },
        'appendix': {
            'methodology': analysis_data.get('methodology', 'Standard analysis methodology'),
            'limitations': analysis_data.get('limitations', []),
            'confidence_levels': analysis_data.get('confidence_levels', {})
        }
    }

    return report


def _generate_next_steps(recommendations: list) -> list:
    """Generate actionable next steps from recommendations."""
    if not recommendations:
        return ['Review findings', 'Identify stakeholders', 'Plan implementation']

    next_steps = []
    for idx, rec in enumerate(recommendations[:5], 1):
        if isinstance(rec, dict):
            step = f"Step {idx}: {rec.get('action', rec.get('title', 'Review recommendation'))}"
        else:
            step = f"Step {idx}: {str(rec)[:100]}"
        next_steps.append(step)

    return next_steps


def _extract_considerations(analysis_data: Dict[str, Any]) -> list:
    """Extract important considerations from analysis data."""
    considerations = []

    # Add gaps as considerations
    if 'gaps' in analysis_data:
        gaps = analysis_data['gaps']
        if isinstance(gaps, list):
            considerations.extend([f"Gap identified: {gap}" for gap in gaps])
        elif isinstance(gaps, str):
            considerations.append(f"Gap identified: {gaps}")

    # Add risks as considerations
    if 'risks' in analysis_data:
        risks = analysis_data['risks']
        if isinstance(risks, list):
            considerations.extend([f"Risk consideration: {risk}" for risk in risks])

    # Add caveats
    if 'caveats' in analysis_data:
        caveats = analysis_data['caveats']
        if isinstance(caveats, list):
            considerations.extend(caveats)

    return considerations if considerations else ['No special considerations identified']


def _format_citations(sources: list) -> list:
    """Format sources into proper citations."""
    citations = []

    for idx, source in enumerate(sources, 1):
        if isinstance(source, dict):
            citation = {
                'number': idx,
                'title': source.get('title', 'Untitled'),
                'url': source.get('url', source.get('link', '')),
                'accessed': source.get('accessed', datetime.utcnow().isoformat()),
                'type': source.get('type', 'web')
            }
        else:
            citation = {
                'number': idx,
                'reference': str(source),
                'type': 'general'
            }
        citations.append(citation)

    return citations


def _extract_data_sources(data_points: list) -> list:
    """Extract unique data sources from data points."""
    sources = set()

    for point in data_points:
        if isinstance(point, dict):
            source = point.get('source', point.get('origin'))
            if source:
                sources.add(source)

    return list(sources) if sources else ['Primary research']


def generate_markdown_report(report_data: Dict[str, Any]) -> str:
    """
    Generate a markdown-formatted version of the report.

    Args:
        report_data: Structured report dictionary

    Returns:
        Markdown-formatted report string
    """
    metadata = report_data.get('metadata', {})
    exec_summary = report_data.get('executive_summary', {})
    findings = report_data.get('detailed_findings', {})
    recommendations = report_data.get('recommendations', {})
    references = report_data.get('references', {})
    appendix = report_data.get('appendix', {})

    md_lines = [
        f"# {metadata.get('title', 'Research Report')}",
        "",
        f"**Generated:** {metadata.get('generated_at', 'N/A')}  ",
        f"**Version:** {metadata.get('version', '1.0')}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        exec_summary.get('overview', 'No summary available'),
        "",
    ]

    # Key takeaways
    if exec_summary.get('key_takeaways'):
        md_lines.extend([
            "### Key Takeaways",
            "",
        ])
        for takeaway in exec_summary['key_takeaways']:
            md_lines.append(f"- {takeaway}")
        md_lines.append("")

    # Human feedback
    if exec_summary.get('human_feedback'):
        md_lines.extend([
            "### Incorporated Feedback",
            "",
            exec_summary['human_feedback'],
            "",
        ])

    md_lines.extend([
        "---",
        "",
        "## Detailed Findings",
        "",
    ])

    # Primary findings
    if findings.get('primary_findings'):
        md_lines.extend([
            "### Primary Findings",
            "",
        ])
        for finding in findings['primary_findings']:
            if isinstance(finding, dict):
                md_lines.append(f"**{finding.get('title', 'Finding')}:** {finding.get('description', '')}")
            else:
                md_lines.append(f"- {finding}")
        md_lines.append("")

    # Insights
    if findings.get('insights'):
        md_lines.extend([
            "### Key Insights",
            "",
        ])
        for insight in findings['insights']:
            md_lines.append(f"- {insight}")
        md_lines.append("")

    # Recommendations
    md_lines.extend([
        "---",
        "",
        "## Recommendations",
        "",
    ])

    if recommendations.get('strategic_recommendations'):
        md_lines.extend([
            "### Strategic Recommendations",
            "",
        ])
        for rec in recommendations['strategic_recommendations']:
            if isinstance(rec, dict):
                md_lines.append(f"**{rec.get('title', 'Recommendation')}:** {rec.get('description', '')}")
            else:
                md_lines.append(f"- {rec}")
        md_lines.append("")

    if recommendations.get('next_steps'):
        md_lines.extend([
            "### Next Steps",
            "",
        ])
        for step in recommendations['next_steps']:
            md_lines.append(f"{step}")
        md_lines.append("")

    # References
    md_lines.extend([
        "---",
        "",
        "## References",
        "",
    ])

    if references.get('citations'):
        for citation in references['citations']:
            if isinstance(citation, dict):
                num = citation.get('number', '')
                title = citation.get('title', citation.get('reference', ''))
                url = citation.get('url', '')
                if url:
                    md_lines.append(f"{num}. [{title}]({url})")
                else:
                    md_lines.append(f"{num}. {title}")
        md_lines.append("")

    # Appendix
    if appendix.get('methodology') or appendix.get('limitations'):
        md_lines.extend([
            "---",
            "",
            "## Appendix",
            "",
        ])

        if appendix.get('methodology'):
            md_lines.extend([
                "### Methodology",
                "",
                appendix['methodology'],
                "",
            ])

        if appendix.get('limitations'):
            md_lines.extend([
                "### Limitations",
                "",
            ])
            for limitation in appendix['limitations']:
                md_lines.append(f"- {limitation}")
            md_lines.append("")

    return "\n".join(md_lines)
