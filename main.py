from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict
from models import Base, get_engine
import asyncio
import random

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, Float, select

# -------------------- Database setup --------------------
DATABASE_URL = "sqlite+aiosqlite:///./aviator.db"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    balance = Column(Float, default=0.0)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# -------------------- FastAPI setup --------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Models --------------------
class Bet(BaseModel):
    user_id: int
    amount: float

class CashoutRequest(BaseModel):
    user_id: int

class BalanceTopUp(BaseModel):
    user_id: int
    amount: float

# -------------------- Game state --------------------
bets: Dict[int, Dict[str, float]] = {}
connections: Dict[int, WebSocket] = {}
current_multiplier = 1.0
crash_multiplier = 2.0
round_active = False

# -------------------- API Endpoints --------------------
@app.get("/balance")
async def get_balance(user_id: int):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        return {"balance": round(user.balance, 2) if user else 0.0}

@app.post("/topup_balance")
async def topup_balance(data: BalanceTopUp):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == data.user_id))
        user = result.scalar_one_or_none()
        if user:
            user.balance += data.amount
        else:
            user = User(user_id=data.user_id, balance=data.amount)
            session.add(user)
        await session.commit()
        return {"message": "Баланс толықтырылды"}

@app.post("/place_bet")
async def place_bet(bet: Bet):
    global round_active
    if not round_active:
        return {"error": "Раунд әлі басталған жоқ"}

    async with async_session() as session:
        result = await session.execute(select(User).where(User.user_id == bet.user_id))
        user = result.scalar_one_or_none()
        if not user or user.balance < bet.amount:
            return {"error": "Жеткілікті баланс жоқ"}
        user.balance -= bet.amount
        bets[bet.user_id] = {"amount": bet.amount, "auto_cashout": None}
        await session.commit()
        return {"message": "Ставка қабылданды"}

@app.post("/cashout")
async def cashout(data: CashoutRequest):
    if data.user_id in bets:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.user_id == data.user_id))
            user = result.scalar_one_or_none()
            if not user:
                return {"error": "Пайдаланушы табылмады"}
            win = bets[data.user_id]["amount"] * current_multiplier
            user.balance += win
            del bets[data.user_id]
            await session.commit()
            return {"message": f"Кэшаут сәтті! Ұтыс: {round(win, 2)}"}
    return {"error": "Ставка табылмады"}

# -------------------- WebSocket --------------------
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    connections[user_id] = websocket
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        del connections[user_id]

# -------------------- Game Loop --------------------
async def round_loop():
    global current_multiplier, crash_multiplier, round_active
    while True:
        await asyncio.sleep(3)  # Pause before round starts
        round_active = True
        current_multiplier = 1.0
        crash_multiplier = round(random.uniform(1.5, 3.0), 2)
        await broadcast({"event": "start", "crash_at": crash_multiplier})

        while current_multiplier < crash_multiplier:
            await asyncio.sleep(0.1)
            current_multiplier = round(current_multiplier + 0.01, 2)
            await broadcast({"event": "update", "multiplier": current_multiplier})

        round_active = False
        await broadcast({"event": "crash", "at": crash_multiplier})
        bets.clear()

async def broadcast(message: dict):
    for ws in connections.values():
        await ws.send_json(message)

@app.on_event("startup")
async def startup():
    # 🔧 Дерекқор кестесін жасау
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 🚀 Aviator ойынының циклін іске қосу
    asyncio.create_task(round_loop())
