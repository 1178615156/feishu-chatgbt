import json
import logging
import os
import sys
import time
import traceback
from os import environ
from queue import Queue
from uuid import uuid4

from cachetools import TTLCache, cached
from flask import Flask
from flask import g
from flask import request
from flask.helpers import make_response
from flask.wrappers import Response
from larksuiteoapi import Config
from larksuiteoapi import Context
from larksuiteoapi import DOMAIN_FEISHU
from larksuiteoapi import LEVEL_DEBUG
from larksuiteoapi.event import handle_event
from larksuiteoapi.model import OapiHeader
from larksuiteoapi.model import OapiRequest
from larksuiteoapi.service.contact.v3 import Service as ContactService
from larksuiteoapi.service.im.v1 import MessageReceiveEvent
from larksuiteoapi.service.im.v1 import MessageReceiveEventHandler
from larksuiteoapi.service.im.v1 import Service as ImService
from larksuiteoapi.service.im.v1 import model
from loguru import logger
from revChatGPT.V3 import Chatbot
from revChatGPT.typings import Error as ChatGPTError

if not os.environ.get("API_URL", "").endswith("/v1/chat/completions"):
    os.environ['API_URL'] = os.environ['API_URL'] + "/v1/chat/completions"
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logger.level(environ.get("LOG_LEVEL", "INFO").upper())
logger.configure(handlers=[dict(
    sink=sys.stdout,
    colorize=True,
    format='<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level> {message}</level>',
)])
app = Flask('bot')
cache = TTLCache(maxsize=996, ttl=10080)
CMD_HELP = '''
/help: 查看命令说明
/reset: 重新开始对话
/title <title>: 修改对话标题，为空则表示清除设置
/prompt <prompt>: 修改 Prompt，为空则表示清除设置，修改 Prompt 会自动重置对话
'''


def read(filename, default=None, mode="r", *args, **kwargs):
    if not os.path.isfile(filename):
        return default
    with open(filename, mode=mode, *args, **kwargs) as fp:
        return fp.read()


def write(filename, content, mode="w", *args, **kwargs):
    with open(filename, mode=mode, *args, **kwargs) as fp:
        fp.write(content)


def read_json(filename, default=None):
    if not os.path.isfile(filename):
        return default
    with open(filename) as fp:
        return json.load(fp)


def write_json(filename, data, **kwargs):
    with open(filename, "w") as fp:
        json.dump(data, fp, **kwargs)


DB_FILE = "db.json"
LOADING_IMG_KEY = environ.get("LOADING_IMG_KEY")

# ALL_MODELS = {
#     "default": "text-davinci-002-render-sha",
#     "legacy": "text-davinci-002-render-paid",
#     "gpt-4": "gpt-4",
# }
# DEFAULT_MODEL = ALL_MODELS["default"]


# 当前访问的是飞书，使用默认存储、默认日志（Error级别），更多可选配置，请看：README.zh.md->如何构建整体配置（Config）
app_settings = Config.new_internal_app_settings_from_env()
conf = Config(DOMAIN_FEISHU, app_settings, log_level=LEVEL_DEBUG)

im_service = ImService(conf)
contact_service = ContactService(conf)

keys = ["email", "password", "session_token", "access_token", "proxy"]
bot_conf = {k: environ.get(k.upper()) for k in keys}
bot_conf = {k: v for k, v in bot_conf.items() if v}
chatbot = Chatbot(
    timeout=int(os.environ.get("TIMEOUT", 60)),
    api_key=os.environ.get("API_KEY", os.environ.get("OPENAI_API_KEY")),
    system_prompt=os.environ.get("SYSTEM_PROMPT", "你是ChatGPT，OpenAI训练的大型语言模型。对话式回应")
)

cmd_queue = Queue()
msg_queue = Queue()


def get_conf(uuid):
    db = read_json(DB_FILE, {})
    return db.get(uuid, {})


def set_conf(uuid, conf):
    db = read_json(DB_FILE, {})
    db.setdefault(uuid, {}).update(conf)
    write_json(DB_FILE, db)


def worker(queue):
    def decorator(func):
        def wrapper():
            while True:
                args = queue.get()
                message_id = args[0]
                try:
                    msg = func(*args)
                    # msg = pool.apply(func,args)
                    if msg is not None:
                        reply_message(message_id, msg)
                except ChatGPTError as e:
                    reply_message(message_id, f"{e.source}({e.code}): {e.message}")
                except Exception as e:
                    traceback.print_exc()
                    reply_message(message_id, f"服务器异常: {type(e)}")

        return wrapper

    return decorator


@worker(cmd_queue)
def handle_cmd(message_id, open_id, chat_id, text):
    uuid = f"{open_id}@{chat_id}"

    if not text.startswith("/"):
        conf = get_conf(uuid)
        conversation_id = conf.get("conversation_id")
        prompt = conf.get("prompt")

        name = get_user_name(open_id)
        title = conf.get("title")
        if title is None:
            title = get_group_name(chat_id)
        title = f"{name} - {title}"

        if conversation_id is None:
            reply_message(message_id, f"开始新对话：{title}")

            if prompt:
                resp_message_id = reply_message(message_id, "", card=True)
                msg_queue.put_nowait((message_id, resp_message_id, title, uuid, prompt))

        resp_message_id = reply_message(message_id, "", card=True)
        msg_queue.put_nowait((message_id, resp_message_id, title, uuid, text))

        return

    cmds = text.split()
    cmd = cmds[0]
    args = cmds[1:]
    if cmd == "/help":
        return CMD_HELP

    conf = get_conf(uuid)
    conversation_id = conf.get("conversation_id")

    if conversation_id is None:
        return "对话不存在"

    if cmd == "/reset":
        reset_chat(uuid)
        return "对话已重新开始"
    elif cmd == "/title":
        if args:
            title = args[0].strip()
        else:
            title = None

        set_conf(uuid, dict(title=title))

        if title is None:
            return "成功清除标题设置"

        if conversation_id is not None:
            name = get_user_name(open_id)
            title = f"{name} - {title}"
        return f"成功修改标题为：{title}"
    elif cmd == "/prompt":
        if args:
            prompt = " ".join(args)
        else:
            prompt = None

        set_conf(uuid, dict(prompt=prompt))

        if prompt is None:
            return "成功清除 Prompt 设置"

        reset_chat(uuid)
        return f"成功修改 Prompt 为：{prompt}\n\n对话已重新开始"
    # elif cmd == "/model":
    #     if not args:
    #         model = conf.get("model", DEFAULT_MODEL)
    #         return f"当前模型为：{model}"
    # model = args[0].strip().lower()
    # if model not in ALL_MODELS:
    #     return "模型不存在"
    #
    # set_conf(uuid, dict(model=ALL_MODELS[model]))
    # reset_chat(uuid)
    # return f"成功修改模型为：{model} ({ALL_MODELS[model]})\n\n对话已重新开始"

    # if cmd == "/rollback":
    #     if args:
    #         n = int(args[0])
    #     else:
    #         n = 1
    #
    #     conf = get_conf(uuid)
    #     parent_ids = conf["parent_ids"]
    #     if not 1 <= n <= len(parent_ids):
    #         return "回滚范围不合法"
    #
    #     conf["parent_ids"] = parent_ids[:-n]
    #     set_conf(uuid, conf)
    #     return f"成功回滚 {n} 条消息"

    return "无效命令"


@worker(msg_queue)
def handle_msg(_, resp_message_id, title, uuid, text):
    conf = get_conf(uuid)
    conversation_id = conf.get("conversation_id") or str(uuid4())
    msg = chatbot.ask(text, convo_id=conversation_id)

    if not msg:
        logger.warning(f"no response for conversation {conversation_id}")
        if conversation_id is None:
            return "获取对话结果失败：对话不存在"
        else:
            return f"获取对话结果失败：\n{chatbot.conversation.get(conversation_id)}"

    update_message(resp_message_id, msg, finish=True)

    conf = dict(conversation_id=conversation_id)
    set_conf(uuid, conf)


def reset_chat(uuid):
    conf = get_conf(uuid)
    conversation_id = conf.get("conversation_id")
    chatbot.reset(conversation_id)
    set_conf(uuid, dict(conversation_id=None, parent_ids=[]))
    if conversation_id is not None:
        del chatbot.conversation[conversation_id]


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


def convert_to_card(msg, finish=False):
    elements = [{"tag": "div", "text": {"tag": "plain_text", "content": msg}}]
    if not finish:
        notes = []
        if LOADING_IMG_KEY:
            notes.append(
                {
                    "tag": "img",
                    "img_key": LOADING_IMG_KEY,
                    "alt": {"tag": "plain_text", "content": ""},
                },
            )
        notes.append({"tag": "plain_text", "content": "typing..."})
        elements.append({"tag": "note", "elements": notes})
    return {"config": {"wide_screen_mode": True}, "elements": elements}


def update_message(message_id, msg, finish=False):
    body = model.MessagePatchReqBody()
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
    body = model.MessageCreateReqBody()
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


def message_receive_handle(ctx: Context, conf: Config, event: MessageReceiveEvent) -> None:
    logger.info(f"request_id = {ctx.get_request_id()}, event={event.event}")

    message = event.event.message
    chat_type = event.event.message.chat_type
    if message.message_type != "text":
        logger.warning("unhandled message type")
        reply_message(message.message_id, "暂时只能处理文本消息")
        return

    open_id = event.event.sender.sender_id.open_id

    text: str = json.loads(message.content).get("text")
    logger.info(f"<{open_id}@{message.chat_id}> {message.message_id}: {text}")
    if chat_type == 'group' and not text.startswith('@_user_1'):
        logger.info(f"ignore :{text}")
        return
    text = text.replace("@_user_1", "").strip()

    cmd_queue.put_nowait((message.message_id, open_id, message.chat_id, text))


MessageReceiveEventHandler.set_callback(conf, message_receive_handle)


@app.route("/webhook/event", methods=["GET", "POST"])
def webhook_event():
    oapi_request = OapiRequest(uri=request.path, body=request.data, header=OapiHeader(request.headers))
    resp = make_response()
    oapi_resp = handle_event(conf, oapi_request)
    resp.headers["Content-Type"] = oapi_resp.content_type
    resp.data = oapi_resp.body
    resp.status_code = oapi_resp.status_code
    return resp


@app.before_request
def app_before_request():
    g.app_start_time = time.time()


@app.after_request
def app_after_request(response: Response):
    use_time = time.time() - g.get('app_start_time', time.time())
    logger.info(
        f"{request.method} {request.url} -- response:{response.status}, use_time:{use_time:.2f}s, size:{response.content_length}B")
    return response


# 设置 "开发者后台" -> "事件订阅" 请求网址 URL：https://domain/webhook/chatgpt
if __name__ == "__main__":
    from threading import Thread

    for i in range(2):
        Thread(target=handle_cmd, args=()).start()

    # Only one message at a time allowed for ChatGPT website
    Thread(target=handle_msg, args=()).start()

    app.run(debug=False, port=os.environ.get("PORT", 8000), host="0.0.0.0")
