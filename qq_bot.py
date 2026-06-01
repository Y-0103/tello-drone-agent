import asyncio,os,botpy,aiohttp,base64
from botpy.types.message import Message
from agent import main
from tencentcloud.common import credential
from tencentcloud.asr.v20190614 import asr_client, models
from djitellopy import Tello
from dotenv import load_dotenv

load_dotenv()

class MyClient(botpy.Client):
    def __init__(self,intents):
        super().__init__(intents = intents)
        cred = credential.Credential(os.getenv("TENCENTCLOUD_KEY_ID"),
                                     os.getenv("TENCENTCLOUD_KEY_SECRET"))
        self.asr_cli = asr_client.AsrClient(cred, "ap-chengdu")

    async def on_c2c_message_create(self, message: Message):
        print(f"[私聊任务], 消息ID={message.id}, 内容={message.content}")
        await self.process_message(message)

    async def process_message(self, message: Message):
        user_openid = message.author.user_openid
        config = {"configurable": {"thread_id": user_openid,
                                   "tello": tello,}}
        voice_attachment = None
        # 语音信息
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type in ("voice", "audio"):
                    voice_attachment = attachment
                    break

        if voice_attachment:
            try:
                voice_url =  voice_attachment.url
                voice_data = await self._download_file(voice_url)
                input_text = await self._speech_to_text(voice_data)
                print(f"语音识别结果: {input_text}")
            except Exception as e:
                await self.api.post_c2c_message(
                    openid=user_openid, content="未识别语言信息。"
                )
                return
        # 文本信息
        else:
            input_text = message.content

        response = await main(input_text, config)
        response_text = response["messages"][-1].content

        try:
            await self.api.post_c2c_message(openid=user_openid, content=response_text)
        except Exception as e:
            print("回复失败")

    async def _download_file(self, url: str) -> bytes:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    raise Exception(f"下载失败")

    async def _speech_to_text(self, voice_data: bytes) -> str:
        voice_base64 = base64.b64encode(voice_data).decode("utf-8")
        # 识别一句话
        mod = models.SentenceRecognitionRequest()
        mod.EngSerViceType = "16k_zh"
        mod.SourceType = 1
        mod.VoiceFormat = "silk"
        mod.Data = voice_base64
        mod.DataLen = len(voice_data)

        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, self.asr_cli.SentenceRecognition, mod)
        if resp.Result:
            return resp.Result.strip()
        else:
            raise Exception("未识别结果")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    intents = botpy.Intents(public_messages=True, direct_message=True)
    client = MyClient(intents=intents)
    tello = Tello()
    #tello.connect()
    client.run(appid=os.getenv("QQ_APPID"), secret=os.getenv("QQ_SECRET"))
