from sqlalchemy import Column, Integer, Float
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///aviator.db"

Base = declarative_base()

class Player(Base):
    __tablename__ = "players"

    user_id = Column(Integer, primary_key=True, index=True)
    balance = Column(Float, default=0.0)

# Engine және сессия
def get_engine():
    return create_async_engine(DATABASE_URL, echo=False)

async_session = sessionmaker(
    get_engine(), class_=AsyncSession, expire_on_commit=False
)
