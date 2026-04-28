"""REST routers grouped by backend resource."""

from glucotracker.api.routers.admin import router as admin_router
from glucotracker.api.routers.autocomplete import router as autocomplete_router
from glucotracker.api.routers.dashboard import router as dashboard_router
from glucotracker.api.routers.database import router as database_router
from glucotracker.api.routers.meals import router as meals_router
from glucotracker.api.routers.nightscout import router as nightscout_router
from glucotracker.api.routers.nutrients import router as nutrients_router
from glucotracker.api.routers.patterns import router as patterns_router
from glucotracker.api.routers.photos import router as photos_router
from glucotracker.api.routers.products import router as products_router

__all__ = [
    "admin_router",
    "autocomplete_router",
    "dashboard_router",
    "database_router",
    "meals_router",
    "nightscout_router",
    "nutrients_router",
    "patterns_router",
    "photos_router",
    "products_router",
]
