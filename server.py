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
import smtplib
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
        msg = MIMEMultipart()
        msg["From"] = os.environ["EMAIL_USER"]
        msg["To"] = os.environ["EMAIL_TO"]
        msg["Subject"] = "📩 New Portfolio Contact Message"

        body = f"""
New contact form submission:

Name: {name}
Email: {email}

Message:
{message}
"""
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP(os.environ["EMAIL_HOST"], int(os.environ["EMAIL_PORT"]))
        server.starttls()
        server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
        server.send_message(msg)
        server.quit()

    except Exception as e:
        logging.error(f"Email error: {e}")

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

@api_router.post("/contact")
async def submit_contact_form(
    contact_data: ContactFormSubmit,
    request: Request
):
    contact_doc = {
        "name": contact_data.name,
        "email": contact_data.email,
        "message": contact_data.message,
        "timestamp": datetime.utcnow(),
        "read": False,
    }

    result = await request.app.state.db.contacts.insert_one(contact_doc)

    send_email_notification(
        contact_data.name,
        contact_data.email,
        contact_data.message,
    )

    return {"success": True}

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
