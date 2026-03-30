import csv
import os
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def load_places():
    places = []
    with open("places.csv", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # normalize missing fields safely
            places.append({
                "name": row.get("name", "").strip(),
                "location": row.get("location", "").strip(),
                "description": row.get("description", "").strip(),
                "vibe": row.get("vibe", "").strip(),
                "best_time": row.get("best_time", "").strip(),
                "budget": row.get("budget", "").strip(),
            })
    return places


def extract_preferences(user_input: str):
    text = user_input.lower()

    locations = [
        "ubud", "canggu", "uluwatu", "seminyak", "kuta",
        "sanur", "nusa dua", "jimbaran", "sidemen", "denpasar"
    ]
    vibes = [
        "chill", "trendy", "cultural", "romantic", "party",
        "local", "quiet", "luxury", "family"
    ]
    time_keywords = [
        "morning", "breakfast", "brunch", "afternoon",
        "sunset", "dinner", "night", "tonight"
    ]
    budget_keywords = ["$", "$$", "$$$", "cheap", "budget", "affordable", "luxury"]

    location = next((loc for loc in locations if loc in text), None)
    vibe = next((v for v in vibes if v in text), None)
    time_intent = next((t for t in time_keywords if t in text), None)
    budget = next((b for b in budget_keywords if b in text), None)

    return {
        "location": location,
        "vibe": vibe,
        "time": time_intent,
        "budget": budget,
    }


def score_place(place, prefs):
    score = 0

    place_location = place.get("location", "").lower()
    place_description = place.get("description", "").lower()
    place_vibe = place.get("vibe", "").lower()
    place_best_time = place.get("best_time", "").lower()
    place_budget = place.get("budget", "").lower()

    # hard-prioritized location
    if prefs["location"] and prefs["location"] in place_location:
        score += 10

    # soft matches
    if prefs["vibe"]:
        if prefs["vibe"] in place_vibe or prefs["vibe"] in place_description:
            score += 3

    if prefs["time"]:
        if prefs["time"] in place_best_time or prefs["time"] in place_description:
            score += 2

    if prefs["budget"]:
        if prefs["budget"] in place_budget or prefs["budget"] in place_description:
            score += 2

    return score


def filter_places(places, prefs, limit=8):
    filtered = places

    # HARD FILTER: if user mentions a location, only show that location
    if prefs["location"]:
        filtered = [
            p for p in filtered
            if prefs["location"] in p.get("location", "").lower()
        ]

    # if nothing remains after location filtering, return empty immediately
    if not filtered:
        return []

    # rank remaining places by soft preferences
    ranked = sorted(
        filtered,
        key=lambda p: score_place(p, prefs),
        reverse=True
    )

    return ranked[:limit]


def ask_clarifying_question(prefs):
    if not prefs["location"]:
        return "Which area are you in or asking about? Ubud, Canggu, Uluwatu, Seminyak, or somewhere else?"
    return "Can you tell me a bit more about the vibe you want — chill, trendy, cultural, sunset, or budget-friendly?"


def ask_ai(user_input: str) -> str:
    places = load_places()
    prefs = extract_preferences(user_input)
    filtered_places = filter_places(places, prefs)

    # if user gave no location, better to clarify than guess across Bali
    if not prefs["location"]:
        return ask_clarifying_question(prefs)

    # if location was given but nothing matched, do not hallucinate
    if not filtered_places:
        return f"I couldn’t find a good match in {prefs['location'].title()} yet. Want cafes, restaurants, beach clubs, temples, or something else?"

    places_text = ""
    for p in filtered_places:
        places_text += (
            f"- {p['name']} ({p['location']})"
            f" | vibe: {p.get('vibe', '-')}"
            f" | best_time: {p.get('best_time', '-')}"
            f" | budget: {p.get('budget', '-')}"
            f" | {p['description']}\n"
        )

    prompt = f"""
You are Kadek, a friendly Bali travel concierge on WhatsApp.

IMPORTANT RULES:
- Recommend ONLY from the filtered list below
- Do NOT mention places outside this list
- Give max 3 suggestions
- Keep it concise and helpful
- Sound warm, local, and natural
- If useful, briefly explain why each place matches the user's request

User request:
{user_input}

Detected preferences:
- location: {prefs['location']}
- vibe: {prefs['vibe']}
- time: {prefs['time']}
- budget: {prefs['budget']}

Filtered places:
{places_text}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    return response.output_text.strip()

@app.get("/")
def root():
    return {"status": "KadekAI is running"}

@app.get("/")
def root():
    return {"status": "KadekAI is running"}


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    form = await request.form()
    incoming_msg = (form.get("Body") or "").strip()
    sender = (form.get("From") or "").strip()

    if not incoming_msg:
        reply_text = "Hi, I’m Kadek 👋 Your Bali travel concierge. What are you in the mood for today?"
    else:
        try:
            print(f"[WhatsApp] From: {sender} | Message: {incoming_msg}")
            reply_text = ask_ai(incoming_msg)
            print(f"[Kadek Reply] {reply_text}")
        except Exception as e:
            print(f"[Error] whatsapp_webhook: {e}")
            reply_text = "Sorry, I hit a small issue just now. Try again in a moment."

    twiml = MessagingResponse()
    twiml.message(reply_text)

    return PlainTextResponse(str(twiml), media_type="application/xml")