"""
test_api.py — Tests for JSON API endpoints (/ping, /api/chat).
"""
import pytest
import json


class TestPingEndpoint:
    def test_ping_returns_200(self, client):
        """Health check endpoint should always be reachable."""
        res = client.get("/ping")
        assert res.status_code == 200

    def test_ping_returns_json(self, client):
        """Health check should return JSON with status: success."""
        res = client.get("/ping")
        data = json.loads(res.data)
        assert data["status"] == "success"
        assert "message" in data


class TestChatbot:
    def _post_message(self, client, message):
        return client.post("/api/chat",
            data=json.dumps({"message": message}),
            content_type="application/json"
        )

    def test_chat_returns_json(self, client):
        """Chat endpoint should return JSON with a 'reply' key."""
        res = self._post_message(client, "hello")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert "reply" in data

    def test_chat_hours_query(self, client):
        """Asking about 'hours' should trigger the hours response."""
        res = self._post_message(client, "what are your hours")
        data = json.loads(res.data)
        assert "24/7" in data["reply"] or "hours" in data["reply"].lower()

    def test_chat_booking_query(self, client):
        """Asking about 'book' should trigger the booking response."""
        res = self._post_message(client, "how do I book a class")
        data = json.loads(res.data)
        assert "Classes" in data["reply"] or "book" in data["reply"].lower()

    def test_chat_cancel_query(self, client):
        """Asking about 'cancel' should trigger the cancellation response."""
        res = self._post_message(client, "how do I cancel")
        data = json.loads(res.data)
        assert "cancel" in data["reply"].lower() or "Dashboard" in data["reply"]

    def test_chat_human_query_includes_whatsapp(self, client):
        """Asking to speak to a human should return a WhatsApp link."""
        res = self._post_message(client, "I need a human")
        data = json.loads(res.data)
        assert "wa.me" in data["reply"] or "WhatsApp" in data["reply"]

    def test_chat_unknown_query_returns_fallback(self, client):
        """An unrecognized query should return the fallback message."""
        res = self._post_message(client, "xyzzy foobar gibberish")
        data = json.loads(res.data)
        assert len(data["reply"]) > 0  # Always returns something

    def test_chat_empty_message(self, client):
        """An empty message body should not crash the server."""
        res = client.post("/api/chat",
            data=json.dumps({}),
            content_type="application/json"
        )
        assert res.status_code == 200