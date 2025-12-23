"""
Analyst Agent Module

This module provides analysis capabilities for the serverless durable agent
orchestration platform. It receives research data and produces structured
analysis with insights, patterns, and recommendations.
"""

__version__ = "1.0.0"
__author__ = "AgentOrchestration"

from .tools import (
    save_artifact,
    analyze_data,
    calculate_confidence_scores,
    identify_patterns,
    generate_recommendations
)

__all__ = [
    'save_artifact',
    'analyze_data',
    'calculate_confidence_scores',
    'identify_patterns',
    'generate_recommendations'
]
