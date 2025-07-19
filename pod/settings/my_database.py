import asyncio
import ssl
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from apps.chats_app.models import GroupModel, GroupParticipantModel, GroupMessageModel, ChatModel, ChatParticipantModel, ChatMessageModel  # noqa
from apps.feeds_app.models import FeedModel, TagModel, CategoryModel, ReportModel, EngagementModel  # noqa
from apps.users_app.models import Base, UserModel  # noqa
from settings.my_config import get_settings
from utility.my_logger import my_logger

settings = get_settings()

ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(settings.CA_PATH))
ssl_context.load_cert_chain(certfile=str(settings.FASTAPI_CLIENT_CERT_PATH), keyfile=str(settings.FASTAPI_CLIENT_KEY_PATH))
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

async_engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args={"ssl": ssl_context})
async_session = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_session)]


async def initialize_db():
    async with async_engine.begin() as conn:
        my_logger.debug("Database is initializing...")
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(initialize_db())
