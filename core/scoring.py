import json
import os
from sqlalchemy.orm import Session
from database.models import Usuario, Prediccion, DatosOficiales
from core.constantes import GRUPOS, KNOCKOUT

CONFIG_FILE = "torneo_config.json"

class ScoringEngine:
    def __init__(self, config_path=CONFIG_FILE):
        self.config = self._load_config(config_path)
        self.rules = self.config.get("scoring_rules", {})
        self.multipliers = self.config.get("phase_multipliers", {})
        # Construir un mapa rápido de todos los partidos para saber a qué fase pertenecen
        self.match_phases = {}
        for g, partidos in GRUPOS.items():
            for p in partidos:
                self.match_phases[p['id']] = 'group'
        
        for p in KNOCKOUT:
            phase_raw = p.get('phase', '').lower()
            if 'dieciseisavos' in phase_raw:
                phase_id = 'round_of_32'
            elif 'octavos' in phase_raw:
                phase_id = 'round_of_16'
            elif 'cuartos' in phase_raw:
                phase_id = 'quarter'
            elif 'semifinal' in phase_raw:
                phase_id = 'semi'
            elif 'tercer' in phase_raw:
                phase_id = 'third_place'
            elif 'final' in phase_raw:
                phase_id = 'final'
            else:
                phase_id = 'knockout'
            
            self.match_phases[p['id']] = phase_id

    def _load_config(self, path):
        # Como estamos en ProdeFastAPI/core, el archivo torneo_config puede estar un nivel arriba
        parent_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", path)
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        
        load_path = local_path if os.path.exists(local_path) else (parent_path if os.path.exists(parent_path) else None)
        
        if load_path:
            try:
                with open(load_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error cargando config {load_path}: {e}")
        return {
            "scoring_rules": {
                "exact_score": 6,
                "winner_only": 3,
                "penalty_bonus": 1
            },
            "phase_multipliers": {
                "group": 1.0, "round_of_32": 1.25, "round_of_16": 1.5,
                "quarter": 2.0, "semi": 3.0, "third_place": 2.0, "final": 4.0
            }
        }

    def recalcular_todo(self, db: Session):
        """
        Itera sobre todos los usuarios, cruza sus predicciones JSON con los DatosOficiales JSON
        y actualiza su columna puntos_totales.
        """
        # 1. Cargar todos los resultados oficiales
        resultados_raw = db.query(DatosOficiales).all()
        resultados = {}
        for r in resultados_raw:
            try:
                resultados[r.match_id] = json.loads(r.datos)
            except:
                pass

        if not resultados:
            # Si no hay resultados oficiales todavía, todos tienen 0 puntos.
            db.query(Usuario).update({"puntos_totales": 0})
            db.commit()
            return
            
        # 2. Cargar todos los usuarios y sus predicciones
        usuarios = db.query(Usuario).all()
        for usuario in usuarios:
            puntos_usuario = 0
            
            # Buscar su prediccion unica
            pred = db.query(Prediccion).filter(Prediccion.username == usuario.username).first()
            if pred and pred.datos:
                try:
                    datos_prediccion = json.loads(pred.datos)
                except:
                    datos_prediccion = {}
                
                # Para cada partido oficial, chequear si el usuario lo predijo
                for match_id, off_data in resultados.items():
                    puntos_partido = self._calcular_partido(match_id, datos_prediccion, off_data)
                    puntos_usuario += puntos_partido
            
            # 3. Guardar puntos totales en usuario
            usuario.puntos_totales = puntos_usuario
        
        db.commit()

    def _calcular_partido(self, match_id: str, preds: dict, oficial: dict) -> int:
        """Compara un partido individual y devuelve los puntos."""
        off_g1 = oficial.get("g1")
        off_g2 = oficial.get("g2")
        off_winner = oficial.get("winner")

        if off_g1 is None or off_g2 is None:
            return 0 # Si falta resultado oficial de goles, no hay puntos

        # Obtener prediccion del usuario
        pred_g1 = preds.get(f"{match_id}_g1")
        pred_g2 = preds.get(f"{match_id}_g2")
        pred_winner = preds.get(f"{match_id}_penales")

        # Si el usuario no ingresó absolutamente nada
        if (pred_g1 is None or str(pred_g1).strip() == "") and (pred_g2 is None or str(pred_g2).strip() == "") and not pred_winner:
            return 0
            
        # Quizás solo evaluó ganador en penales y dejó los goles vacíos
        if (pred_g1 is None or str(pred_g1).strip() == "") and (pred_g2 is None or str(pred_g2).strip() == ""):
            if pred_winner and pred_winner == off_winner:
               phase = self.match_phases.get(match_id, 'group')
               mult = self.multipliers.get(phase, 1.0)
               return int(self.rules.get("winner_only", 3) * mult)
            return 0
            
        try:
            o_g1 = int(off_g1)
            o_g2 = int(off_g2)
            p_g1 = int(pred_g1)
            p_g2 = int(pred_g2)
        except (ValueError, TypeError):
            # Si hay algún error casteando, tal vez pusieron letras en vez de números. 
            # Pero si le atinaron al ganador, les damos esos puntos al menos.
            if pred_winner and pred_winner == off_winner:
               phase = self.match_phases.get(match_id, 'group')
               mult = self.multipliers.get(phase, 1.0)
               return int(self.rules.get("winner_only", 3) * mult)
            return 0

        # Lógica de Marcador
        base_points = 0
        real_winner_str = self._get_winner_str(o_g1, o_g2)
        pred_winner_str = self._get_winner_str(p_g1, p_g2)

        is_exact = (o_g1 == p_g1 and o_g2 == p_g2)
        is_tie = (real_winner_str == "draw")

        if real_winner_str == pred_winner_str:
            if is_exact:
                base_points = self.rules.get("exact_score", 6)
                if is_tie and pred_winner and off_winner and pred_winner == off_winner:
                    base_points += self.rules.get("penalty_bonus", 1)
            else:
                base_points = self.rules.get("winner_only", 3)

        # Multiplicador Fase
        phase = self.match_phases.get(match_id, 'group')
        multiplier = self.multipliers.get(phase, 1.0)
        
        return int(base_points * multiplier)

    def _get_winner_str(self, g1, g2):
        if g1 > g2: return "home"
        if g2 > g1: return "away"
        return "draw"
