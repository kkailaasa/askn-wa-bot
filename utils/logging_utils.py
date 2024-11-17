# utils/logging_utils.py

from db_scripts.base import SessionLocal, AsyncSessionLocal, get_db
import traceback
from typing import Optional, Dict, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from db_scripts.logs import ConversationLog, ErrorLog

async def log_error_async(
    db: AsyncSession,
    error_type: str,
    error_message: str,
    conversation_id: Optional[str] = None,
    phone_number: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
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
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise

def log_error_sync(
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
        raise
    finally:
        db.close()

# Function that handles both async and sync cases
def log_error(
    error_type: str,
    error_message: str,
    conversation_id: Optional[str] = None,
    phone_number: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Union[AsyncSession, Session]] = None
):
    if db is not None and isinstance(db, AsyncSession):
        return log_error_async(db, error_type, error_message, conversation_id, phone_number, metadata)
    else:
        return log_error_sync(error_type, error_message, conversation_id, phone_number, metadata)

async def log_conversation_async(
    db: AsyncSession,
    phone_number: str,
    message: str,
    response: str,
    conversation_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    try:
        log = ConversationLog(
            phone_number=phone_number,
            message=message,
            response=response,
            conversation_id=conversation_id,
            metadata=metadata
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise

def log_conversation_sync(
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
        raise
    finally:
        db.close()

# Function that handles both async and sync cases
def log_conversation(
    phone_number: str,
    message: str,
    response: str,
    conversation_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Union[AsyncSession, Session]] = None
):
    if db is not None and isinstance(db, AsyncSession):
        return log_conversation_async(db, phone_number, message, response, conversation_id, metadata)
    else:
        return log_conversation_sync(phone_number, message, response, conversation_id, metadata)