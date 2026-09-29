import asyncio
import json
import logging
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import BASE_DIR, BATCH_CONCURRENCY, JEV_MODEL
from app.models import BatchIn, RoutingDecision, StatusOut, TicketIn
from app.router import TicketRouter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("jev_support_router")

app = FastAPI(
    title="Jev Support Ticket Router",
    description="Routes support tickets with TypeSafe's Jev System One model",
    version="0.1.0",
)

router = TicketRouter()
tickets: List[RoutingDecision] = []  # in-memory store, newest first


async def _route_or_http_error(ticket: TicketIn) -> RoutingDecision:
    try:
        return await router.route(ticket)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Jev routing failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Jev request failed: {e}")


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/status", response_model=StatusOut)
async def status():
    return StatusOut(jev_configured=router.configured, model=JEV_MODEL, tickets_routed=len(tickets))


@app.post("/api/tickets", response_model=RoutingDecision)
async def route_ticket(ticket: TicketIn):
    decision = await _route_or_http_error(ticket)
    tickets.insert(0, decision)
    return decision


@app.post("/api/tickets/batch", response_model=List[RoutingDecision])
async def route_batch(batch: BatchIn):
    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def limited(t: TicketIn):
        async with semaphore:
            return await _route_or_http_error(t)

    decisions = await asyncio.gather(*(limited(t) for t in batch.tickets))
    tickets[:0] = decisions
    return decisions


@app.get("/api/tickets", response_model=List[RoutingDecision])
async def list_tickets():
    return tickets


@app.delete("/api/tickets")
async def clear_tickets():
    tickets.clear()
    return {"cleared": True}


@app.get("/api/samples", response_model=List[TicketIn])
async def sample_tickets():
    with open(BASE_DIR / "sample_data" / "tickets.json") as f:
        return json.load(f)
