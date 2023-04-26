from utils import find_urls


def test_find_urls():
    urls = find_urls("hello https://1.1.1.1/996 world: zz https://baidu.com/996")
    print(urls)
    assert urls == ['https://1.1.1.1/996', 'https://baidu.com/996']
