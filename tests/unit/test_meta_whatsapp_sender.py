import json

import httpx
import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.core.events import MediaRef
from whatsapp_ai_agent.integrations.whatsapp_meta.sender import (
    MetaGraphApiError,
    MetaWhatsAppSender,
)
from whatsapp_ai_agent.media.downloader import MetaMediaDownloader


@pytest.mark.asyncio
async def test_meta_sender_posts_graph_text_message_with_bearer_token():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.outbound-1"}]})

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        message_id = await MetaWhatsAppSender(settings=settings, http_client=client).send_text(
            to="2348012345678",
            body="Your work update has been saved.",
        )

    assert message_id == "wamid.outbound-1"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://graph.example.test/v23.0/1234567890123456/messages"
    assert request.headers["authorization"] == "Bearer meta-access-token"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "2348012345678",
        "type": "text",
        "text": {"body": "Your work update has been saved."},
    }


@pytest.mark.asyncio
async def test_meta_sender_posts_graph_document_message():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.document-1"}]})

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        message_id = await MetaWhatsAppSender(settings=settings, http_client=client).send_document(
            to="+2348012345678",
            body="Weekly report",
            filename="weekly-report.docx",
            document_url="https://files.example.test/report.docx",
        )

    assert message_id == "wamid.document-1"
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["type"] == "document"
    assert payload["document"]["link"] == "https://files.example.test/report.docx"
    assert payload["document"]["filename"] == "weekly-report.docx"


@pytest.mark.asyncio
async def test_meta_sender_surfaces_safe_graph_error_details_without_access_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Recipient is not an allowed test recipient",
                    "type": "OAuthException",
                    "code": 131030,
                    "error_subcode": 2494013,
                    "error_data": {"details": "Add the recipient in the WhatsApp API setup."},
                    "fbtrace_id": "trace-123",
                }
            },
        )

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MetaGraphApiError) as exc_info:
            await MetaWhatsAppSender(settings=settings, http_client=client).send_text(
                to="2348012345678",
                body="Your work update has been saved.",
            )

    error_text = str(exc_info.value)
    assert "status=400" in error_text
    assert "code=131030" in error_text
    assert "Add the recipient" in error_text
    assert "meta-access-token" not in error_text


@pytest.mark.asyncio
async def test_meta_media_downloader_retrieves_metadata_then_file_bytes():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v23.0/media-image-1":
            return httpx.Response(
                200,
                json={
                    "url": "https://download.example.test/meta/media-image-1",
                    "mime_type": "image/jpeg",
                    "filename": "site-photo.jpg",
                },
            )
        assert str(request.url) == "https://download.example.test/meta/media-image-1"
        return httpx.Response(
            200,
            content=b"jpeg-bytes",
            headers={"content-type": "image/jpeg"},
        )

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        downloaded = await MetaMediaDownloader(settings, http_client=client).download(
            MediaRef(platform_media_id="media-image-1", content_type="image/jpeg", index=0)
        )

    assert downloaded.data == b"jpeg-bytes"
    assert downloaded.content_type == "image/jpeg"
    assert downloaded.filename == "site-photo.jpg"
    assert [request.headers["authorization"] for request in requests] == [
        "Bearer meta-access-token",
        "Bearer meta-access-token",
    ]


@pytest.mark.asyncio
async def test_meta_media_downloader_rejects_missing_media_id():
    settings = Settings(meta_access_token="meta-access-token", _env_file=None)

    with pytest.raises(RuntimeError, match="platform_media_id"):
        await MetaMediaDownloader(settings).download(MediaRef(index=0))


@pytest.mark.asyncio
async def test_meta_sender_posts_read_receipt_and_typing_indicator():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True})

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await MetaWhatsAppSender(settings=settings, http_client=client).send_typing_indicator(
            to="+234****5678",
            message_id="wamid.HBgLMTY1MDM4Nzk0MzkVAgARGBJDQjZCMzlEQUE4OTJBMTE4RTUA",
        )

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://graph.example.test/v23.0/1234567890123456/messages"
    assert request.headers["authorization"] == "Bearer meta-access-token"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.HBgLMTY1MDM4Nzk0MzkVAgARGBJDQjZCMzlEQUE4OTJBMTE4RTUA",
        "typing_indicator": {"type": "text"},
    }


@pytest.mark.asyncio
async def test_meta_sender_typing_indicator_is_best_effort_on_failure():
    # A failing typing indicator must not raise; the caller still sends the reply.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad", "code": 1}})

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        # Should not raise even though the API returns 400.
        await MetaWhatsAppSender(settings=settings, http_client=client).send_typing_indicator(
            to="+234****5678",
            message_id="wamid.HBgLMTY1MDM4Nzk0MzkVAgARGBJDQjZCMzlEQUE4OTJBMTE4RTUA",
        )


@pytest.mark.asyncio
async def test_meta_sender_uploads_media_then_sends_by_id(tmp_path):
    # send_document_file should POST to /media first (upload), then POST to
    # /messages with document.id (not a public link), so it works on local storage.
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-abc-123"})
        return httpx.Response(200, json={"messages": [{"id": "wamid.outbound-doc"}]})

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    doc = tmp_path / "weekly-report.docx"
    doc.write_bytes(b"PK\x03\x04 fake docx bytes")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        message_id = await MetaWhatsAppSender(
            settings=settings, http_client=client
        ).send_document_file(
            to="+234****5678",
            body="Your weekly report",
            filename="weekly-report.docx",
            document_path=doc,
        )

    assert message_id == "wamid.outbound-doc"
    assert len(requests) == 2
    upload, send = requests
    assert upload.url.path == "/v23.0/1234567890123456/media"
    assert send.url.path == "/v23.0/1234567890123456/messages"
    sent_payload = json.loads(send.content)
    assert sent_payload["type"] == "document"
    # Delivered by media id, not a public link.
    assert sent_payload["document"]["id"] == "media-abc-123"
    assert "link" not in sent_payload["document"]


@pytest.mark.asyncio
async def test_meta_sender_send_document_uses_public_link_when_provided():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"messages": [{"id": "wamid.link-doc"}]})

    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        message_id = await MetaWhatsAppSender(settings=settings, http_client=client).send_document(
            to="+234****5678",
            body="Report",
            filename="report.docx",
            document_url="https://cdn.example.test/report.docx",
        )

    assert message_id == "wamid.link-doc"
    sent = json.loads(requests[0].content)
    assert sent["document"]["link"] == "https://cdn.example.test/report.docx"
    assert "id" not in sent["document"]


@pytest.mark.asyncio
async def test_meta_sender_send_document_rejects_missing_url():
    settings = Settings(
        meta_graph_api_base_url="https://graph.example.test",
        meta_graph_api_version="v23.0",
        meta_phone_number_id="1234567890123456",
        meta_access_token="meta-access-token",
        _env_file=None,
    )
    with pytest.raises(ValueError, match="document_url"):
        await MetaWhatsAppSender(settings=settings).send_document(
            to="+234****5678", body="Report", filename="report.docx"
        )
