from sqlalchemy import Boolean, Column, Integer, String
from .database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    is_admin = Column(Boolean, default=False)
    puntos_totales = Column(Integer, default=0)

class Prediccion(Base):
    __tablename__ = "predicciones"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True)
    datos = Column(String) # Guardaremos el JSON serializado por ahora para migrar rápido

class ConfigGlobal(Base):
    __tablename__ = "config_global"

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String, unique=True, index=True)
    valor = Column(String) # JSON serializado (ej: el estado de las fases)

class DatosOficiales(Base):
    __tablename__ = "datos_oficiales"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String, unique=True, index=True)
    datos = Column(String) # Goles, ganador, penales, etc.
