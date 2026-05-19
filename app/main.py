from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status

import app.db.models_registry
from app.db.database import Base, engine, get_db
from app.modules.admin import router as admin
from app.modules.owner_applications import router as owner_applications
from app.modules.users import router as users


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


app.include_router(users.router)
app.include_router(owner_applications.router)
app.include_router(admin.router)
