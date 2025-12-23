"""
Unit tests for the callback handler.

Run with: python -m pytest test_handler.py
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from handler import (
    parse_request_body,
    validate_callback_payload,
    create_response,
    handler
)


class TestParseRequestBody:
    """Test request body parsing."""

    def test_parse_valid_json_string(self):
        """Should parse valid JSON string."""
        event = {'body': '{"token": "abc123", "status": "SUCCESS"}'}
        result = parse_request_body(event)
        assert result == {"token": "abc123", "status": "SUCCESS"}

    def test_parse_dict_body(self):
        """Should handle dict body directly."""
        event = {'body': {"token": "abc123", "status": "SUCCESS"}}
        result = parse_request_body(event)
        assert result == {"token": "abc123", "status": "SUCCESS"}

    def test_parse_invalid_json(self):
        """Should return None for invalid JSON."""
        event = {'body': '{invalid json}'}
        result = parse_request_body(event)
        assert result is None

    def test_parse_empty_body(self):
        """Should handle empty body."""
        event = {}
        result = parse_request_body(event)
        assert result == {}


class TestValidateCallbackPayload:
    """Test payload validation."""

    def test_valid_success_payload(self):
        """Should accept valid SUCCESS payload."""
        body = {
            "token": "abc123",
            "status": "SUCCESS",
            "result": {"data": "test"}
        }
        is_valid, error = validate_callback_payload(body)
        assert is_valid is True
        assert error is None

    def test_valid_failure_payload(self):
        """Should accept valid FAILURE payload."""
        body = {
            "token": "abc123",
            "status": "FAILURE",
            "error": "Something went wrong"
        }
        is_valid, error = validate_callback_payload(body)
        assert is_valid is True
        assert error is None

    def test_missing_token(self):
        """Should reject payload without token."""
        body = {"status": "SUCCESS", "result": {}}
        is_valid, error = validate_callback_payload(body)
        assert is_valid is False
        assert "token" in error

    def test_missing_status(self):
        """Should reject payload without status."""
        body = {"token": "abc123", "result": {}}
        is_valid, error = validate_callback_payload(body)
        assert is_valid is False
        assert "status" in error

    def test_invalid_status(self):
        """Should reject invalid status value."""
        body = {"token": "abc123", "status": "PENDING", "result": {}}
        is_valid, error = validate_callback_payload(body)
        assert is_valid is False
        assert "Invalid status" in error

    def test_success_without_result(self):
        """Should reject SUCCESS without result."""
        body = {"token": "abc123", "status": "SUCCESS"}
        is_valid, error = validate_callback_payload(body)
        assert is_valid is False
        assert "result" in error

    def test_failure_without_error(self):
        """Should reject FAILURE without error."""
        body = {"token": "abc123", "status": "FAILURE"}
        is_valid, error = validate_callback_payload(body)
        assert is_valid is False
        assert "error" in error


class TestCreateResponse:
    """Test response formatting."""

    def test_create_success_response(self):
        """Should create proper success response."""
        response = create_response(200, {"status": "ok"})
        assert response['statusCode'] == 200
        assert 'Content-Type' in response['headers']
        assert json.loads(response['body']) == {"status": "ok"}

    def test_create_error_response(self):
        """Should create proper error response."""
        response = create_response(400, {"error": "Bad request"})
        assert response['statusCode'] == 400
        assert json.loads(response['body']) == {"error": "Bad request"}


class TestHandler:
    """Test main handler function."""

    @patch('handler.store_callback_result')
    @patch('handler.update_workflow_status')
    def test_successful_callback(self, mock_update, mock_store):
        """Should handle successful callback."""
        mock_store.return_value = True
        mock_update.return_value = True

        event = {
            'body': json.dumps({
                'token': 'test123',
                'status': 'SUCCESS',
                'result': {'data': 'test'}
            }),
            'requestContext': {'identity': {'sourceIp': '1.2.3.4'}}
        }
        context = Mock(request_id='req123')

        response = handler(event, context)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'callback_delivered'
        assert body['token'] == 'test123'
        mock_store.assert_called_once()
        mock_update.assert_called_once()

    @patch('handler.store_callback_result')
    @patch('handler.update_workflow_status')
    def test_failed_callback(self, mock_update, mock_store):
        """Should handle failed callback."""
        mock_store.return_value = True
        mock_update.return_value = True

        event = {
            'body': json.dumps({
                'token': 'test123',
                'status': 'FAILURE',
                'error': 'Task failed'
            }),
            'requestContext': {'identity': {'sourceIp': '1.2.3.4'}}
        }
        context = Mock(request_id='req123')

        response = handler(event, context)

        assert response['statusCode'] == 200
        mock_store.assert_called_once_with('test123', 'FAILURE', None, 'Task failed')

    def test_invalid_json(self):
        """Should reject invalid JSON."""
        event = {
            'body': '{invalid}',
            'requestContext': {'identity': {'sourceIp': '1.2.3.4'}}
        }
        context = Mock(request_id='req123')

        response = handler(event, context)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body

    def test_missing_token(self):
        """Should reject request without token."""
        event = {
            'body': json.dumps({
                'status': 'SUCCESS',
                'result': {}
            }),
            'requestContext': {'identity': {'sourceIp': '1.2.3.4'}}
        }
        context = Mock(request_id='req123')

        response = handler(event, context)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'token' in body['error']

    @patch('handler.store_callback_result')
    @patch('handler.update_workflow_status')
    def test_storage_failure(self, mock_update, mock_store):
        """Should return 500 if storage fails."""
        mock_store.return_value = False

        event = {
            'body': json.dumps({
                'token': 'test123',
                'status': 'SUCCESS',
                'result': {'data': 'test'}
            }),
            'requestContext': {'identity': {'sourceIp': '1.2.3.4'}}
        }
        context = Mock(request_id='req123')

        response = handler(event, context)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'Failed to store' in body['error']
