import string


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
