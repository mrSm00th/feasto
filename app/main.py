from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db.database import engine
from app.db.models_registry import load_models
from app.modules.addresses import router as addresses
from app.modules.admins import router as admins
from app.modules.carts import router as carts
from app.modules.locations import router as locations
from app.modules.menus import router as menus
from app.modules.notifications import router as notifications
from app.modules.orders import customer_orders_router as customer_orders
from app.modules.orders import restaurant_orders_router as restaurant_orders
from app.modules.partner_applications import router as partner_applications
from app.modules.payments.router import router as payments_router
from app.modules.realtime import router as realtime
from app.modules.restaurants import router as restaurants
from app.modules.rider_applications import router as admmin_rider_application
from app.modules.rider_applications import router as rider_applications
from app.modules.riders import router as riders
from app.modules.users import router as users
from app.modules.riders import payout_router 


# generatings tables using alembic
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # STARTUP
    # RUN APP
    yield

    # SHUTDOWN
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


app.mount("/media", StaticFiles(directory="media"), name="media")

load_models()


app.include_router(users.router)
app.include_router(partner_applications.router)
app.include_router(admins.router)
app.include_router(restaurants.router)
app.include_router(menus.router)
app.include_router(carts.router)
app.include_router(addresses.router)
app.include_router(payments_router)
app.include_router(
    restaurant_orders.restaurant_orders_router
)  # handles the incomming orders and stuff
app.include_router(
    restaurant_orders.order_actions_router
)  # handles acting upon that orders like acc / rej
app.include_router(realtime.router)
app.include_router(notifications.router)
app.include_router(locations.router)
app.include_router(customer_orders.router)
app.include_router(rider_applications.router)
app.include_router(admmin_rider_application.admin_router)
app.include_router(riders.router)

from app.modules.reviews.router import my_reviews_router, public_router
from app.modules.reviews.router import router as review_router

app.include_router(review_router, prefix="/api")
app.include_router(my_reviews_router, prefix="/api")
app.include_router(public_router, prefix="/api")
app.include_router(payout_router.router)