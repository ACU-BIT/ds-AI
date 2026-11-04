import hmac
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bot
from app.workers.handle_message import handle_message

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/telegram/{bot_id}")
async def telegram_webhook(bot_id: int, request: Request, db: Session = Depends(get_db),
                           x_telegram_bot_api_secret_token: str | None = Header(None)):
    bot = db.get(Bot, bot_id)
    if not bot or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", bot.secret):
        raise HTTPException(403, "forbidden")  # مش تليجرام
    update = await request.json()
    handle_message.delay(bot_id, update)  # نحط في الطابور ونرد فورا
    return {"ok": True}
