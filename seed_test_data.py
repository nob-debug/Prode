import json
import random
from sqlalchemy.orm import Session
from database.database import SessionLocal
from database.models import DatosOficiales, Prediccion, Usuario
from core.constantes import GRUPOS, KNOCKOUT
from core.scoring import ScoringEngine

def seed_random_data():
    db = SessionLocal()
    try:
        # 1. Limpiar o asegurar resultados oficiales para grupos
        print("Generando resultados oficiales aleatorios para grupos...")
        all_group_match_ids = []
        for g_name, matches in GRUPOS.items():
            for m in matches:
                m_id = m['id']
                all_group_match_ids.append(m_id)
                oficial = db.query(DatosOficiales).filter(DatosOficiales.match_id == m_id).first()
                if not oficial:
                    oficial = DatosOficiales(match_id=m_id)
                    db.add(oficial)
                
                # Resultado aleatorio entre 0 y 3
                g1, g2 = random.randint(0, 3), random.randint(0, 3)
                oficial.datos = json.dumps({"g1": g1, "g2": g2, "winner": None})
        
        # 2. Asegurar que pepe tenga predicciones
        pepe = db.query(Usuario).filter(Usuario.username == "pepe").first()
        if not pepe:
            pepe = Usuario(username="pepe", password="password", puntos_totales=0)
            db.add(pepe)
            db.commit()

        pred_pepe = db.query(Prediccion).filter(Prediccion.username == "pepe").first()
        if not pred_pepe:
            pred_pepe = Prediccion(username="pepe", datos="{}")
            db.add(pred_pepe)
        
        pepe_data = {}
        target_pts = 50
        current_pts = 0
        
        # 3. Forzar algunas predicciones de pepe para llegar a ~50 puntos
        # Reglas: Exacto = 6, Tendencia = 3
        print("Ajustando predicciones de 'pepe' para alcanzar ~50 puntos...")
        
        # Obtenemos los resultados que acabamos de setear
        db.commit() # Guardamos los oficiales primero
        
        for m_id in all_group_match_ids:
            oficial = db.query(DatosOficiales).filter(DatosOficiales.match_id == m_id).first()
            off_res = json.loads(oficial.datos)
            o_g1, o_g2 = off_res['g1'], off_res['g2']
            
            if current_pts < target_pts:
                # Hacer que coincida exactamente (6 pts)
                pepe_data[f"{m_id}_g1"] = o_g1
                pepe_data[f"{m_id}_g2"] = o_g2
                current_pts += 6
            else:
                # Fallar totalmente
                pepe_data[f"{m_id}_g1"] = o_g1 + 5
                pepe_data[f"{m_id}_g2"] = o_g2 + 5
        
        pred_pepe.datos = json.dumps(pepe_data)
        db.commit()
        
        # 4. Recalcular todo
        print("Recalculando puntajes...")
        engine = ScoringEngine()
        engine.recalcular_todo(db)
        
        pepe_final = db.query(Usuario).filter(Usuario.username == "pepe").first()
        print(f"Finalizado. El usuario 'pepe' ahora tiene {pepe_final.puntos_totales} puntos.")

    finally:
        db.close()

if __name__ == "__main__":
    seed_random_data()
