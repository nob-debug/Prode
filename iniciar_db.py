import os
import sys

# Asegurarse de que ProdeFastAPI esté en el path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal, engine, Base
from database.models import Usuario

# Asegurar tablas creadas
Base.metadata.create_all(bind=engine)

def init_db():
    db = SessionLocal()
    try:
        # Verificar y crear usuario normal
        pepe = db.query(Usuario).filter(Usuario.username == "pepe").first()
        if not pepe:
            pepe = Usuario(username="pepe", password="golazo2026", is_admin=False)
            db.add(pepe)
            print("Usuario 'pepe' creado exitosamente.")
        else:
            print("Usuario 'pepe' ya existe.")

        # Verificar y crear admin
        admin = db.query(Usuario).filter(Usuario.username == "admin").first()
        if not admin:
            admin = Usuario(username="admin", password="admin123", is_admin=True)
            db.add(admin)
            print("Administrador 'admin' creado exitosamente.")
        else:
            print("Administrador 'admin' ya existe.")
            
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
