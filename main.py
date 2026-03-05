import os
from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database.database import Base, engine, get_db

import routers.admin as admin_router
import routers.users as users_router
import routers.auth as auth_router

# Crear las tablas en la base de datos local (SQLite para empezar)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Mundial API", description="Prode Mundial Backend")

# Rutas estáticas (CSS, JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Plantillas HTML
templates = Jinja2Templates(directory="templates")

# Incluir Routers
app.include_router(auth_router.router, tags=["Auth"])
app.include_router(admin_router.router, prefix="/admin", tags=["Admin"])
app.include_router(users_router.router, tags=["Users"])
