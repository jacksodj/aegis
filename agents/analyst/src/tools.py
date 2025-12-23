"""
Tools for the Analyst Agent
"""
import os
import json
import boto3
from datetime import datetime
from typing import Dict, List, Any

# Initialize AWS clients
s3 = boto3.client('s3')
ARTIFACT_BUCKET = os.environ.get('ARTIFACT_BUCKET')


def save_artifact(content: str, artifact_type: str, workflow_id: str) -> Dict[str, str]:
    """
    Save large content to S3 and return reference.

    Args:
        content: The content to save
        artifact_type: Type of artifact (e.g., 'analysis_results')
        workflow_id: Parent workflow identifier

    Returns:
        Dictionary with S3 reference information
    """
    if not ARTIFACT_BUCKET:
        raise ValueError("ARTIFACT_BUCKET environment variable not set")

    key = f'artifacts/{workflow_id}/{artifact_type}_{datetime.utcnow().isoformat()}.json'

    s3.put_object(
        Bucket=ARTIFACT_BUCKET,
        Key=key,
        Body=content if isinstance(content, bytes) else content.encode('utf-8'),
        ContentType='application/json',
        Metadata={
            'workflow_id': workflow_id,
            'artifact_type': artifact_type,
            'created_at': datetime.utcnow().isoformat()
        }
    )

    return {
        'artifact_type': 's3_reference',
        's3_uri': f's3://{ARTIFACT_BUCKET}/{key}',
        'bucket': ARTIFACT_BUCKET,
        'key': key
    }


def analyze_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper function to perform structured data analysis.

    Args:
        data: Dictionary containing data to analyze

    Returns:
        Structured analysis results
    """
    analysis = {
        'metadata': {
            'analyzed_at': datetime.utcnow().isoformat(),
            'data_size': len(json.dumps(data)),
        },
        'statistics': {},
        'patterns': [],
        'insights': []
    }

    # Extract key findings if present
    if 'key_findings' in data:
        findings = data['key_findings']
        analysis['statistics']['total_findings'] = len(findings) if isinstance(findings, list) else 0

    # Extract sources if present
    if 'sources' in data:
        sources = data['sources']
        analysis['statistics']['total_sources'] = len(sources) if isinstance(sources, list) else 0

    # Extract data points if present
    if 'data_points' in data:
        data_points = data['data_points']
        analysis['statistics']['total_data_points'] = len(data_points) if isinstance(data_points, list) else 0

    # Identify patterns based on data structure
    if 'summary' in data:
        analysis['patterns'].append({
            'type': 'summary_available',
            'description': 'Research includes executive summary',
            'confidence': 1.0
        })

    # Add basic insights
    if analysis['statistics'].get('total_findings', 0) > 5:
        analysis['insights'].append({
            'category': 'research_depth',
            'description': 'Comprehensive research with multiple findings',
            'confidence': 0.9
        })

    return analysis


def calculate_confidence_scores(data: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculate confidence scores for different aspects of the analysis.

    Args:
        data: Data to evaluate

    Returns:
        Dictionary of confidence scores by category
    """
    scores = {
        'data_completeness': 0.0,
        'source_reliability': 0.0,
        'finding_consistency': 0.0,
        'overall': 0.0
    }

    # Data completeness score
    required_fields = ['summary', 'key_findings', 'sources']
    present_fields = sum(1 for field in required_fields if field in data)
    scores['data_completeness'] = present_fields / len(required_fields)

    # Source reliability (based on number of sources)
    if 'sources' in data:
        source_count = len(data['sources']) if isinstance(data['sources'], list) else 0
        # More sources generally means higher confidence, capped at 1.0
        scores['source_reliability'] = min(1.0, source_count / 5.0)

    # Finding consistency (placeholder - would need more sophisticated analysis)
    if 'key_findings' in data:
        finding_count = len(data['key_findings']) if isinstance(data['key_findings'], list) else 0
        scores['finding_consistency'] = min(1.0, finding_count / 3.0)

    # Overall confidence (average of other scores)
    score_values = [v for k, v in scores.items() if k != 'overall']
    scores['overall'] = sum(score_values) / len(score_values) if score_values else 0.0

    return scores


def identify_patterns(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Identify patterns in the research data.

    Args:
        data: Research data to analyze

    Returns:
        List of identified patterns
    """
    patterns = []

    # Check for temporal patterns
    if 'data_points' in data and isinstance(data['data_points'], list):
        has_dates = any('date' in str(dp).lower() or 'time' in str(dp).lower()
                       for dp in data['data_points'])
        if has_dates:
            patterns.append({
                'type': 'temporal',
                'description': 'Time-series data detected',
                'confidence': 0.8
            })

    # Check for quantitative patterns
    if 'data_points' in data and isinstance(data['data_points'], list):
        has_numbers = any(isinstance(dp, (int, float)) or
                         any(char.isdigit() for char in str(dp))
                         for dp in data['data_points'])
        if has_numbers:
            patterns.append({
                'type': 'quantitative',
                'description': 'Numerical data available for analysis',
                'confidence': 0.9
            })

    # Check for gaps
    if 'gaps' in data and data['gaps']:
        patterns.append({
            'type': 'research_gaps',
            'description': 'Areas identified needing further research',
            'confidence': 1.0,
            'gaps': data['gaps']
        })

    return patterns


def generate_recommendations(
    analysis: Dict[str, Any],
    patterns: List[Dict[str, Any]],
    confidence_scores: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    Generate recommendations based on analysis, patterns, and confidence scores.

    Args:
        analysis: Analysis results
        patterns: Identified patterns
        confidence_scores: Confidence scores

    Returns:
        List of recommendations
    """
    recommendations = []

    # Recommend additional research if confidence is low
    if confidence_scores['overall'] < 0.7:
        recommendations.append({
            'priority': 'high',
            'category': 'research_quality',
            'action': 'Gather additional sources to increase confidence',
            'rationale': f"Overall confidence score is {confidence_scores['overall']:.2f}, below threshold of 0.70"
        })

    # Recommend addressing research gaps
    gap_patterns = [p for p in patterns if p['type'] == 'research_gaps']
    if gap_patterns:
        for gap_pattern in gap_patterns:
            if 'gaps' in gap_pattern:
                recommendations.append({
                    'priority': 'medium',
                    'category': 'research_gaps',
                    'action': 'Address identified research gaps',
                    'gaps': gap_pattern['gaps']
                })

    # Recommend quantitative analysis if numerical data is available
    quant_patterns = [p for p in patterns if p['type'] == 'quantitative']
    if quant_patterns:
        recommendations.append({
            'priority': 'medium',
            'category': 'analysis_depth',
            'action': 'Perform quantitative analysis on numerical data',
            'rationale': 'Numerical data patterns detected'
        })

    # General recommendation for high-quality research
    if confidence_scores['overall'] >= 0.8:
        recommendations.append({
            'priority': 'low',
            'category': 'proceed',
            'action': 'Research quality is high, proceed to next phase',
            'rationale': f"Overall confidence score is {confidence_scores['overall']:.2f}"
        })

    return recommendations
