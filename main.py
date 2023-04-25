import logging
import os
import sys
import time
from os import environ

from flask import Flask
from flask import g
from flask import request
from flask.helpers import make_response
from flask.wrappers import Response
from larksuiteoapi.event import handle_event
from larksuiteoapi.model import OapiHeader
from larksuiteoapi.model import OapiRequest
from larksuiteoapi.service.im.v1 import MessageReceiveEventHandler
from loguru import logger

from feishu_actor import feishu_event_handler
from feishu_client import conf

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

MessageReceiveEventHandler.set_callback(conf, feishu_event_handler)


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


if __name__ == "__main__":
    app.run(debug=False, port=os.environ.get("PORT", 8000), host="0.0.0.0")
