from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import random
from typing import Dict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Bet(BaseModel):
    user_id: int
    amount: float

class CashoutRequest(BaseModel):
    user_id: int

class BalanceTopUp(BaseModel):
    user_id: int
    amount: float

# Ойын ішкі мәліметтері
balances: Dict[int, float] = {}
bets: Dict[int, Dict[str, float]] = {}
connections: Dict[int, WebSocket] = {}
current_multiplier = 1.0
crash_multiplier = 2.0
round_active = False

# Баланс сұрау
@app.get("/balance")
async def get_balance(user_id: int):
    return {"balance": round(balances.get(user_id, 0.0), 2)}

# Баланс толтыру
@app.post("/topup_balance")
async def topup_balance(data: BalanceTopUp):
    balances[data.user_id] = balances.get(data.user_id, 0.0) + data.amount
    return {"message": "Баланс толықтырылды"}

# Ставка қою
@app.post("/place_bet")
async def place_bet(bet: Bet):
    if not round_active:
        return {"error": "Раунд әлі басталған жоқ"}
    if balances.get(bet.user_id, 0) < bet.amount:
        return {"error": "Жеткілікті баланс жоқ"}
    balances[bet.user_id] -= bet.amount
    bets[bet.user_id] = {"amount": bet.amount, "auto_cashout": None}
    return {"message": "Ставка қабылданды"}

# Кэшаут жасау
@app.post("/cashout")
async def cashout(data: CashoutRequest):
    if data.user_id in bets:
        win = bets[data.user_id]["amount"] * current_multiplier
        balances[data.user_id] += win
        del bets[data.user_id]
        return {"message": f"Кэшаут сәтті! Ұтыс: {round(win, 2)}"}
    return {"error": "Ставка табылмады"}

# WebSocket байланысы
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    connections[user_id] = websocket
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        del connections[user_id]

# Раундты автоматты түрде іске қосу
async def round_loop():
    global current_multiplier, crash_multiplier, round_active
    while True:
        await asyncio.sleep(3)  # Раунд арасындағы үзіліс
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
async def startup_event():
    asyncio.create_task(round_loop())
