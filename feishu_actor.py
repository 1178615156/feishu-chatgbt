import dataclasses
import json
import os
import string
import threading
import time
import traceback
import urllib
import urllib.request
from multiprocessing.pool import ThreadPool
from typing import List, Dict
from urllib.parse import urlparse

from cachetools import TTLCache
from larksuiteoapi import Config
from larksuiteoapi import Context
from larksuiteoapi.service.im.v1 import MessageReceiveEvent, MentionEvent, EventMessage, EventSender
from loguru import logger
from revChatGPT.V3 import Chatbot
from revChatGPT.typings import Error as ChatGPTError

from feishu_client import reply_message, update_message, get_user_name, get_group_name, docx_service

import utils

actor_cache: Dict[str, "FeishuActor"] = TTLCache(maxsize=1000, ttl=600)
pool = ThreadPool()
from inscriptis import get_text


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
        title = get_user_name(open_id)
        if title is None:
            title = get_group_name(chat_id)
        reply_message(message.message_id, f"开始新对话：{title}")

    pool.apply_async(lambda: actor_cache[uuid].receive_message(text=text, sender=sender, message=message))


class FeishuActor:
    def __init__(self, uuid: str):
        self.uuid = str(uuid)
        self.lock = threading.Lock()
        self.chatbot = mk_chatbot()
        self.msg_ids = TTLCache(maxsize=500, ttl=600)
        self.continue_state = object()

    def receive_message(self, text: str, *, sender: EventSender, message: EventMessage):
        message_id = message.message_id
        self.sender = sender
        self.message = message
        try:
            self.lock.locked()
            if message_id in self.msg_ids:
                logger.info(f"duplicate:{message_id}")
                return
            self.msg_ids[message_id] = time.time()
            cmd_result = self.when_cmd(text)
            if cmd_result:
                reply_message(message.message_id, cmd_result)

            resp_message_id = reply_message(message.message_id, "", card=True)
            result = self.when_text(text)
            update_message(resp_message_id, result, finish=True)
        except ChatGPTError as e:
            reply_message(message_id, f"{e.source}({e.code}): {e.message}")
        except Exception as e:
            traceback.print_exc()
            reply_message(message_id, f"服务器异常: {type(e)}")
        finally:
            self.lock.release()
            self.sender = None
            self.message = None

    def when_cmd(self, text: str):
        if text.startswith('/reset'):
            self.chatbot = mk_chatbot()
            return '对话已重新开始'
        if text.startswith('/prompt'):
            prompt = text[len('/prompt'):].strip()
            if prompt == 'debug':
                prompt = '假装你是一个优秀的程序员,我会提供程序运行的log,你需要找出错误原因以及对应的解决方法.'
            self.chatbot = mk_chatbot(system_prompt=prompt)
            return f'设置Prompt: {prompt}'
        if text.startswith('/history'):
            return str(self.chatbot.conversation['default'])

    def when_text(self, text: str):
        if text.startswith("/url"):
            urls = utils.find_urls(text)
            urls_content = self.request_urls(urls)
            for url, content in urls_content.items():
                text = text.replace(url, content)

        return self.chatbot.ask(text)

    def request_urls(self, urls: List[str]):
        '''
        请求url获取纯文本
        :param urls:
        :return:
        '''
        result = {}
        for raw_url in urls:
            url = urlparse(raw_url)
            if 'feishu' in url.netloc:
                doc_id = url.path.split("/")[-1]
                doc_type = url.path.split("/")[-2]
                logger.info(f'url:{url} , doc_type:{doc_type}, doc_id:{doc_id}')
                content = docx_service.documents.raw_content().set_document_id(doc_id).do().data.content
            else:
                content = urllib.request.urlopen(raw_url).read().decode('utf-8')
                content = get_text(content)
            result[raw_url] = content

        return result
