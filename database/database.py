from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Primero usaremos SQLite para emular la actual 'prode.db'
# Cuando se migre a producción, esto se cambia por una URL PostgreSQL
# ej: SQLALCHEMY_DATABASE_URL = "postgresql://user:password@postgresserver/db"
SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

# connect_args solo necesario para SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependencia para inyectar en las rutas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
