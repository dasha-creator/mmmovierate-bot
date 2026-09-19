from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Float, ForeignKey, UniqueConstraint
from datetime import datetime

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    invited_by = Column(BigInteger, nullable=True)  # telegram_id кто пригласил

class UserMovie(Base):
    __tablename__ = "user_movies"
    id = Column(Integer, primary_key=True)
    user_telegram_id = Column(BigInteger, nullable=False)
    tmdb_id = Column(Integer, nullable=False)
    media_type = Column(String, nullable=False)  # movie / tv
    title = Column(String, nullable=False)
    poster_path = Column(String, nullable=True)
    status = Column(String, nullable=False)  # watchlist / watched
    rating = Column(Integer, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    watched_at = Column(DateTime, nullable=True)
    recommended_by = Column(BigInteger, nullable=True)  # telegram_id кто посоветовал
    
    __table_args__ = (
        UniqueConstraint("user_telegram_id", "tmdb_id", "media_type", name="uq_user_movie"),
    )

class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True)
    from_telegram_id = Column(BigInteger, nullable=False)
    to_telegram_id = Column(BigInteger, nullable=False)
    tmdb_id = Column(Integer, nullable=False)
    media_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    poster_path = Column(String, nullable=True)
    message = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    seen = Column(Integer, default=0)  # 0/1

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session():
    async with async_session() as session:
        yield session
