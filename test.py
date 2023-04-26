from utils import find_urls


def test_find_urls():
    urls = find_urls("hello https://1.1.1.1/996 world: zz https://baidu.com/996")
    print(urls)
    assert urls == ['https://1.1.1.1/996', 'https://baidu.com/996']


import requests

print(requests.get('http://www.scio.gov.cn/37234/Document/1738206/1738206.htm',

                   headers={
                       'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                       'Accept-Encoding': 'gzip, deflate',
                       'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                       'Cache-Control': 'no-cache',
                       'Connection': 'keep-alive',
                       'Cookie':
                       'jsluid_h=b29dc15f44783cb6e3bc5a12d2787154; Hm_lvt_7cd4be5b075ad771f065c6fe4059883a=1681177476; Hm_lpvt_7cd4be5b075ad771f065c6fe4059883a=1682495300',
                   'Pragma': 'no-cache',
'Referer': 'http://www.scio.gov.cn/index.htm',
'Upgrade-Insecure-Requests': '1',
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'
}).text)
