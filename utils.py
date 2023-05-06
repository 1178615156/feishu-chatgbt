import string

import requests
from inscriptis import get_text


def find_urls(text: str):
    '''
    查找文本中的url
    :param text:
    :param url_index_start:
    :return:
    '''
    http = 'http://'
    http_len = len(http)
    https = "https://"
    https_len = len(https)
    i = 0
    results = []
    text_len = len(text)
    while i < text_len:
        if text[i:i + https_len] == https or text[i:i + http_len] == http:
            url_index_start = i
            while i < text_len and text[i] in (string.digits + string.ascii_letters + string.punctuation):
                i += 1
            results.append(text[url_index_start:i])
            continue
        i += 1
    return results


def get_url_text(raw_url):
    content = requests.get(url=raw_url, headers={
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'cache-control': 'no-cache',
        'pragma':'no-cache',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'
    }).text
    # content = urllib.request.urlopen(raw_url).read().decode('utf-8')
    return get_text(content)
