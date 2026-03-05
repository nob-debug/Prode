import json
from functools import cmp_to_key
from database.database import SessionLocal
from database.models import DatosOficiales, ConfigGlobal
from core.constantes import GRUPOS, KNOCKOUT, COUNTRIES

def get_flag(team_name):
    for c in COUNTRIES:
        if c['name'] == team_name:
            return c['flag']
    return "🏳️"

def auto_assign():
    db = SessionLocal()
    try:
        print("Cargando resultados oficiales y calculando clasificaciones...")
        resultados_oficiales = {r.match_id: json.loads(r.datos) for r in db.query(DatosOficiales).all()}
        
        group_standings = {}
        third_places = []
        
        for g_name, matches in GRUPOS.items():
            group_letter = g_name.replace("GRUPO ", "")
            teams = set()
            sim_matches = []
            for m in matches:
                teams.add(m['t1'])
                teams.add(m['t2'])
                res = resultados_oficiales.get(m['id'])
                if res and res.get('g1') is not None:
                    sim_matches.append({'t1': m['t1'], 't2': m['t2'], 'g1': res['g1'], 'g2': res['g2']})
            
            stats = {t: {'pts': 0, 'gf': 0, 'gc': 0, 'gd': 0, 'name': t, 'group': group_letter} for t in teams}
            for m in sim_matches:
                g1, g2 = m['g1'], m['g2']
                if g1 > g2: stats[m['t1']]['pts'] += 3
                elif g2 > g1: stats[m['t2']]['pts'] += 3
                else:
                    stats[m['t1']]['pts'] += 1
                    stats[m['t2']]['pts'] += 1
                stats[m['t1']]['gf'] += g1
                stats[m['t1']]['gc'] += g2
                stats[m['t2']]['gf'] += g2
                stats[m['t2']]['gc'] += g1
                
            for t in stats.values():
                t['gd'] = t['gf'] - t['gc']
                
            def compare(tA, tB):
                # 1. Mayor cantidad de puntos
                if tA['pts'] != tB['pts']: return tB['pts'] - tA['pts']
                # 2. Duelo directo (H2H)
                h2h_match = next((m for m in sim_matches if (m['t1'] == tA['name'] and m['t2'] == tB['name']) or (m['t1'] == tB['name'] and m['t2'] == tA['name'])), None)
                if h2h_match:
                    gA = h2h_match['g1'] if h2h_match['t1'] == tA['name'] else h2h_match['g2']
                    gB = h2h_match['g2'] if h2h_match['t1'] == tA['name'] else h2h_match['g1']
                    if gA != gB: return gB - gA
                # 3. Diferencia de goles
                if tA['gd'] != tB['gd']: return tB['gd'] - tA['gd']
                # 4. Goles a favor
                if tA['gf'] != tB['gf']: return tB['gf'] - tA['gf']
                return 0 # Si sigue empatado (raro pero posible), mantiene el orden
                
            sorted_teams = sorted(stats.values(), key=cmp_to_key(compare))
            group_standings[group_letter] = sorted_teams
            
            # Guardamos el 3er puesto para la tabla de mejores terceros
            if len(sorted_teams) >= 3:
                third_places.append(sorted_teams[2])
            
        print("Clasificando a los 8 mejores terceros...")
        # Ordenar mejores terceros (Puntos, DG, GF)
        def compare_thirds(tA, tB):
            if tA['pts'] != tB['pts']: return tB['pts'] - tA['pts']
            if tA['gd'] != tB['gd']: return tB['gd'] - tA['gd']
            if tA['gf'] != tB['gf']: return tB['gf'] - tA['gf']
            return 0
            
        third_places = sorted(third_places, key=cmp_to_key(compare_thirds))
        top_8_thirds = third_places[:8]
        
        print(f"Mejores 8 terceros seleccionados: {[t['name'] + ' (' + str(t['pts']) + 'pts)' for t in top_8_thirds]}")
        
        # Mapeando clasificados
        allocations = {}
        for letter, std in group_standings.items():
            if len(std) >= 2:
                allocations[f"1º Grupo {letter}"] = std[0]['name']
                allocations[f"2º Grupo {letter}"] = std[1]['name']
            
        available_thirds = top_8_thirds.copy()
        knockout_asignaciones = {}
        
        print("Asignando equipos a los Dieciseisavos...")
        for k_match in KNOCKOUT[:16]: # Solo Dieciseisavos (P73 a P88)
            desc = k_match['desc']
            parts = desc.split(' v ')
            if len(parts) == 2:
                p1_desc, p2_desc = parts[0], parts[1]
                
                # Función auxiliar para resolver el slot
                def resolve_slot(str_desc):
                    val = allocations.get(str_desc)
                    if val: return val
                    if str_desc.startswith("3º"):
                        allowed_groups = str_desc.replace("3º Grupo ", "").split("/")
                        for i, t in enumerate(available_thirds):
                            if t['group'] in allowed_groups:
                                t_name = t['name']
                                available_thirds.pop(i)
                                return t_name
                    # Fallback aleatorio de terceros si no cuadra exactamente por el "sistema heurístico simple"
                    if str_desc.startswith("3º") and available_thirds:
                        t_name = available_thirds[0]['name']
                        available_thirds.pop(0)
                        return t_name
                    return "TBD"
                
                t1_name = resolve_slot(p1_desc)
                t2_name = resolve_slot(p2_desc)
                            
                if t1_name != "TBD" and t2_name != "TBD":
                    knockout_asignaciones[k_match['id']] = {
                        "t1": t1_name, "bandera1": get_flag(t1_name),
                        "t2": t2_name, "bandera2": get_flag(t2_name)
                    }

        # Guardar en la base de datos (ConfigGlobal)
        conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        if not conf_asig:
            conf_asig = ConfigGlobal(clave="knockout_asignaciones", valor=json.dumps(knockout_asignaciones))
            db.add(conf_asig)
        else:
            # Mantener las que ya existan en octavos u otras fases, aunque aquí reseteamos los dieciseisavos
            actual = json.loads(conf_asig.valor)
            actual.update(knockout_asignaciones)
            conf_asig.valor = json.dumps(actual)
            
        db.commit()
        print(f"✅ Se han asignado {len(knockout_asignaciones)} partidos de Dieciseisavos automáticamente.")
        
    finally:
        db.close()

if __name__ == "__main__":
    auto_assign()
