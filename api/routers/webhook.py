"""
WhatsApp webhook router — thin HTTP wrapper over services.webhook.
Handles Twilio signature validation and HTTP response formatting only.
All business logic lives in services/webhook.py.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from integrations import twilio_client
from services import webhook as webhook_svc

router = APIRouter()


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    x_twilio_signature: str = Header(default=""),
):
    # Validate Twilio signature
    form_data = dict(await request.form())
    url = str(request.url).replace("http://", "https://", 1)

    if not twilio_client.validate_signature(url, form_data, x_twilio_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

    message = twilio_client.parse_inbound(form_data)

    result = await webhook_svc.process_webhook_message(db, message, background_tasks)

    return {"status": result}
