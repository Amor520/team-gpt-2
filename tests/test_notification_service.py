import re
import unittest
from unittest.mock import patch

from app.services.notification import NotificationService


class DummyResponse:
    def raise_for_status(self):
        return None


class RecordingAsyncClient:
    def __init__(self, calls, *args, **kwargs):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, headers=None):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers or {},
            }
        )
        return DummyResponse()


class NotificationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_generic_webhook_keeps_original_payload_and_api_key(self):
        service = NotificationService()
        calls = []

        def client_factory(*args, **kwargs):
            return RecordingAsyncClient(calls, *args, **kwargs)

        with patch("app.services.notification.httpx.AsyncClient", side_effect=client_factory):
            result = await service.send_webhook_notification(
                "https://webhook.site/example",
                available_seats=2,
                threshold=6,
                api_key="demo-key",
            )

        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        request = calls[0]
        self.assertEqual(request["headers"], {"X-API-Key": "demo-key"})
        self.assertEqual(
            request["json"],
            {
                "event": "low_stock",
                "current_seats": 2,
                "threshold": 6,
                "message": "库存不足预警：系统总可用车位仅剩 2，已低于预警阈值 6，请及时补货导入新账号。",
            },
        )

    async def test_wecom_webhook_uses_enterprise_wechat_text_payload(self):
        service = NotificationService()
        calls = []

        def client_factory(*args, **kwargs):
            return RecordingAsyncClient(calls, *args, **kwargs)

        with patch("app.services.notification.httpx.AsyncClient", side_effect=client_factory):
            result = await service.send_webhook_notification(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key",
                available_seats=2,
                threshold=6,
                api_key="ignored-key",
            )

        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        request = calls[0]
        self.assertEqual(request["headers"], {})
        self.assertEqual(request["json"]["msgtype"], "markdown")
        content = request["json"]["markdown"]["content"]
        self.assertIn("GPT Team <font color=\"warning\">库存预警</font>", content)
        self.assertIn("当前总可用车位：<font color=\"warning\">2</font>", content)
        self.assertIn("预警阈值：<font color=\"comment\">6</font>", content)
        self.assertIn("库存不足预警：系统总可用车位仅剩 2，已低于预警阈值 6，请及时补货导入新账号。", content)
        self.assertRegex(content, r"发送时间：<font color=\"comment\">\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}</font>")

    async def test_generic_test_webhook_uses_test_payload(self):
        service = NotificationService()
        calls = []

        def client_factory(*args, **kwargs):
            return RecordingAsyncClient(calls, *args, **kwargs)

        with patch("app.services.notification.httpx.AsyncClient", side_effect=client_factory):
            result = await service.send_webhook_notification(
                "https://webhook.site/example",
                available_seats=4,
                threshold=6,
                api_key="demo-key",
                is_test=True,
            )

        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        request = calls[0]
        self.assertEqual(request["headers"], {"X-API-Key": "demo-key"})
        self.assertEqual(
            request["json"],
            {
                "event": "low_stock_test",
                "current_seats": 4,
                "threshold": 6,
                "message": "库存预警测试：系统当前总可用车位为 4，当前预警阈值为 6。",
            },
        )

    async def test_wecom_test_webhook_uses_test_message(self):
        service = NotificationService()
        calls = []

        def client_factory(*args, **kwargs):
            return RecordingAsyncClient(calls, *args, **kwargs)

        with patch("app.services.notification.httpx.AsyncClient", side_effect=client_factory):
            result = await service.send_webhook_notification(
                "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key",
                available_seats=4,
                threshold=6,
                is_test=True,
            )

        self.assertTrue(result)
        self.assertEqual(len(calls), 1)
        request = calls[0]
        self.assertEqual(request["headers"], {})
        self.assertEqual(request["json"]["msgtype"], "markdown")
        content = request["json"]["markdown"]["content"]
        self.assertIn("GPT Team <font color=\"comment\">库存测试</font>", content)
        self.assertIn("当前总可用车位：<font color=\"warning\">4</font>", content)
        self.assertIn("预警阈值：<font color=\"comment\">6</font>", content)
        self.assertIn("库存预警测试：系统当前总可用车位为 4，当前预警阈值为 6。", content)
        self.assertRegex(content, r"发送时间：<font color=\"comment\">\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}</font>")
