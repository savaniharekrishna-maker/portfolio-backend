from fastapi import FastAPI, APIRouter
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


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Contact Form Models
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

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

# Contact Form Routes
@api_router.post("/contact")
async def submit_contact_form(contact_data: ContactFormSubmit):
    try:
        # Create contact document
        contact_doc = {
            "name": contact_data.name,
            "email": contact_data.email,
            "message": contact_data.message,
            "timestamp": datetime.utcnow(),
            "read": False
        }
        
        # Insert into MongoDB
        result = await db.contacts.insert_one(contact_doc)
        
        return {
            "success": True,
            "message": "Contact form submitted successfully",
            "id": str(result.inserted_id)
        }
    except Exception as e:
        logging.error(f"Error submitting contact form: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to submit contact form: {str(e)}"
        }

@api_router.get("/contact", response_model=List[ContactFormResponse])
async def get_contact_submissions():
    try:
        contacts = await db.contacts.find().sort("timestamp", -1).to_list(1000)
        return [
            ContactFormResponse(
                id=str(contact["_id"]),
                name=contact["name"],
                email=contact["email"],
                message=contact["message"],
                timestamp=contact["timestamp"],
                read=contact.get("read", False)
            )
            for contact in contacts
        ]
    except Exception as e:
        logging.error(f"Error fetching contacts: {str(e)}")
        return []

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()