
FROM python:3.11-slim-bullseye
WORKDIR /app
ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US.UTF-8 \
    TZ=Asia/Shanghai \
    HOST=0.0.0.0
COPY sources.list /etc/apt/sources.list
COPY requirements.txt /app/requirements.txt
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
# 常用包缓存,避免重复下载
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
CMD ["python","main.py"]





