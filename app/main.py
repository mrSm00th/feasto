from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db.database import engine
from app.modules.admins import router as admins
from app.modules.menus import router as menus
from app.modules.partner_applications import router as partner_applications
from app.modules.restaurants import router as restaurants
from app.modules.users import router as users


# generatings tables using alembic
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
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
