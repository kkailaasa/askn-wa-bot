# services/sequence_manager.py

from enum import Enum
from fastapi import HTTPException
from typing import Dict, Any, Optional, List, Tuple
import json
from utils.redis_pool import get_redis_client
import logging
from datetime import datetime
import asyncio
from pydantic import BaseModel, ValidationError
from redis.client import Pipeline
from redis.exceptions import WatchError
import functools
from core.config import settings
from utils.redis_helpers import AsyncRedisLock, redis_helper, cache

logger = logging.getLogger(__name__)

class AccountCreationStep(str, Enum):
    CHECK_PHONE = "check_phone"
    CHECK_EMAIL = "check_email"
    CREATE_ACCOUNT = "create_account"
    SEND_EMAIL_OTP = "send_email_otp"
    VERIFY_EMAIL = "verify_email"

STEP_SEQUENCE = {
    AccountCreationStep.CHECK_PHONE: None,  # First step
    AccountCreationStep.CHECK_EMAIL: AccountCreationStep.CHECK_PHONE,
    AccountCreationStep.CREATE_ACCOUNT: AccountCreationStep.CHECK_EMAIL,
    AccountCreationStep.SEND_EMAIL_OTP: AccountCreationStep.CREATE_ACCOUNT,
    AccountCreationStep.VERIFY_EMAIL: AccountCreationStep.SEND_EMAIL_OTP,
}

# Step-specific data validation models
class PhoneCheckData(BaseModel):
    phone_number: str
    verification_status: Optional[bool] = False
    timestamp: str

class EmailCheckData(BaseModel):
    email: str
    phone_number: str
    verification_status: Optional[bool] = False
    timestamp: str

class AccountCreationData(BaseModel):
    phone_number: str
    email: str
    first_name: str
    last_name: str
    gender: str
    country: str
    timestamp: str

class EmailVerificationData(BaseModel):
    email: str
    otp_attempts: int = 0
    verified: bool = False
    timestamp: str

STEP_VALIDATORS = {
    AccountCreationStep.CHECK_PHONE: PhoneCheckData,
    AccountCreationStep.CHECK_EMAIL: EmailCheckData,
    AccountCreationStep.CREATE_ACCOUNT: AccountCreationData,
    AccountCreationStep.VERIFY_EMAIL: EmailVerificationData
}

def with_retry(max_retries: int = 3, retry_delay: float = 0.1):
    """Decorator for retrying Redis operations"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except WatchError as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                except Exception as e:
                    raise e
            raise last_error
        return wrapper
    return decorator

class TransactionManager:
    """Manages atomic operations and transactions"""
    def __init__(self, redis_client):
        self.redis_client = redis_client

    async def execute_transaction(self, keys: List[str], operation: callable) -> Any:
        """Execute an atomic transaction with optimistic locking"""
        pipeline = self.redis_client.pipeline()
        while True:
            try:
                # Watch the keys for changes
                pipeline.watch(*keys)
                # Execute the operation
                result = await operation(pipeline)
                pipeline.execute()
                return result
            except WatchError:
                # Key changed during transaction, retry
                await asyncio.sleep(0.1)
                continue
            finally:
                pipeline.reset()

class SequenceManager:
    def __init__(self):
        self.redis_client = get_redis_client()
        self.sequence_expiry = 3600  # 1 hour
        self.transaction_manager = TransactionManager(self.redis_client)
        self.max_retries = 3
        self.retry_delay = 0.1

    def _get_sequence_key(self, identifier: str) -> str:
        return f"sequence:{identifier}"

    def _get_data_key(self, identifier: str) -> str:
        return f"sequence_data:{identifier}"

    def _get_lock_key(self, identifier: str) -> str:
        return f"sequence_lock:{identifier}"

    async def _acquire_lock(self, identifier: str, timeout: int = 10) -> bool:
        """Acquire a distributed lock with timeout"""
        lock_key = self._get_lock_key(identifier)
        acquired = await self.transaction_manager.execute_transaction(
            [lock_key],
            lambda pipe: pipe.set(lock_key, "1", nx=True, ex=timeout)
        )
        return bool(acquired)

    async def _release_lock(self, identifier: str) -> bool:
        """Release a distributed lock"""
        lock_key = self._get_lock_key(identifier)
        return bool(self.redis_client.delete(lock_key))

    @with_retry(max_retries=3)
    async def validate_step_data(self, step: AccountCreationStep, data: Dict[str, Any]) -> None:
        """Validate step-specific data using Pydantic models"""
        validator = STEP_VALIDATORS.get(step)
        if validator:
            try:
                validated_data = validator(**data)
                return validated_data.dict()
            except ValidationError as e:
                logger.error(f"Data validation failed for step {step}: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid data for step {step}: {str(e)}"
                )
        return data

    @with_retry(max_retries=3)
    async def start_sequence(self, identifier: str) -> None:
        """Initialize a new sequence with atomic operation"""
        sequence_key = self._get_sequence_key(identifier)
        data_key = self._get_data_key(identifier)

        async def transaction(pipe: Pipeline):
            pipe.multi()
            pipe.set(sequence_key, AccountCreationStep.CHECK_PHONE, ex=self.sequence_expiry)
            pipe.set(data_key, json.dumps({"started_at": datetime.utcnow().isoformat()}), ex=self.sequence_expiry)

        await self.transaction_manager.execute_transaction(
            [sequence_key, data_key],
            transaction
        )
        logger.info(f"Started new sequence for {identifier}")

    @with_retry(max_retries=3)
    async def validate_step(self, identifier: str, current_step: AccountCreationStep) -> None:
        """Validate step with atomic operation"""
        async with AsyncRedisLock(f"sequence:{identifier}"):
            sequence_key = self._get_sequence_key(identifier)
            redis = await self.redis_helper.get_redis()

            last_step = await redis.get(sequence_key)
            if not last_step:
                if current_step != AccountCreationStep.CHECK_PHONE:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid sequence. Please start with phone number verification."
                    )
                await self.start_sequence(identifier)
                return

            last_step = AccountCreationStep(last_step)
            required_previous_step = STEP_SEQUENCE.get(current_step)

            if required_previous_step and last_step != required_previous_step:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid sequence. {current_step} must follow {required_previous_step}"
                )


    @with_retry(max_retries=3)
    async def update_step(self, identifier: str, step: AccountCreationStep) -> None:
        """Update step with atomic operation"""
        if not await self._acquire_lock(identifier):
            raise HTTPException(status_code=423, detail="Resource locked")

        try:
            sequence_key = self._get_sequence_key(identifier)

            async def transaction(pipe: Pipeline):
                pipe.multi()
                pipe.set(sequence_key, step, ex=self.sequence_expiry)

            await self.transaction_manager.execute_transaction([sequence_key], transaction)
            logger.info(f"Updated sequence step for {identifier} to {step}")

        finally:
            await self._release_lock(identifier)

    @with_retry(max_retries=3)
    async def store_step_data(self, identifier: str, step: AccountCreationStep, data: Dict[str, Any]) -> None:
        """Store validated step data atomically"""
        if not await self._acquire_lock(identifier):
            raise HTTPException(status_code=423, detail="Resource locked")

        try:
            data_key = self._get_data_key(identifier)
            validated_data = await self.validate_step_data(step, data)

            async def transaction(pipe: Pipeline):
                existing_data = pipe.get(data_key)
                current_data = json.loads(existing_data) if existing_data else {}
                current_data.update({
                    step: validated_data,
                    "last_updated": datetime.utcnow().isoformat()
                })
                pipe.multi()
                pipe.set(data_key, json.dumps(current_data), ex=self.sequence_expiry)

            await self.transaction_manager.execute_transaction([data_key], transaction)
            logger.debug(f"Stored step data for {identifier}: {validated_data}")

        finally:
            await self._release_lock(identifier)

    @with_retry(max_retries=3)
    async def get_step_data(self, identifier: str, step: Optional[AccountCreationStep] = None) -> Optional[Dict[str, Any]]:
        """Retrieve stored data with optional step filter"""
        data_key = self._get_data_key(identifier)
        try:
            data = self.redis_client.get(data_key)
            if data:
                all_data = json.loads(data)
                if step:
                    return all_data.get(step)
                return all_data
        except Exception as e:
            logger.error(f"Error retrieving step data for {identifier}: {str(e)}")
        return None

    async def cleanup_expired_sequences(self) -> None:
        """Remove expired sequences and their data"""
        try:
            pattern = "sequence:*"
            for key in self.redis_client.scan_iter(pattern):
                identifier = key.decode().split(':')[1]
                if self.redis_client.ttl(key) <= 0:
                    await self.clear_sequence(identifier)
                    logger.info(f"Cleaned up expired sequence for {identifier}")
        except Exception as e:
            logger.error(f"Error cleaning up sequences: {str(e)}")

    async def clear_sequence(self, identifier: str) -> None:
        """Clear all sequence data"""
        keys = [
            self._get_sequence_key(identifier),
            self._get_data_key(identifier),
            self._get_lock_key(identifier)
        ]
        self.redis_client.delete(*keys)

    async def get_sequence_status(self, identifier: str) -> Dict[str, Any]:
        """Get detailed sequence status"""
        sequence_key = self._get_sequence_key(identifier)
        data = await self.get_step_data(identifier)
        current_step = self.redis_client.get(sequence_key)

        return {
            "current_step": current_step.decode() if current_step else None,
            "has_data": bool(data),
            "last_updated": data.get('last_updated') if data else None,
            "completed_steps": [step for step in AccountCreationStep if step in (data or {})],
            "has_errors": bool(data and data.get('last_error'))
        }

# Initialize singleton instance
sequence_manager = SequenceManager()