from fastapi import FastAPI, APIRouter, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from datetime import datetime
from typing import List
import os
import logging
import requests
from dotenv import load_dotenv
from pathlib import Path

# --------------------------------------------------
# ENV
# --------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# --------------------------------------------------
# APP
# --------------------------------------------------
app = FastAPI()
api_router = APIRouter(prefix="/api")

# --------------------------------------------------
# CORS (IMPORTANT)
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # keep * until fully stable
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# DB LIFECYCLE
# --------------------------------------------------
@app.on_event("startup")
async def startup():
    app.state.client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    app.state.db = app.state.client[os.environ["DB_NAME"]]

@app.on_event("shutdown")
async def shutdown():
    app.state.client.close()

# --------------------------------------------------
# EMAIL (RESEND)
# --------------------------------------------------
def send_email_notification(name, email, message):
    try:
        requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "from": "Portfolio <onboarding@resend.dev>",
                "to": [os.environ["EMAIL_TO"]],
                "subject": "📩 New Portfolio Contact Message",
                "html": f"""
                <h3>New Contact Form Submission</h3>
                <p><b>Name:</b> {name}</p>
                <p><b>Email:</b> {email}</p>
                <p><b>Message:</b><br>{message}</p>
                """,
            },
            timeout=10,
        )
    except Exception as e:
        logging.error(f"Email error: {e}")

# --------------------------------------------------
# MODELS
# --------------------------------------------------
class ContactForm(BaseModel):
    name: str
    email: str
    message: str

class ContactOut(BaseModel):
    id: str
    name: str
    email: str
    message: str
    timestamp: datetime
    read: bool

# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@api_router.get("/")
async def root():
    return {"status": "API running"}

@api_router.post("/contact")
async def submit_contact(
    data: ContactForm,
    request: Request,
    background_tasks: BackgroundTasks,
):
    doc = {
        "name": data.name,
        "email": data.email,
        "message": data.message,
        "timestamp": datetime.utcnow(),
        "read": False,
    }

    await request.app.state.db.contacts.insert_one(doc)

    background_tasks.add_task(
        send_email_notification,
        data.name,
        data.email,
        data.message,
    )

    return {"success": True}

@api_router.get("/contact", response_model=List[ContactOut])
async def get_contacts(request: Request):
    contacts = await request.app.state.db.contacts.find().sort(
        "timestamp", -1
    ).to_list(1000)

    return [
        {
            "id": str(c["_id"]),
            "name": c["name"],
            "email": c["email"],
            "message": c["message"],
            "timestamp": c["timestamp"],
            "read": c.get("read", False),
        }
        for c in contacts
    ]

# --------------------------------------------------
# REGISTER ROUTER
# --------------------------------------------------
app.include_router(api_router)

logging.basicConfig(level=logging.INFO)


