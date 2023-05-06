import json
import os
import threading
import time
import traceback
import urllib
import urllib.request
from multiprocessing.pool import ThreadPool
from typing import List, Dict
from urllib.parse import urlparse

import requests
from cachetools import TTLCache
from inscriptis import get_text
from larksuiteoapi import Config
from larksuiteoapi import Context
from larksuiteoapi.service.im.v1 import MessageReceiveEvent, MentionEvent, EventMessage, EventSender
from loguru import logger
from revChatGPT.V3 import Chatbot
from revChatGPT.typings import Error as ChatGPTError

import utils
from feishu_client import reply_message, update_message, docx_service, im_service, FeishuService

actor_cache: Dict[str, "FeishuActor"] = TTLCache(maxsize=1000, ttl=600)
pool = ThreadPool(8)


def mk_chatbot(timeout=None,
               api_key=None,
               system_prompt=None):
    return Chatbot(
        timeout=timeout if timeout else int(os.environ.get("TIMEOUT", 60)),
        api_key=api_key if api_key else os.environ.get("API_KEY", os.environ.get("OPENAI_API_KEY")),
        system_prompt=system_prompt if system_prompt else os.environ.get("SYSTEM_PROMPT",
                                                                         "引导:\n你是ChatGPT，一个由 OpenAI 训练的大语言模型。")
    )


def feishu_event_handler(ctx: Context,
                         conf: Config,
                         event: MessageReceiveEvent):
    '''
    接收飞书事件,匹配对应的actor
    :param ctx:
    :param conf:
    :param event:
    :return:
    '''
    logger.info(f"{event.event}")

    message: EventMessage = event.event.message
    sender: EventSender = event.event.sender
    open_id = sender.sender_id.open_id
    chat_id = message.chat_id
    chat_type = message.chat_type
    uuid = f"{open_id}@{chat_id}"
    mentions: List[MentionEvent] = message.mentions
    mention_bot = [mention for mention in (mentions if mentions else []) if mention.name == os.environ.get("BOT_NAME")]
    # 判断有无@机器人
    if chat_type == 'group' and not mention_bot:
        logger.info(f"ignore :{message.content}")
        return

    if uuid not in actor_cache:
        actor_cache[uuid] = FeishuActor(uuid=uuid)
        # title = get_user_name(open_id)
        # if title is None:
        #     title = get_group_name(chat_id)
        # logger.info(f"{message.message_id} 开始新对话：{title}")
        reply_message(message.message_id, f"开始新对话：{uuid}")

    pool.apply_async(lambda: actor_cache[uuid].receive(sender=sender, message=message))


class FeishuActor:
    def __init__(self, uuid: str):
        self.uuid = str(uuid)
        self.lock = threading.Lock()
        self.chatbot = mk_chatbot()
        self.msg_ids = TTLCache(maxsize=500, ttl=600)

    def receive(self, sender: EventSender, message: EventMessage):
        message_id = message.message_id
        self.sender = sender
        self.message = message
        try:
            self.lock.locked()
            ack_text = ''
            if message_id in self.msg_ids:
                logger.info(f"duplicate:{message_id}")
                return
            else:
                self.msg_ids[message_id] = time.time()

            # 文本数据
            if message.message_type == 'text':
                ack_text: str = json.loads(message.content).get("text")
                mentions: List[MentionEvent] = message.mentions
                mentions = mentions if mentions else []
                for mention in mentions:
                    ack_text = ack_text.replace(mention.key, mention.name if mention.name else '').strip()

            # 文件
            if message.message_type == 'file':
                msg_file = json.loads(message.content)
                file_key = msg_file.get('file_key')
                ack_text = (
                    im_service.message_resources.get()
                        .set_type("file")
                        .set_message_id(message_id)
                        .set_file_key(file_key)
                        .do()
                        .data.decode('UTF-8')
                )
                if len(ack_text) > 2048:
                    reply_message(message_id=message.message_id,
                                  msg="文件太长,只支持2000字符")
                    return
                else:
                    reply_message(message_id, f"read file:\n{ack_text}")

            if message.message_type == 'image':
                msg_file = json.loads(message.content)
                file_key = msg_file.get('image_key')
                image = (
                    im_service.message_resources.get()
                        .set_type("image")
                        .set_message_id(message_id)
                        .set_file_key(file_key)
                        .do()
                        .data
                )
                result = FeishuService().orc_service(image)
                ack_text = "\n".join(result)
                reply_message(message_id, f"orc:\n{ack_text}")
            if ack_text:
                self.match(ack_text)
            else:
                reply_message(message_id, f"未知消息:{message.content}")

        except ChatGPTError as e:
            reply_message(message_id, f"{e.source}({e.code}): {e.message}")
        except Exception as e:
            traceback.print_exc()
            reply_message(message_id, f"服务器异常: {type(e)}")
        finally:
            self.lock.release()
            self.sender = None
            self.message = None

    def match(self, text):
        message = self.message
        cmd_result = self.match_cmd(text)
        if cmd_result:
            reply_message(message.message_id, cmd_result)
            return

        resp_message_id = reply_message(message.message_id, "", card=True)
        result = self.match_text(text)
        update_message(resp_message_id, result, finish=True)

    def match_cmd(self, text: str):
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

    def match_text(self, text: str):
        urls = utils.find_urls(text)
        for url in urls:
            if 'feishu' in url:
                text = text.replace(url, self.request_feishu_doc(url))
            if text.startswith("/url"):
                text = text.replace(url, utils.get_url_text(url))
        if text.startswith("/url"):
            text = text[len("/url"):].strip()
        logger.info(f"ask:{text}")
        return self.chatbot.ask(text)

    def request_feishu_doc(self, raw_url):
        try:
            url = urlparse(raw_url)
            if 'feishu' in url.netloc:
                doc_id = url.path.split("/")[-1]
                doc_type = url.path.split("/")[-2]
                logger.info(f'url:{url} , doc_type:{doc_type}, doc_id:{doc_id}')
                return docx_service.documents.raw_content().set_document_id(doc_id).do().data.content
        except Exception as e:
            traceback.print_exc()
            # logger.exception(e)
        return raw_url

