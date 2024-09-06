import sys
import os

sys.path.append("./")
from prismadb import Prisma
from celery import Celery
import asyncio

from dotenv import load_dotenv
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
# Set up a Celery instance
celery_app = Celery(
    "celery_app",
    broker=f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_redirect_stdouts=False,
)

@celery_app.task(name="celery_login", bind=True, max_retries=3)
def celery_login(self, name, user_email):
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(create_user(name, user_email))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

async def create_user(user_mail: str, name: str):
    db = Prisma()
    await db.connect()
    try:
        new_user = await db.user.create(
            data={
                "user_email": user_mail,
                "name": name,
            }
        )
        return new_user
    except Exception as e:
        return None
    finally:
        await db.disconnect()