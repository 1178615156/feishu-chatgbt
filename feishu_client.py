import json

from cachetools import TTLCache, cached
from larksuiteoapi import DOMAIN_FEISHU, Config, LEVEL_DEBUG
from larksuiteoapi.service.contact.v3 import Service as ContactService
from larksuiteoapi.service.docx.v1 import Service as DocxService
from larksuiteoapi.service.im.v1 import Service as ImService
from larksuiteoapi.service.im.v1 import model as im_model
from loguru import logger

app_settings = Config.new_internal_app_settings_from_env()
conf = Config(DOMAIN_FEISHU, app_settings, log_level=LEVEL_DEBUG)
im_service = ImService(conf)
contact_service = ContactService(conf)
cache = TTLCache(maxsize=996, ttl=10080)
docx_service = DocxService(conf)


def convert_to_card(msg, finish=False):
    elements = [{"tag": "div", "text": {"tag": "plain_text", "content": msg}}]
    if not finish:
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": "typing..."}]})
    return {"config": {"wide_screen_mode": True}, "elements": elements}


def update_message(message_id, msg, finish=False):
    body = im_model.MessagePatchReqBody()
    body.content = json.dumps(convert_to_card(msg, finish))

    req_call = im_service.messages.patch(body)
    req_call.set_message_id(message_id)

    resp = req_call.do()
    logger.info(f"request_id:{resp.get_request_id()}, code:{resp.get_http_status_code()}, msg:{msg}")
    if resp.code == 0:
        logger.info(f"update {message_id} success")
    else:
        logger.error(f"{resp.msg}: {resp.error}")


def reply_message(message_id, msg, card=False, finish=False):
    body = im_model.MessageCreateReqBody()
    if card:
        body.content = json.dumps(convert_to_card(msg, finish))
        body.msg_type = "interactive"
    else:
        body.content = json.dumps(dict(text=msg))
        body.msg_type = "text"

    req_call = im_service.messages.reply(body)
    req_call.set_message_id(message_id)

    resp = req_call.do()
    logger.info(f"request_id:{resp.get_request_id()}, code:{resp.get_http_status_code()}, msg:{msg}")
    if resp.code == 0:
        logger.info(f"reply for {message_id}: {resp.data.message_id} msg:{msg}")
        return resp.data.message_id
    else:
        logger.error(f"{resp.msg}: {resp.error} ")


@cached(cache)
def get_user_name(open_id):
    req_call = contact_service.users.get()
    req_call.set_user_id(open_id)
    resp = req_call.do()
    logger.debug(f"request id = {resp.get_request_id()}")
    logger.debug(f"http status code = {resp.get_http_status_code()}")
    if resp.code != 0:
        logger.error(f"{resp.msg}: {resp.error}")
        return "Unknown"
    logger.info(f"user: {resp.data.user.name} ({resp.data.user.en_name})")
    return resp.data.user.name


@cached(cache)
def get_group_name(chat_id):
    req_call = im_service.chats.get()
    req_call.set_chat_id(chat_id)
    resp = req_call.do()
    logger.debug(f"request id = {resp.get_request_id()}")
    logger.debug(f"http status code = {resp.get_http_status_code()}")
    if resp.code != 0:
        logger.error(f"{resp.msg}: {resp.error}")
        return f"<{chat_id}>"
    if resp.data.chat_mode != "group":
        logger.info(f"group mode: {resp.data.chat_mode}")
        return f"[{resp.data.chat_mode}]"
    logger.info(f"group: {resp.data.name}")
    return resp.data.name
