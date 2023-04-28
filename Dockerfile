FROM alpine:3 as model
ARG HTTP_PROXY
ENV HTTP_PROXY=$HTTP_PROXY \
    HTTPS_PROXY=$HTTP_PROXY

RUN echo "http:$HTTP_PROXY , https:$HTTPS_PROXY"
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories
RUN apk add unzip && apk add wget
RUN mkdir /app && cd /app
RUN wget --proxy=on https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip -o zh_sim_g2.zip && \
    unzip zh_sim_g2.zip && \
    rm -f zh_sim_g2.zip
RUN wget --proxy=on https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip -o craft_mlt_25k.zip && \
    unzip craft_mlt_25k.zip && \
    rm -f craft_mlt_25k.zip


FROM python:3.11-slim-bullseye
WORKDIR /app
ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8 \
    TZ=Asia/Shanghai \
    HOST=0.0.0.0
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir easyocr

COPY sources.list /etc/apt/sources.list
COPY requirements.txt /app/requirements.txt
# 常用包缓存,避免重复下载
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
COPY --from=model /app ~/.EasyOCR/model
CMD ["python","main.py"]





