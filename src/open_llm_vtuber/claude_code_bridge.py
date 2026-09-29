"""Turn Claude Code hook events into proactive-speak prompts for the character."""

import asyncio
import os
from typing import Optional

from loguru import logger

from .websocket_handler import WebSocketHandler

MAX_SUMMARY_CHARS = 300

_PREFIX = "（系統通知，不是使用者說的話）"
_SUFFIX = "請用一到兩句簡短、口語的台灣繁體中文提醒使用者，不要念出檔名路徑或程式碼。"


def build_prompt(event: dict) -> Optional[str]:
    """Build a prompt from a Claude Code hook payload, or None to stay silent."""
    event_name = event.get("hook_event_name", "")
    project = os.path.basename(event.get("cwd", "").rstrip("/\\")) or "目前的專案"

    if event_name == "Stop":
        summary = (event.get("last_assistant_message") or "").strip()
        detail = (
            f"Claude 最後的回覆摘要：{summary[:MAX_SUMMARY_CHARS]}。" if summary else ""
        )
        return (
            f"{_PREFIX}Claude Code 在「{project}」剛完成了一項任務。{detail}"
            f"{_SUFFIX}可以簡單提一下做了什麼。"
        )

    if event_name == "Notification":
        message = event.get("message", "")
        if event.get("notification_type") == "idle_prompt":
            situation = "正在等使用者回覆"
        else:
            situation = "正在等使用者授權或確認"
        return f"{_PREFIX}Claude Code 在「{project}」{situation}：{message}。{_SUFFIX}"

    logger.debug(f"Ignoring Claude Code event: {event_name}")
    return None


async def _speak_when_idle(ws_handler: WebSocketHandler, client_uid: str, prompt: str):
    """Wait for the client's current conversation to finish, then speak."""
    task = ws_handler.current_conversation_tasks.get(client_uid)
    if task and not task.done():
        try:
            await asyncio.shield(task)
        except BaseException:
            pass

    websocket = ws_handler.client_connections.get(client_uid)
    if websocket is None:
        return
    await ws_handler._handle_conversation_trigger(
        websocket, client_uid, {"type": "ai-speak-signal", "prompt": prompt}
    )


def dispatch_event(ws_handler: WebSocketHandler, event: dict) -> int:
    """Schedule the character to announce the event on every connected client.

    Returns the number of clients notified.
    """
    prompt = build_prompt(event)
    if prompt is None:
        return 0

    client_uids = list(ws_handler.client_connections.keys())
    for client_uid in client_uids:
        asyncio.create_task(_speak_when_idle(ws_handler, client_uid, prompt))
    logger.info(
        f"Claude Code event '{event.get('hook_event_name')}' sent to {len(client_uids)} client(s)"
    )
    return len(client_uids)
