import os
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ask_ai(user_input: str) -> str:
    prompt = f"""
You are Kadek, a friendly Bali travel concierge on WhatsApp.

Your job:
- Help tourists already in Bali decide what to do now, today, or tonight
- Be concise, friendly, and practical
- Suggest Bali places, activities, cafes, beaches, temples, and day plans
- Ask 1 short follow-up question if needed
- Keep replies short enough for WhatsApp

User says: "{user_input}"

Respond like a helpful local guide.
"""
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return response.output_text.strip()

@app.get("/")
def root():
    return {"status": "KadekAI is running"}

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    incoming_msg = (form.get("Body") or "").strip()

    if not incoming_msg:
        reply_text = "Hi, I’m Kadek 👋 Your Bali travel concierge. What are you in the mood for today?"
    else:
        try:
            reply_text = ask_ai(incoming_msg)
        except Exception:
            reply_text = "Sorry, I hit a small issue just now. Try again in a moment."

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return PlainTextResponse(str(twiml), media_type="application/xml")
