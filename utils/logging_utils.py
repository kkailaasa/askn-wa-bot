from models.base import SessionLocal
from models.logs import ConversationLog, ErrorLog
import traceback
import json
from typing import Optional, Dict, Any

def log_conversation(
    phone_number: str,
    message: str,
    response: str,
    conversation_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    db = SessionLocal()
    try:
        log = ConversationLog(
            phone_number=phone_number,
            message=message,
            response=response,
            conversation_id=conversation_id,
            metadata=metadata
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def log_error(
    error_type: str,
    error_message: str,
    conversation_id: Optional[str] = None,
    phone_number: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    db = SessionLocal()
    try:
        log = ErrorLog(
            error_type=error_type,
            error_message=str(error_message),
            stack_trace=traceback.format_exc(),
            conversation_id=conversation_id,
            phone_number=phone_number,
            metadata=metadata
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()