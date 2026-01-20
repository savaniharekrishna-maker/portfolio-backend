from fastapi import FastAPI, APIRouter, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --------------------------------------------------
# ENV SETUP
# --------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# --------------------------------------------------
# APP INIT (ONLY ONCE)
# --------------------------------------------------
app = FastAPI()
api_router = APIRouter(prefix="/api")

# --------------------------------------------------
# DATABASE LIFECYCLE
# --------------------------------------------------
@app.on_event("startup")
async def startup_db():
    app.state.mongo_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    app.state.db = app.state.mongo_client[os.environ["DB_NAME"]]

@app.on_event("shutdown")
async def shutdown_db():
    app.state.mongo_client.close()

# --------------------------------------------------
# EMAIL FUNCTION
# --------------------------------------------------
def send_email_notification(name, email, message):
    try:
        response = requests.post(
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
                <p><strong>Name:</strong> {name}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Message:</strong><br>{message}</p>
                """,
            },
            timeout=10,
        )

        response.raise_for_status()

    except Exception as e:
        logging.error(f"Email API error: {e}")


# --------------------------------------------------
# MODELS
# --------------------------------------------------
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class ContactFormSubmit(BaseModel):
    name: str
    email: str
    message: str

class ContactFormResponse(BaseModel):
    id: str
    name: str
    email: str
    message: str
    timestamp: datetime
    read: bool = False

# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

from fastapi import BackgroundTasks

@api_router.post("/contact")
async def submit_contact_form(
    contact_data: ContactFormSubmit,
    request: Request,
    background_tasks: BackgroundTasks,
):
    contact_doc = {
        "name": contact_data.name,
        "email": contact_data.email,
        "message": contact_data.message,
        "timestamp": datetime.utcnow(),
        "read": False,
    }

    await request.app.state.db.contacts.insert_one(contact_doc)

    # EMAIL RUNS IN BACKGROUND (cannot break API)
    # background_tasks.add_task(
    #     send_email_notification,
    #     contact_data.name,
    #     contact_data.email,
    #     contact_data.message,
    # )

    return {
        "success": True,
        "message": "Message saved successfully"
    }


@api_router.get("/contact", response_model=List[ContactFormResponse])
async def get_contact_submissions(request: Request):
    contacts = await request.app.state.db.contacts.find().sort(
        "timestamp", -1
    ).to_list(1000)

    return [
        ContactFormResponse(
            id=str(c["_id"]),
            name=c["name"],
            email=c["email"],
            message=c["message"],
            timestamp=c["timestamp"],
            read=c.get("read", False),
        )
        for c in contacts
    ]

# --------------------------------------------------
# MIDDLEWARE
# --------------------------------------------------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://portfolio-dhnzig9nk-harekrisshnas-projects.vercel.app"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(level=logging.INFO)
