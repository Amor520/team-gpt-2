import logging
from urllib.parse import urlparse
from datetime import datetime

import httpx
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.settings import settings_service
from app.services.redemption import RedemptionService
from app.services.team import team_service
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class NotificationService:
    """通知服务类"""

    def __init__(self):
        self.redemption_service = RedemptionService()

    async def check_and_notify_low_stock(self) -> bool:
        """
        检查库存（车位）并发送通知
        使用独立的数据库会话以支持异步后台任务
        """
        async with AsyncSessionLocal() as db_session:
            try:
                # 1. 获取配置
                webhook_url = await settings_service.get_setting(db_session, "webhook_url")
                if not webhook_url:
                    return False

                threshold_str = await settings_service.get_setting(db_session, "low_stock_threshold", "10")
                api_key = await settings_service.get_setting(db_session, "api_key")

                try:
                    threshold = int(threshold_str)
                except (ValueError, TypeError):
                    threshold = 10

                # 2. 检查可用车位 (作为预警指标)
                available_seats = await team_service.get_total_available_seats(db_session)
                
                logger.info(f"库存检查 - 当前总可用车位: {available_seats}, 触发阈值: {threshold}")

                # 仅根据可用车位触发补货
                if available_seats <= threshold:
                    logger.info(f"检测到车位不足，触发补货预警! Webhook URL: {webhook_url}")
                    return await self.send_webhook_notification(webhook_url, available_seats, threshold, api_key)
                
                return False

            except Exception as e:
                logger.error(f"检查库存并通知过程发生错误: {e}")
                return False

    @staticmethod
    def _is_wecom_webhook(url: str) -> bool:
        """判断是否为企业微信机器人 Webhook。"""
        try:
            parsed = urlparse(url)
        except Exception:
            return False

        host = (parsed.hostname or "").lower()
        return host == "qyapi.weixin.qq.com" and parsed.path.startswith("/cgi-bin/webhook/send")

    @staticmethod
    def _build_low_stock_message(available_seats: int, threshold: int, is_test: bool = False) -> str:
        if is_test:
            return f"库存预警测试：系统当前总可用车位为 {available_seats}，当前预警阈值为 {threshold}。"
        return f"库存不足预警：系统总可用车位仅剩 {available_seats}，已低于预警阈值 {threshold}，请及时补货导入新账号。"

    @staticmethod
    def _build_wecom_markdown_content(available_seats: int, threshold: int, is_test: bool = False) -> str:
        title = "库存测试" if is_test else "库存预警"
        status_line = (
            f"### GPT Team <font color=\"comment\">{title}</font>"
            if is_test
            else f"### GPT Team <font color=\"warning\">{title}</font>"
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = NotificationService._build_low_stock_message(
            available_seats,
            threshold,
            is_test=is_test,
        )
        return (
            f"{status_line}\n"
            f"> 当前总可用车位：<font color=\"warning\">{available_seats}</font>\n"
            f"> 预警阈值：<font color=\"comment\">{threshold}</font>\n"
            f"> 发送时间：<font color=\"comment\">{timestamp}</font>\n"
            f"> 说明：{message}"
        )

    def _build_notification_request(
        self,
        url: str,
        available_seats: int,
        threshold: int,
        api_key: Optional[str] = None,
        is_test: bool = False,
    ) -> tuple[dict, dict]:
        """根据目标地址构造通知请求内容。"""
        message = self._build_low_stock_message(available_seats, threshold, is_test=is_test)

        if self._is_wecom_webhook(url):
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": self._build_wecom_markdown_content(
                        available_seats,
                        threshold,
                        is_test=is_test,
                    )
                }
            }
            return payload, {}

        payload = {
            "event": "low_stock_test" if is_test else "low_stock",
            "current_seats": available_seats,
            "threshold": threshold,
            "message": message,
        }
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        return payload, headers

    async def send_webhook_notification(
        self,
        url: str,
        available_seats: int,
        threshold: int,
        api_key: Optional[str] = None,
        is_test: bool = False,
    ) -> bool:
        """
        发送 Webhook 通知
        """
        try:
            payload, headers = self._build_notification_request(
                url,
                available_seats,
                threshold,
                api_key,
                is_test=is_test,
            )
            webhook_type = "wecom" if self._is_wecom_webhook(url) else "generic"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.info(
                    "Webhook 通知发送成功: type=%s mode=%s url=%s",
                    webhook_type,
                    "test" if is_test else "live",
                    url,
                )
                return True
        except Exception as e:
            logger.error(f"发送 Webhook 通知失败: {e}")
            return False

# 创建全局实例
notification_service = NotificationService()
