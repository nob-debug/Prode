import json
import random
from sqlalchemy.orm import Session
from database.database import SessionLocal, engine, Base
from database.models import DatosOficiales, Prediccion, Usuario, ConfigGlobal
from core.constantes import GRUPOS, KNOCKOUT
from core.scoring import ScoringEngine

def reset_and_seed():
    # 1. Recrear tablas (Reset total)
    print("Reseteando base de datos...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 2. Re-crear usuarios básicos
        print("Creando usuarios 'admin' y 'pepe'...")
        admin = Usuario(username="admin", password="admin123", is_admin=True, puntos_totales=0)
        pepe = Usuario(username="pepe", password="golazo2026", is_admin=False, puntos_totales=0)
        db.add_all([admin, pepe])
        db.commit()

        # 3. Inicializar ConfigGlobal
        print("Inicializando configuraciones globales...")
        estados_fases = {"Grupos": True, "Dieciseisavos": True, "Octavos": True, "Cuartos": True, "Semis": True, "Finales": True}
        db.add(ConfigGlobal(clave="fases_estado", valor=json.dumps(estados_fases)))
        
        # 4. Generar resultados oficiales aleatorios para todos los grupos (Admin)
        print("Generando resultados oficiales aleatorios para los 12 grupos...")
        all_group_matches = []
        for g_name, matches in GRUPOS.items():
            for m in matches:
                m_id = m['id']
                all_group_matches.append(m_id)
                g1, g2 = random.randint(0, 4), random.randint(0, 4)
                
                winner = None
                if g1 == g2:
                    # En fase de grupos no suele haber penales, pero para el test el usuario los pide
                    winner = m['t1'] if random.random() < 0.5 else m['t2']
                
                db.add(DatosOficiales(match_id=m_id, datos=json.dumps({"g1": g1, "g2": g2, "winner": winner})))
        
        # Cerrar todos los partidos de grupos para que se vean los puntos
        db.add(ConfigGlobal(clave="partidos_cerrados", valor=json.dumps(all_group_matches)))
        db.commit()

        # 5. Generar predicciones para 'pepe' (20% aciertos exactos, 10% aciertos penales en empates)
        print("Generando predicciones para 'pepe' (20% exactos, 10% ganador penales en empates)...")
        pepe_preds = {}
        exact_hits = 0
        penalty_hits = 0
        draw_count = 0
        total_matches = len(all_group_matches)
        
        resultados_oficiales = {r.match_id: json.loads(r.datos) for r in db.query(DatosOficiales).all()}
        
        for m_id in all_group_matches:
            off = resultados_oficiales[m_id]
            o_g1, o_g2 = off['g1'], off['g2']
            o_winner = off['winner']
            
            # Buscar t1/t2 originales de las constantes
            m_const = None
            for g_name, matches in GRUPOS.items():
                for match in matches:
                    if match['id'] == m_id:
                        m_const = match
                        break
            
            t1, t2 = m_const['t1'], m_const['t2']

            if random.random() < 0.20:
                # Acierto exacto de goles
                p_g1, p_g2 = o_g1, o_g2
                exact_hits += 1
            else:
                p_g1, p_g2 = random.randint(0, 4), random.randint(0, 4)
                while p_g1 == o_g1 and p_g2 == o_g2:
                    p_g1, p_g2 = random.randint(0, 4), random.randint(0, 4)
            
            pepe_preds[f"{m_id}_g1"] = p_g1
            pepe_preds[f"{m_id}_g2"] = p_g2

            # Lógica de penales si el resultado oficial es empate
            if o_g1 == o_g2:
                draw_count += 1
                if random.random() < 0.10:
                    pepe_preds[f"{m_id}_penales"] = o_winner
                    penalty_hits += 1
                else:
                    pepe_preds[f"{m_id}_penales"] = t2 if o_winner == t1 else t1
            elif p_g1 == p_g2:
                # Predijo empate pero no fue oficial, elegir uno random para que no quede nulo
                pepe_preds[f"{m_id}_penales"] = t1 if random.random() < 0.5 else t2
        
        db.add(Prediccion(username="pepe", datos=json.dumps(pepe_preds)))
        db.commit()

        # 6. Recalcular puntajes
        print("Ejecutando Scoring Engine...")
        scoring_engine = ScoringEngine()
        scoring_engine.recalcular_todo(db)
        
        # 7. Resumen
        pepe_final = db.query(Usuario).filter(Usuario.username == "pepe").first()
        print(f"--- RESUMEN DEL TEST ---")
        print(f"Total partidos procesados: {total_matches}")
        print(f"Aciertos exactos de Pepe: {exact_hits} ({round(exact_hits/total_matches*100, 1)}%)")
        print(f"Empates encontrados: {draw_count}")
        print(f"Aciertos de Pepe en penales: {penalty_hits}")
        print(f"Puntaje total final de Pepe: {pepe_final.puntos_totales}")
        print(f"Base de datos lista.")

    finally:
        db.close()

if __name__ == "__main__":
    reset_and_seed()
