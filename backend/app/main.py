from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import companies, health, search, users

app = FastAPI(
    title="BigSpring Search Engine",
    description="Secure multi-tenant enterprise search engine for sales training",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(companies.router, tags=["companies"])
app.include_router(users.router, tags=["users"])
app.include_router(search.router, tags=["search"])
