import json
import random
from sqlalchemy.orm import Session
from database.database import SessionLocal
from database.models import DatosOficiales, Prediccion, Usuario, ConfigGlobal
from core.constantes import KNOCKOUT, ESTRUCTURA_MUNDIAL_2026, COUNTRIES
from core.scoring import ScoringEngine

def get_flag(team_name):
    for c in COUNTRIES:
        if c['name'] == team_name:
            return c['flag']
    return "🏳️"

def simulate_round(phase_name="Dieciseisavos", pepe_hit_rate=0.10):
    db = SessionLocal()
    try:
        print(f"--- Simulando Fase: {phase_name} ---")
        
        # 1. Obtener partidos de la fase
        matches_in_phase = [m for m in KNOCKOUT if m['phase'] == phase_name]
        match_ids = [m['id'] for m in matches_in_phase]
        
        # 2. Cargar asignaciones actuales (para saber quién juega)
        conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        if not conf_asig:
            print("❌ No hay equipos asignados a eliminatorias todavía.")
            return
        asignaciones = json.loads(conf_asig.valor)
        
        # Verificar que todos los partidos de la fase tengan equipos
        for m_id in match_ids:
            if m_id not in asignaciones:
                print(f"❌ Falta asignar equipos para el partido {m_id}.")
                return
                
        # 3. Generar Resultados Oficiales
        print("Generando resultados oficiales...")
        for m_id in match_ids:
            g1, g2 = random.randint(0, 3), random.randint(0, 3)
            winner = None
            if g1 == g2:
                # En eliminatorias, el empate exige penales
                t1 = asignaciones[m_id]['t1']
                t2 = asignaciones[m_id]['t2']
                winner = t1 if random.random() < 0.5 else t2
            
            oficial = db.query(DatosOficiales).filter(DatosOficiales.match_id == m_id).first()
            oficial_data = {"g1": g1, "g2": g2, "winner": winner}
            if oficial:
                oficial.datos = json.dumps(oficial_data)
            else:
                db.add(DatosOficiales(match_id=m_id, datos=json.dumps(oficial_data)))
                
        # Cerrar partidos
        conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
        cerrados = json.loads(conf_cerrados.valor) if conf_cerrados else []
        for m_id in match_ids:
            if m_id not in cerrados:
                cerrados.append(m_id)
        if not conf_cerrados:
            db.add(ConfigGlobal(clave="partidos_cerrados", valor=json.dumps(cerrados)))
        else:
            conf_cerrados.valor = json.dumps(cerrados)
            
        db.commit()

        # 4. Generar Predicciones para Pepe
        print(f"Generando predicciones de 'pepe' ({pepe_hit_rate*100}% acierto)...")
        pepe_pred_obj = db.query(Prediccion).filter(Prediccion.username == "pepe").first()
        pepe_preds = json.loads(pepe_pred_obj.datos) if pepe_pred_obj and pepe_pred_obj.datos else {}
        
        resultados_oficiales = {r.match_id: json.loads(r.datos) for r in db.query(DatosOficiales).all()}
        exact_hits = 0
        
        for m_id in match_ids:
            off = resultados_oficiales[m_id]
            o_g1, o_g2, o_winner = off['g1'], off['g2'], off.get('winner')
            t1 = asignaciones[m_id]['t1']
            t2 = asignaciones[m_id]['t2']
            
            if random.random() < pepe_hit_rate:
                p_g1, p_g2 = o_g1, o_g2
                exact_hits += 1
                if o_g1 == o_g2:
                    pepe_preds[f"{m_id}_penales"] = o_winner
            else:
                p_g1, p_g2 = random.randint(0, 4), random.randint(0, 4)
                while p_g1 == o_g1 and p_g2 == o_g2:
                    p_g1, p_g2 = random.randint(0, 4), random.randint(0, 4)
                
                if p_g1 == p_g2:
                    pepe_preds[f"{m_id}_penales"] = t1 if random.random() < 0.5 else t2
            
            pepe_preds[f"{m_id}_g1"] = p_g1
            pepe_preds[f"{m_id}_g2"] = p_g2
            
        pepe_pred_obj.datos = json.dumps(pepe_preds)
        db.commit()

        # 5. Propagar Ganadores a la siguiente fase (Octavos)
        print("Propagando ganadores a la siguiente fase...")
        for m_id in match_ids:
            off = resultados_oficiales[m_id]
            o_g1, o_g2, o_winner = off['g1'], off['g2'], off.get('winner')
            
            # Quién avanzó?
            if o_g1 > o_g2:
                advancing_team = asignaciones[m_id]['t1']
            elif o_g2 > o_g1:
                advancing_team = asignaciones[m_id]['t2']
            else:
                advancing_team = o_winner
                
            # A dónde va?
            estructura = ESTRUCTURA_MUNDIAL_2026.get(m_id)
            if estructura and estructura['destino']:
                dest_id = estructura['destino']
                pos = estructura['pos_destino'] # 0 es t1, 1 es t2
                
                if dest_id not in asignaciones:
                    asignaciones[dest_id] = {}
                    
                if pos == 0:
                    asignaciones[dest_id]['t1'] = advancing_team
                    asignaciones[dest_id]['bandera1'] = get_flag(advancing_team)
                else:
                    asignaciones[dest_id]['t2'] = advancing_team
                    asignaciones[dest_id]['bandera2'] = get_flag(advancing_team)

        # Guardar nuevas asignaciones (Octavos)
        conf_asig.valor = json.dumps(asignaciones)
        db.commit()

        # 6. Recalcular Puntajes
        print("Recalculando puntajes...")
        engine = ScoringEngine()
        engine.recalcular_todo(db)
        
        pepe_final = db.query(Usuario).filter(Usuario.username == "pepe").first()
        print(f"✅ Simulación completada para {phase_name}.")
        print(f"Aciertos exactos de Pepe: {exact_hits}/{len(match_ids)}")
        print(f"Puntaje total de Pepe: {pepe_final.puntos_totales}")
        print("Los ganadores han sido asignados a Octavos.")

    finally:
        db.close()

if __name__ == "__main__":
    simulate_round("Octavos", 0.10)
