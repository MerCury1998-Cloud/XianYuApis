import base64
import json
import asyncio
import os
import threading
import time

from loguru import logger
import websockets
from openai import AsyncOpenAI
from goofish_apis import XianyuApis, qrcode_login

from utils.goofish_utils import generate_mid, generate_uuid, trans_cookies, generate_device_id, decrypt, \
    get_session_cookies_str
from message import Message, make_text, make_image

# ===== LLM 配置 =====
LLM_API_KEY = 'sk-32ff2a5953fbb4d96a26bdc778bfd263'
LLM_BASE_URL = 'https://v2.aicodee.com/v1'
LLM_MODEL = 'MiniMax-M2.7-highspeed'
LLM_SYSTEM_PROMPT = '''【Switch 游戏机闲鱼自动客服 - 价格信息】

你是闲鱼客服，我们这里主要经营Switch游戏机。回答客户问题时，请参考以下价格信息：

■ Switch 普通版 日/港版
  - 正版：拿货价1100元，建议零售价1170元
  - 128G 预装10款游戏：拿货价1250元，建议零售价1320元
  - 256G 预装25款游戏：拿货价1350元，建议零售价1420元
  - 400G 预装40款游戏：拿货价1450元，建议零售价1520元
  - 512G 预装50款游戏：拿货价1600元，建议零售价1670元
  - 1T 预装100款游戏：拿货价2200元，建议零售价2270元

■ Switch 续航版 国行版
  - 正版：拿货价1200元，建议零售价1270元
  - 128G 预装10款游戏：拿货价1350元，建议零售价1420元
  - 256G 预装25款游戏：拿货价1450元，建议零售价1520元
  - 400G 预装40款游戏：拿货价1550元，建议零售价1620元
  - 512G 预装50款游戏：拿货价1700元，建议零售价1770元
  - 1T 预装100款游戏：拿货价2300元，建议零售价2370元

■ Switch 续航版 日/港版
  - 正版：拿货价1300元，建议零售价1370元
  - 128G 预装10款游戏：拿货价1450元，建议零售价1520元
  - 256G 预装25款游戏：拿货价1550元，建议零售价1620元
  - 400G 预装40款游戏：拿货价1650元，建议零售价1720元
  - 512G 预装50款游戏：拿货价1800元，建议零售价1870元
  - 1T 预装100款游戏：拿货价2400元，建议零售价2470元

■ Switch OLED 版 日/港版
  - 正版：拿货价1600元，建议零售价1670元
  - 128G 预装10款游戏：拿货价1800元，建议零售价1870元
  - 256G 预装25款游戏：拿货价1900元，建议零售价1970元
  - 400G 预装40款游戏：拿货价2000元，建议零售价2070元
  - 512G 预装50款游戏：拿货价2250元，建议零售价2320元
  - 1T 预装100款游戏：拿货价2750元，建议零售价2820元

■ Switch OLED 限定版 日/港版
  - 正版：拿货价1700元，建议零售价1770元
  - 128G 预装10款游戏：拿货价1900元，建议零售价1970元
  - 256G 预装25款游戏：拿货价2000元，建议零售价2070元
  - 400G 预装40款游戏：拿货价2100元，建议零售价2170元
  - 512G 预装50款游戏：拿货价2250元，建议零售价2320元
  - 1T 预装100款游戏：拿货价2850元，建议零售价2920元

■ 配件价格
  - 99新：150元
  - 翻全新：250元
  - 全新日版原装健身环：200元
  - 二手日版原装pro手柄：150元
  - Switch原装joycon手柄一对 95新：240元
  - Switch原装joycon手柄一对 99新：290元
  - joycon腕带：20元
  - joycon握把：25元
  - 帮破服务（所有型号统一）：100元

【注意事项】
- 所有机器均为双系统（正版+破解）
- 顺丰包邮，河南周口发货
- 闲鱼禁止词：破解、动森、动物之森、生化危机、微信等，回复时避免使用这些词汇

回答要求：
- 用朋友聊天的语气，随意简短，不要过度热情假客气
- 回答要简短直接，不要啰嗦
- 如果客户问"在吗"这类招呼，直接回答"在，怎么了"或类似简短回应
- 如果客户询价，根据上面的价格表给出建议零售价
- 如果客户有购买意向（说下单、改价等），直接说好的并告知会通知老板来处理
- 如果客户问及配置差异，如实介绍
- 不要使用表情符号，不要用"亲"等淘宝味称呼'''

# ===== 飞书通知配置 =====
FEISHU_WEBHOOK_URL = 'https://open.feishu.cn/open-apis/bot/v2/hook/52fa6601-ac5b-4a04-9a34-0ca1033e3237'


def send_feishu_notification(title: str, content: str):
    """发送飞书机器人通知"""
    try:
        import requests
        msg = {
            "msg_type": "text",
            "content": {
                "text": f"{title}\n{content}"
            }
        }
        resp = requests.post(FEISHU_WEBHOOK_URL, json=msg, timeout=10)
        if resp.status_code == 200:
            logger.info("飞书通知发送成功")
        else:
            logger.warning(f"飞书通知返回异常: {resp.status_code}")
    except Exception as e:
        logger.error(f"飞书通知发送失败: {e}")


# ===== 下单意向检测 =====
ORDER_KEYWORDS = ['下单', '改价', '拍下', '我买了', '付款', '怎么买', '链接发我', '拍', '已拍', '去拍',
                  '优惠', '包邮吗', '多少钱', '价格', '能便宜', '少点']


def check_order_intent(message: str) -> bool:
    """检测用户是否有下单/购买意向"""
    msg_lower = message.lower()
    for kw in ORDER_KEYWORDS:
        if kw in msg_lower:
            return True
    return False


llm_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


class XianyuLive:
    def __init__(self, cookies_str):
        self.base_url = 'wss://wss-goofish.dingtalk.com/'
        self.cookies_str = cookies_str
        self.cookies = trans_cookies(cookies_str)
        self.myid = self.cookies['unb']
        self.device_id = generate_device_id(self.myid)
        self.xianyu = XianyuApis(self.cookies, self.device_id)
        self.ws = None

    async def list_all_conversations(self, cid):
        headers = {
            "Cookie": get_session_cookies_str(self.xianyu.session),
            "Host": "wss-goofish.dingtalk.com",
            "Connection": "Upgrade",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://www.goofish.com",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        async with websockets.connect(self.base_url, additional_headers=headers) as websocket:
            asyncio.create_task(self.init(websocket))
            send_mid = generate_mid()
            msg = {
                "lwp": "/r/MessageManager/listUserMessages",
                "headers": {
                    "mid": send_mid
                },
                "body": [
                    f"{cid}@goofish",
                    False,
                    9007199254740991,
                    20,
                    False
                ]
            }
            user_message_models = []
            async for message in websocket:
                try:
                    message = json.loads(message)
                    ack = {
                        "code": 200,
                        "headers": {
                            "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                            "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                        }
                    }
                    if 'app-key' in message["headers"]:
                        ack["headers"]["app-key"] = message["headers"]["app-key"]
                    if 'ua' in message["headers"]:
                        ack["headers"]["ua"] = message["headers"]["ua"]
                    if 'dt' in message["headers"]:
                        ack["headers"]["dt"] = message["headers"]["dt"]
                    await websocket.send(json.dumps(ack))
                except Exception as e:
                    pass
                try:
                    if 'lwp' in message and message['lwp'] == "/s/vulcan":
                        await websocket.send(json.dumps(msg))
                    recv_mid = message["headers"]["mid"] if "mid" in message["headers"] else ''
                    if recv_mid == send_mid:
                        logger.info(f"user history message: {message}")
                        has_more = message["body"]["hasMore"] == 1
                        next_cursor = message["body"]["nextCursor"]
                        for user_message in message["body"]["userMessageModels"]:
                            send_user_name = user_message["message"]["extension"]["reminderTitle"]
                            send_user_id = user_message["message"]["extension"]["senderUserId"]
                            send_message_base64 = user_message["message"]["content"]["custom"]["data"]
                            send_message_json = json.loads(base64.b64decode(send_message_base64).decode('utf-8'))
                            user_message_models.insert(0, {
                                "send_user_id": send_user_id,
                                "send_user_name": send_user_name,
                                "message": send_message_json
                            })
                        if has_more:
                            logger.info(f"has more history messages, next cursor: {next_cursor}")
                            send_mid = generate_mid()
                            msg["headers"]["mid"] = send_mid
                            msg["body"][2] = next_cursor
                            await websocket.send(json.dumps(msg))
                        else:
                            return user_message_models
                except Exception as e:
                    return user_message_models

    async def create_chat(self, ws, toid, item_id='891198795482'):
        msg = {
            "lwp": "/r/SingleChatConversation/create",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "pairFirst": f"{toid}@goofish",
                    "pairSecond": f"{self.myid}@goofish",
                    "bizType": "1",
                    "extension": {
                        "itemId": item_id
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    }
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def send_msg(self, ws, cid, toid, message: Message):
        msg_type = message["type"]
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": None,
                            "data": None
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {
                        "extJson": "{}"
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",
                        f"{self.myid}@goofish"
                    ]
                }
            ]
        }
        if msg_type == "text":
            payload = {
                "contentType": 1,
                "text": {
                    "text": message["text"]
                }
            }
            text_base64 = str(base64.b64encode(json.dumps(payload).encode('utf-8')), 'utf-8')
            msg["body"][0]["content"]["custom"]["type"] = 1
            msg["body"][0]["content"]["custom"]["data"] = text_base64
        elif msg_type == "image":
            payload = {
                "contentType": 2,
                "image": {
                    "pics": [
                        {
                            "type": 0,
                            "url": message["image_url"],
                            "width": message["width"],
                            "height": message["height"]
                        }
                    ]
                }
            }
            image_base64 = str(base64.b64encode(json.dumps(payload).encode('utf-8')), 'utf-8')
            msg["body"][0]["content"]["custom"]["type"] = 2
            msg["body"][0]["content"]["custom"]["data"] = image_base64
        elif msg_type == "audio":
            # TODO: handle audio message
            logger.error(f"不支持的消息类型: {msg_type}")
            return
        else:
            logger.error(f"不支持的消息类型: {msg_type}")
            return
        await ws.send(json.dumps(msg))

    async def init(self, ws):
        data = self.xianyu.get_token()
        token = data['data']['accessToken'] if 'data' in data and 'accessToken' in data['data'] else ''
        if not token:
            logger.error('获取token失败')
            exit(0)
        msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        current_time = int(time.time() * 1000)
        msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time
                }
            ]
        }
        await ws.send(json.dumps(msg))
        logger.info('init')

    async def heart_beat(self, ws):
        while True:
            msg = {
                "lwp": "/!",
                "headers": {
                    "mid": generate_mid()
                 }
            }
            await ws.send(json.dumps(msg))
            await asyncio.sleep(15)

    def user_alive(self):
        while True:
            time.sleep(600)
            self.xianyu.refresh_token()

    async def main(self):
        try:
            headers = {
                "Cookie": get_session_cookies_str(self.xianyu.session),
                "Host": "wss-goofish.dingtalk.com",
                "Connection": "Upgrade",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                "Origin": "https://www.goofish.com",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            threading.Thread(target=self.user_alive).start()
            async with websockets.connect(self.base_url, additional_headers=headers) as websocket:
                asyncio.create_task(self.init(websocket))
                asyncio.create_task(self.heart_beat(websocket))
                async for message in websocket:
                    # logger.info(f"message: {message}")
                    message = json.loads(message)
                    ack = {
                        "code": 200,
                        "headers": {
                            "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                            "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                        }
                    }
                    if 'app-key' in message["headers"]:
                        ack["headers"]["app-key"] = message["headers"]["app-key"]
                    if 'ua' in message["headers"]:
                        ack["headers"]["ua"] = message["headers"]["ua"]
                    if 'dt' in message["headers"]:
                        ack["headers"]["dt"] = message["headers"]["dt"]
                    await websocket.send(json.dumps(ack))

                    await self.handle_message(message, websocket)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            error_time = time.strftime('%Y-%m-%d %H:%M:%S')
            error_msg = (
                f'闲鱼AI自动回复已断开\n'
                f'时间：{error_time}\n'
                f'错误：{type(e).__name__}: {e}\n\n'
                f'请手动重启：\n'
                f'cd C:\\Users\\Administrator\\XianYuApis\n'
                f'python goofish_live.py'
            )
            send_feishu_notification('❌ 闲鱼AI自动回复已断开', error_msg)
            raise

    async def call_llm(self, user_message: str) -> str:
        """调用 LLM 生成回复"""
        try:
            resp = await llm_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            reply = resp.choices[0].message.content.strip()
            logger.info(f'LLM 回复: {reply}')
            return reply
        except Exception as e:
            logger.error(f'LLM 调用失败: {e}')
            return f'抱歉，我现在有点忙，稍后回复您。'

    async def handle_message(self, message, websocket):
        try:
            data = message["body"]["syncPushPackage"]["data"][0]["data"]
            data = json.loads(data)
            # logger.info(f"无需解密 message: {data}")
        except Exception as e:
            try:
                data = decrypt(data)
                message = json.loads(data)
                # logger.info(f"解密的 message: {message}")

                send_user_name = message["1"]["10"]["reminderTitle"]
                send_user_id = message["1"]["10"]["senderUserId"]
                send_message = message["1"]["10"]["reminderContent"]
                logger.info(f"收到消息 - 用户: {send_user_name}, 内容: {send_message}")

                cid = message["1"]["2"]
                cid = cid.split('@')[0]

                # 检测下单意向
                if check_order_intent(send_message):
                    now = time.strftime('%Y-%m-%d %H:%M:%S')
                    order_msg = (
                        f'用户：{send_user_name}\n'
                        f'用户ID：{send_user_id}\n'
                        f'时间：{now}\n'
                        f'消息：{send_message}\n\n'
                        f'请尽快回复处理！'
                    )
                    send_feishu_notification('💰 客户有购买意向', order_msg)
                    logger.info(f'下单意向已通知飞书 - 用户: {send_user_name}')

                # 调用 LLM 生成回复
                reply = await self.call_llm(send_message)
                await self.send_msg(websocket, cid, send_user_id, make_text(reply))

                # 回复图片
                # res_json = self.xianyu.upload_media(r"D:\Desktop\1.png")
                # image_object = res_json["object"]
                # width, height = map(int, image_object["pix"].split('x'))
                # await self.send_msg(websocket, cid, send_user_id, make_image(image_object["url"], width, height))
            except Exception as e:
                pass


if __name__ == '__main__':
    # 扫码自动登录
    xianyu = qrcode_login()
    cookies_str = '; '.join([f'{c.name}={c.value}' for c in xianyu.session.cookies])
    xianyuLive = XianyuLive(cookies_str)

    # 1 获取全部聊天记录
    # cid = '47812870000'
    # all_messages = asyncio.run(xianyuLive.list_all_conversations(cid))
    # for message in all_messages:
    #     print(message)

    # 2 常驻进程 用于接收消息和 AI 自动回复
    asyncio.run(xianyuLive.main())
