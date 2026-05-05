from database.session import SessionLocal
from database.models import ConfigGlobal, Prediccion
from core.scoring import ScoringEngine
import json

db = SessionLocal()

match_id = "1" # Dinamarca vs Mexico might not be id 1, but lets just use any group match
conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
partidos_cerrados = json.loads(conf_cerrados.valor) if conf_cerrados else []

engine = ScoringEngine()
phase_internal = engine.match_phases.get(match_id, 'group')

PHASE_MAP = {
    'group': 'Grupos',
    'round_of_32': 'Dieciseisavos',
    'round_of_16': 'Octavos',
    'quarter': 'Cuartos',
    'semi': 'Semis',
    'third_place': 'Finales',
    'final': 'Finales'
}
phase_display = PHASE_MAP.get(phase_internal, 'Grupos')

conf_fases = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "fases_estado").first()
fases_estado = json.loads(conf_fases.valor) if conf_fases else {}

fase_activa = fases_estado.get(phase_display, True if phase_display == "Grupos" else False)

print(f"match_id: {match_id}")
print(f"phase_internal: {phase_internal}")
print(f"phase_display: {phase_display}")
print(f"fases_estado: {fases_estado}")
print(f"fase_activa: {fase_activa}")

