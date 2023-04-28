import dev_env

print(dev_env)

from utils import find_urls
from feishu_client import im_service, FeishuService


def test_find_urls():
    urls = find_urls("hello https://1.1.1.1/996 world: zz https://baidu.com/996")
    print(urls)
    assert urls == ['https://1.1.1.1/996', 'https://baidu.com/996']


def test_file():
    f = (im_service.message_resources.get()
         .set_type("file")
         .set_message_id('om_52a82a88f537157c86e67a1909e4507e')
         .set_file_key('file_v2_0304d2a0-cebb-4a82-a624-7c474d61d23g')
         .do())

    print(f)
    print(f.data.decode('UTF-8'))
    print(len(f.data.decode('UTF-8')))


def test_img():
    f = (im_service.message_resources.get()
         .set_type("image")
         .set_message_id('om_25acc0195df7f9db2f679623dfe17801')
         .set_file_key('img_v2_3adfd087-2f46-4da8-9642-8f7f71ece67g')
         .do())

    print(f)
    result = FeishuService().orc_service(f.data)
    print(result)


test_img()
