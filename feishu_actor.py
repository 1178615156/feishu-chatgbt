import json
import os
import threading
from typing import List, Dict

from cachetools import TTLCache
from larksuiteoapi import Config
from larksuiteoapi import Context
from larksuiteoapi.service.im.v1 import MessageReceiveEvent, EventMessage, EventSender, MentionEvent
from loguru import logger
from revChatGPT.V3 import Chatbot

actor_cache: Dict[str, "FeishuActor"] = TTLCache(maxsize=1000, ttl=600)


def mk_chatbot(timeout=None,
               api_key=None,
               system_prompt=None):
    return Chatbot(
        timeout=timeout if timeout else int(os.environ.get("TIMEOUT", 60)),
        api_key=api_key if api_key else os.environ.get("API_KEY", os.environ.get("OPENAI_API_KEY")),
        system_prompt=system_prompt if system_prompt else os.environ.get("SYSTEM_PROMPT",
                                                                         "引导:\n你是ChatGPT，一个由 OpenAI 训练的大语言模型。")
    )


def feishu_event_handler(ctx: Context, conf: Config, event: MessageReceiveEvent):
    logger.info(f"{event.event}")

    message: EventMessage = event.event.message
    sender: EventSender = event.event.sender
    open_id = sender.sender_id.open_id
    chat_id = message.chat_id
    chat_type = message.chat_type
    uuid = f"{open_id}@{chat_id}"
    text: str = json.loads(message.content).get("text")
    mentions: List[MentionEvent] = message.mentions
    mentions = mentions if mentions else []
    mention_bot = [mention for mention in mentions if mention.name == os.environ.get("BOT_NAME")]

    if chat_type == 'group' and not mention_bot:
        logger.info(f"ignore :{text}")
        return
    if message.message_type != "text":
        logger.warning("unhandled message type")
        reply_message(message.message_id, "暂时只能处理文本消息")
        return
    for mention in mentions:
        text = text.replace(mention.key, mention.name if mention.name else '').strip()

    if uuid not in actor_cache:
        actor_cache[uuid] = FeishuActor(uuid=uuid)

    actor_cache[uuid].receive_message(text=text, sender=sender, message=message)


class FeishuActor:
    def __init__(self, uuid):
        self.uuid = str(uuid)
        self.lock = threading.Lock()
        self.chatbot = Chatbot(
            timeout=int(os.environ.get("TIMEOUT", 60)),
            api_key=os.environ.get("API_KEY", os.environ.get("OPENAI_API_KEY")),
            system_prompt=os.environ.get("SYSTEM_PROMPT", "引导:\n你是ChatGPT，一个由 OpenAI 训练的大语言模型。")
        )

    def receive_message(self, text: str, *, sender: EventSender, message: EventMessage):
        with self.lock:
            self.sender = sender
            self.message = message
            if text.startswith("/"):
                result = self.when_cmd(text)
        self.sender = None
        self.message = None

    def when_cmd(self, text: str):
        cmd, remain = self.parser_cmd(text)
        if cmd == '/reset':
            pass
        if cmd == '/prompt':
            self.chatbot = mk_chatbot(system_prompt=remain)

    def when_text(self, text: str):
        pass

    def parser_cmd(self, text: str):
        for i in range(len(text)):
            if text[i] == ' ':
                return text[0:i], text[i + 1, :]

        return None, None
