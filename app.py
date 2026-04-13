import os
import traceback
import httpx
from datetime import datetime
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
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import anthropic

load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

app = FastAPI(title="LINE Bot with Claude AI")

SAVE_DIR = "พารวย"
os.makedirs(SAVE_DIR, exist_ok=True)

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


@app.get("/")
async def root():
    return {"status": "LINE Bot is running!"}


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
    # Log source info เพื่อดึง group ID
    if event.source.type == "group":
        print(f"GROUP ID: {event.source.group_id}")
    print(f"Received message: {user_message} from {event.source.type}")

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


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event: MessageEvent):
    message_id = event.message.id
    print(f"Received image: {message_id}")

    try:
        # ดึงชื่อ LINE ของผู้ส่ง
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            profile = messaging_api.get_profile(event.source.user_id)
            display_name = profile.display_name

        # ดาวน์โหลดรูปจาก LINE
        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
        headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
        response = httpx.get(url, headers=headers)
        image_data = response.content

        # อัปโหลดรูปไป Imgur เพื่อเอา URL
        import base64
        img_b64 = base64.b64encode(image_data).decode()
        imgur_res = httpx.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            data={"image": img_b64, "type": "base64"}
        )
        image_url = imgur_res.json()["data"]["link"]
        print(f"Uploaded to imgur: {image_url}")

        # ส่งรูปต่อไปกลุ่มที่กำหนด
        forward_group_id = os.getenv("FORWARD_GROUP_ID")
        if forward_group_id:
            push_url = "https://api.line.me/v2/bot/message/push"
            push_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
            }
            push_data = {
                "to": forward_group_id,
                "messages": [
                    {"type": "text", "text": f"📸 รูปจาก {display_name}"},
                    {"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url}
                ]
            }
            push_res = httpx.post(push_url, headers=push_headers, json=push_data)
            print(f"Forwarded to group: {push_res.status_code}")

        # ตอบกลับผู้ส่ง
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f"สวัสดีครับ {display_name} ได้รับรูปภาพแล้วครับ ส่งต่อเรียบร้อย 📸")]
                )
            )
        print("Image reply sent successfully")
    except Exception as e:
        print(f"Error handling image: {traceback.format_exc()}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
