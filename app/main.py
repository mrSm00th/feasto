from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app.db.models_registry
from app.db.database import Base, engine, get_db
from app.modules.admin import router as admins
from app.modules.menus import router as menus
from app.modules.partner_applications import router as partner_applications
from app.modules.restaurants import router as restaurants
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


app.mount("/media", StaticFiles(directory="media"), name="media")


app.include_router(users.router)
app.include_router(partner_applications.router)
app.include_router(admins.router)
app.include_router(restaurants.router)
app.include_router(menus.router)
