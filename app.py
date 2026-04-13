import os
import traceback
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    ApiClient,
    MessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import anthropic

load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

BOT_USER_ID = "Ucec80d992abfe01b28e69a9beebc5c11"

app = FastAPI(title="LINEAI")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@app.get("/")
async def root():
    return {"status": "LINEAI is running!"}


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")
    print(f"Received webhook: {body[:200]}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print(f"Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"Webhook error: {traceback.format_exc()}")

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    user_message = event.message.text
    print(f"Received message: {user_message} from {event.source.type}")

    # ในกลุ่ม: ตอบเฉพาะเมื่อถูก Mention เท่านั้น
    if event.source.type == "group":
        mention = getattr(event.message, "mention", None)
        is_mentioned = False
        if mention and mention.mentionees:
            for m in mention.mentionees:
                user_id = getattr(m, "user_id", None)
                if user_id == BOT_USER_ID:
                    is_mentioned = True
                    break
        if not is_mentioned:
            print(f"Not mentioned in group, skipping. Mention: {mention}")
            return
        print(f"Bot was mentioned in group!")

    try:
        # ดึงชื่อ LINE ของผู้ส่ง
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            profile = messaging_api.get_profile(event.source.user_id)
            display_name = profile.display_name

        # ส่งข้อความไปให้ Claude AI ตอบ
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=f"คุณเป็นผู้ช่วย AI ที่ตอบคำถามเป็นภาษาไทย ตอบสั้น กระชับ เข้าใจง่าย เหมาะกับการแชทใน LINE ชื่อผู้ใช้คือ {display_name} เริ่มต้นทักทายด้วย สวัสดีครับ {display_name}",
            messages=[
                {"role": "user", "content": user_message}
            ],
        )

        reply_text = response.content[0].text
        print(f"Claude reply: {reply_text}")

        # ตอบกลับไปใน LINE
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
                )
            )
        print("Reply sent successfully")
    except Exception as e:
        print(f"Error handling message: {traceback.format_exc()}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
