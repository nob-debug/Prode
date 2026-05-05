from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from database.database import get_db
from core.constantes import GRUPOS, KNOCKOUT
import datetime

from routers.auth import get_current_user
from database.models import Prediccion, Usuario, ConfigGlobal
import json
from fastapi.responses import RedirectResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def get_sidebar_data(username: str, db: Session):
    user = db.query(Usuario).filter(Usuario.username == username).first()
    if not user:
        return {"puntos": 0, "posicion": "-"}
    puntos = user.puntos_totales or 0
    # Posición es cuántos usuarios tienen estrictamente más puntos + 1
    higher = db.query(Usuario).filter(Usuario.puntos_totales > puntos).count()
    return {"puntos": puntos, "posicion": higher + 1}

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Renderiza la vista principal del usuario con los grupos y partidos."""
    
    # Verificación de Autenticación
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
        
    # --- LOGICA DEL BANNER CRAWLER ---
    hoy_dt = datetime.datetime.now()
    if hoy_dt.year != 2026 or hoy_dt.month != 6:
        hoy_str = "11/06"
    else:
        hoy_str = hoy_dt.strftime("%d/%m")

    partidos_ticker = []
    
    for g, lista in GRUPOS.items():
        for p in lista:
            if p['fecha'].startswith(hoy_str):
                p_copy = dict(p)
                p_copy['cat_label'] = g
                partidos_ticker.append(p_copy)
    
    for p in KNOCKOUT:
        if p['fecha'].startswith(hoy_str):
            p_copy = dict(p)
            p_copy['cat_label'] = p.get('phase', 'ELIMINATORIA').upper()
            partidos_ticker.append(p_copy)

    def sort_key(partido):
        f = partido['fecha']
        parts = f.split(" ")
        dia_mes = parts[0].split("/")
        orden_dia = int(dia_mes[1]) * 100 + int(dia_mes[0])
        orden_hora = parts[1] if len(parts) > 1 else "00:00"
        return (orden_dia, orden_hora)

    partidos_ticker.sort(key=sort_key)
    
    crawler_items = []
    for p in partidos_ticker:
        t1 = p.get('t1') or "TBD"
        t2 = p.get('t2') or "TBD"
        desc_match = p['desc'] if (t1 == "TBD" and "desc" in p) else f"{t1} vs {t2}"
        cat = p.get('cat_label', '')
        txt = f'<span class="crawler-alert">ALERTA {cat}</span> {desc_match} Juega (HOY)'
        crawler_items.append(txt)

    separador = ' <span class="crawler-separator"> - </span> '
    crawling_text = separador.join(crawler_items) if crawler_items else ""
    if crawling_text:
        crawling_text = crawling_text + separador + crawling_text

    # Extraer las predicciones previas del usuario desde la base de datos
    user_preds = db.query(Prediccion).filter(Prediccion.username == username).first()
    datos_actuales = json.loads(user_preds.datos) if user_preds and user_preds.datos else {}

    # Cargar estado de fases y partidos cerrados desde la BD
    from database.models import ConfigGlobal
    conf_fases = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "fases_estado").first()
    if not conf_fases:
        estados_fases = {"Grupos": True, "Dieciseisavos": False, "Octavos": False, "Cuartos": False, "Semis": False, "Finales": False}
        nueva_conf = ConfigGlobal(clave="fases_estado", valor=json.dumps(estados_fases))
        db.add(nueva_conf)
        db.commit()
    else:
        estados_fases = json.loads(conf_fases.valor)

    conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
    partidos_cerrados = json.loads(conf_cerrados.valor) if conf_cerrados else []

    conf_torneo = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "torneo_finalizado").first()
    torneo_finalizado = json.loads(conf_torneo.valor) if conf_torneo else False

    # Datos para reclamar premios si el torneo terminó
    from database.models import Premio, ReclamoPremio
    reclamo_actual = None
    premios_elegibles = []
    
    sidebar = get_sidebar_data(username, db)
    posicion_actual = sidebar["posicion"]
    
    if torneo_finalizado:
        reclamo_actual = db.query(ReclamoPremio).filter(ReclamoPremio.username == username).first()
        if reclamo_actual:
            # Conseguimos el objeto de premio que reclamo
            premio_obj = db.query(Premio).filter(Premio.id == reclamo_actual.premio_id).first()
            if premio_obj:
                setattr(reclamo_actual, 'premio_obj', premio_obj)
            else:
                class DummyPremio:
                    nombre = "Premio Eliminado por el Admin"
                setattr(reclamo_actual, 'premio_obj', DummyPremio())
        else:
            # Buscar premios elegibles buscando coincidencia exacta de orden vs posicion
            premios_elegibles = db.query(Premio).filter(Premio.orden == posicion_actual).all()
            
            # Si no hay premios específicos asignados a esta posición, darle premios de consuelo (orden == 0)
            if not premios_elegibles:
                premios_elegibles = db.query(Premio).filter(Premio.orden == 0).all()

    # Agrupar partidos KNOCKOUT por fase
    # Extraer asignaciones de equipos para knockout
    conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
    knockout_asignaciones = json.loads(conf_asig.valor) if conf_asig else {}

    # Agrupar partidos KNOCKOUT por fase e inyectar equipos dinámicos
    knockout_por_fase = {}
    for p in KNOCKOUT:
        m_id = p['id']
        asig = knockout_asignaciones.get(m_id)
        p_copy = dict(p)
        if asig:
            p_copy['t1'] = asig['t1']
            p_copy['bandera1'] = asig['bandera1']
            p_copy['t2'] = asig['t2']
            p_copy['bandera2'] = asig['bandera2']
        else:
            p_copy['t1'] = "TBD"
            p_copy['bandera1'] = "🏴"
            p_copy['t2'] = "TBD"
            p_copy['bandera2'] = "🏴"
            
        fase = p_copy.get('phase', 'Eliminatorias')
        if fase not in knockout_por_fase:
            knockout_por_fase[fase] = []
        knockout_por_fase[fase].append(p_copy)

    # Agrupar GRUPOS por fecha
    partidos_por_fecha = {}
    for g_name, lista in GRUPOS.items():
        for p in lista:
            dia = p['fecha'].split(" ")[0]
            if dia not in partidos_por_fecha:
                partidos_por_fecha[dia] = []
            p_copy = dict(p)
            p_copy['grupo'] = g_name
            partidos_por_fecha[dia].append(p_copy)
            
    def sort_fecha(dia_str):
        parts = dia_str.split("/")
        if len(parts) == 2:
            return int(parts[1]) * 100 + int(parts[0])
        return 9999
        
    fechas_ordenadas = sorted(partidos_por_fecha.keys(), key=sort_fecha)
    partidos_agrupados_fecha = {}
    for f in fechas_ordenadas:
        partidos_agrupados_fecha[f] = sorted(partidos_por_fecha[f], key=lambda x: x['fecha'].split(" ")[1] if " " in x['fecha'] else "00:00")

    # Extraer los resultados ya cargados por el admin
    from database.models import DatosOficiales
    from core.scoring import ScoringEngine

    resultados_raw = db.query(DatosOficiales).all()
    resultados_dict = {}
    for r in resultados_raw:
        try:
            resultados_dict[r.match_id] = json.loads(r.datos)
        except:
            pass

    engine = ScoringEngine()
    puntos_por_partido = {}

    for f_name, lista_partidos in partidos_agrupados_fecha.items():
        for p in lista_partidos:
            m_id = p['id']
            off_data = resultados_dict.get(m_id)
            if m_id in partidos_cerrados and off_data and off_data.get("g1") is not None:
                pts = engine._calcular_partido(m_id, datos_actuales, off_data)
                
                real_winner_str = engine._get_winner_str(off_data.get("g1"), off_data.get("g2"))
                is_tie = (real_winner_str == "draw")
                
                base_max = engine.rules.get("exact_score", 6)
                if is_tie and off_data.get("winner"):
                    base_max += engine.rules.get("penalty_bonus", 1)
                    
                phase = engine.match_phases.get(m_id, 'group')
                mult = engine.multipliers.get(phase, 1.0)
                max_possible = int(base_max * mult)
                
                puntos_por_partido[m_id] = {
                    "pts": pts,
                    "is_max": pts == max_possible
                }

    return templates.TemplateResponse("index.html", {
        "request": request,
        "grupos": GRUPOS,
        "partidos_agrupados_fecha": partidos_agrupados_fecha,
        "knockout_por_fase": knockout_por_fase,
        "estados_fases": estados_fases,
        "partidos_cerrados": partidos_cerrados,
        "crawling_text": crawling_text,
        "username": username,
        "datos": datos_actuales,
        "resultados_dict": resultados_dict,
        "puntos_por_partido": puntos_por_partido,
        "sidebar_data": sidebar,
        "torneo_finalizado": torneo_finalizado,
        "reclamo_actual": reclamo_actual,
        "premios_elegibles": premios_elegibles
    })

@router.post("/predict/{match_id}", response_class=HTMLResponse)
async def predict_match(
    request: Request,
    match_id: str,
    g1: str = Form(None),
    g2: str = Form(None),
    penales: str = Form(None),
    db: Session = Depends(get_db)
):
    """Guarda la predicción parcial del usuario vía HTMX en SQLite."""
    import json
    
    username = get_current_user(request)
    if not username:
        return f'<span style="color: red; font-size: 0.85rem;">⚠️ No autenticado</span>'

    # 1. Verificar si el partido está cerrado administrativamente (bloqueo individual)
    from database.models import ConfigGlobal
    conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
    partidos_cerrados = json.loads(conf_cerrados.valor) if conf_cerrados else []
    
    if match_id in partidos_cerrados:
        return f'<span style="color: #dc3545; font-size: 0.85rem; font-weight: bold;">🔒 Evento Finalizado. Se conservaron tus datos previos.</span>'

    # 2. Verificar si la FASE completa está habilitada
    from core.scoring import ScoringEngine
    engine = ScoringEngine()
    phase_internal = engine.match_phases.get(match_id, 'group')
    
    # Mapa de fases internas a nombres de configuración
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
    
    # Si la fase no está en el dict, asumimos que está cerrada por seguridad (excepto Grupos que es la inicial)
    fase_activa = fases_estado.get(phase_display, True if phase_display == "Grupos" else False)
    
    if not fase_activa:
        return f'<span style="color: #dc3545; font-size: 0.85rem; font-weight: bold;">🔒 Fase {phase_display} Cerrada. Se conservaron tus datos previos.</span>'

    # Validación simple: si ambos tienen valor, procesamos el guardado en la DB
    if g1 is not None and str(g1).strip() != "" and g2 is not None and str(g2).strip() != "":
        try:
            val_g1 = int(g1)
            val_g2 = int(g2)
            if val_g1 < 0 or val_g2 < 0:
                raise ValueError("Numbers must be positive")
        except ValueError:
            return f'<span style="color: #dc3545; font-size: 0.85rem; font-weight: bold;">❌ Error: Ingresa solo números válidos.</span>'

        # Buscar usuario en DB
        pred = db.query(Prediccion).filter(Prediccion.username == username).first()
        if not pred:
            pred = Prediccion(username=username, datos="{}")
            db.add(pred)
            db.commit()
            
        # Parsear JSON existente
        datos = json.loads(pred.datos) if pred.datos else {}
        datos[f"{match_id}_g1"] = val_g1
        datos[f"{match_id}_g2"] = val_g2
        if penales:
            datos[f"{match_id}_penales"] = penales
        else:
            datos.pop(f"{match_id}_penales", None)
        
        # Volver a guardar JSON
        pred.datos = json.dumps(datos)
        db.commit()
        
        msg = f'<span style="color: #28a745; font-size: 0.85rem; font-weight: bold;">✅ Guardado {val_g1}-{val_g2}</span>'
        if val_g1 == val_g2 and penales:
            msg += f'<br><span style="color: #102a68; font-size: 0.8rem;">(Penales: {penales})</span>'
        return msg
    
    return f'<span style="color: #6c757d; font-size: 0.85rem;">⏳ Pendiente</span>'

@router.post("/reclamar_premio", response_class=HTMLResponse)
async def reclamar_premio(
    request: Request,
    premio_id: int = Form(...),
    db: Session = Depends(get_db)
):
    from database.models import ReclamoPremio, Premio, ConfigGlobal
    username = get_current_user(request)
    if not username:
        return "<div style='color:red;'>⚠️ No autenticado</div>"
        
    conf_torneo = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "torneo_finalizado").first()
    torneo_finalizado = json.loads(conf_torneo.valor) if conf_torneo else False
    if not torneo_finalizado:
        return "<div style='color:red;'>⚠️ El torneo aún no ha finalizado.</div>"
        
    existente = db.query(ReclamoPremio).filter(ReclamoPremio.username == username).first()
    if existente:
        return "<div style='color:red;'>⚠️ Ya has elegido un premio.</div>"
        
    nuevo_reclamo = ReclamoPremio(
        username=username,
        premio_id=premio_id,
        datos_contacto="Sistema"
    )
    db.add(nuevo_reclamo)
    db.commit()
    
    return '''
        <div style="background-color: #d4edda; color: #155724; padding: 20px; border-radius: 12px; text-align: center; border: 2px solid #28a745; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="font-size: 3rem; margin-bottom: 10px;">🏆🎉🚚</div>
            <h3 style="margin-top: 0; color: #155724;">¡Felicitaciones y Gracias por Jugar!</h3>
            <p style="font-size: 1.1rem; font-weight: bold;">Has seleccionado tu premio con éxito.</p>
            <p>Tus datos han sido registrados. En los próximos <strong>30 días</strong> nos pondremos en contacto contigo para coordinar la entrega de tu regalo.</p>
            <div style="margin-top: 15px; font-size: 0.9em; font-style: italic; color: #0f5132;">
                ¡Mucha suerte en la próxima edición! ⚽🙌
            </div>
        </div>
        <script>setTimeout(() => window.location.reload(), 5000);</script>
    '''

@router.get("/fixture", response_class=HTMLResponse)
async def ver_fixture(request: Request, db: Session = Depends(get_db)):
    """Renderiza el fixture de grupos mostrando los resultados oficiales y puntajes."""
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
        
    try:
        from database.models import DatosOficiales
        from core.scoring import ScoringEngine
        
        # Cargar predicciones
        pred = db.query(Prediccion).filter(Prediccion.username == username).first()
        datos_prediccion = json.loads(pred.datos) if pred and pred.datos else {}
                
        # Cargar resultados
        resultados_raw = db.query(DatosOficiales).all()
        resultados_dict = {}
        for r in resultados_raw:
            try:
                resultados_dict[r.match_id] = json.loads(r.datos)
            except:
                pass

        engine = ScoringEngine()
        
        fixture_grupos = {}
        for grupo_name, partidos in GRUPOS.items():
            fixture_grupos[grupo_name] = []
            for p in partidos:
                m_id = p['id']
                pts = "N/A"
                max_pts = False
                off_data = resultados_dict.get(m_id)
                if off_data and off_data.get("g1") is not None:
                    pts = engine._calcular_partido(m_id, datos_prediccion, off_data)
                    
                    real_winner_str = engine._get_winner_str(off_data.get("g1"), off_data.get("g2"))
                    is_tie = (real_winner_str == "draw")
                    
                    base_max = engine.rules.get("exact_score", 6)
                    if is_tie and off_data.get("winner"):
                        base_max += engine.rules.get("penalty_bonus", 1)
                        
                    phase = engine.match_phases.get(m_id, 'group')
                    mult = engine.multipliers.get(phase, 1.0)
                    max_possible = int(base_max * mult)
                    
                    if pts == max_possible:
                        max_pts = True
                
                p_dict = dict(p)
                p_dict['off_g1'] = off_data.get("g1") if off_data else ""
                p_dict['off_g2'] = off_data.get("g2") if off_data else ""
                p_dict['off_penales'] = off_data.get("winner") if off_data and off_data.get("winner") else ""
                p_dict['user_pts'] = pts
                p_dict['is_max_pts'] = max_pts
                
                fixture_grupos[grupo_name].append(p_dict)
                
        # Extraer asignaciones de equipos para knockout
        conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        knockout_asignaciones = json.loads(conf_asig.valor) if conf_asig else {}

        # Calcular y pasar también los partidos KNOCKOUT para la llave
        fixture_knockout = []
        for p in KNOCKOUT:
            m_id = p['id']
            asig = knockout_asignaciones.get(m_id)
            p_copy = dict(p)
            
            # Si el admin ya asignó equipos reales, los usamos
            if asig:
                p_copy['t1'] = asig['t1']
                p_copy['bandera1'] = asig['bandera1']
                p_copy['t2'] = asig['t2']
                p_copy['bandera2'] = asig['bandera2']
            # De lo contrario, NO setteamos t1/t2 aquí para que el template use el 'desc' split
            # o mostramos "TBD" si no hay descripción.

            pts = "N/A"
            max_pts = False
            off_data = resultados_dict.get(m_id)
            if off_data and off_data.get("g1") is not None:
                pts = engine._calcular_partido(m_id, datos_prediccion, off_data)
                
                real_winner_str = engine._get_winner_str(off_data.get("g1"), off_data.get("g2"))
                is_tie = (real_winner_str == "draw")
                
                base_max = engine.rules.get("exact_score", 6)
                if is_tie and off_data.get("winner"):
                    base_max += engine.rules.get("penalty_bonus", 1)
                    
                phase = engine.match_phases.get(m_id, 'round_of_32')
                mult = engine.multipliers.get(phase, 1.0)
                max_possible = int(base_max * mult)
                
                if pts == max_possible:
                    max_pts = True
                    
            p_copy['off_g1'] = off_data.get("g1") if off_data else ""
            p_copy['off_g2'] = off_data.get("g2") if off_data else ""
            p_copy['off_penales'] = off_data.get("winner") if off_data and off_data.get("winner") else ""
            p_copy['user_pts'] = pts
            p_copy['is_max_pts'] = max_pts
            
            fixture_knockout.append(p_copy)
                
        return templates.TemplateResponse("fixture.html", {
            "request": request,
            "username": username,
            "fixture_grupos": fixture_grupos,
            "fixture_knockout": fixture_knockout,
            "sidebar_data": get_sidebar_data(username, db)
        })
    except Exception as e:
        import traceback
        print(f"DEBUG Error en ver_fixture: {str(e)}")
        print(traceback.format_exc())
        return HTMLResponse(content=f"Error en servidor: {str(e)}", status_code=500)

@router.get("/ranking", response_class=HTMLResponse)
async def ver_ranking(request: Request, db: Session = Depends(get_db)):
    """Renderiza la tabla de posiciones global."""
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
        
    # Extraer todos los usuarios ordenados por puntos descendente (excluyendo admins si se desea, aquí los metemos todos)
    from database.models import Usuario, Premio
    usuarios_ordenados = db.query(Usuario).order_by(Usuario.puntos_totales.desc()).all()
    
    premios = db.query(Premio).order_by(Premio.orden.asc()).all()
    
    return templates.TemplateResponse("ranking.html", {
        "request": request,
        "username": username,
        "usuarios": usuarios_ordenados,
        "sidebar_data": get_sidebar_data(username, db),
        "premios": premios
    })

@router.get("/reglas", response_class=HTMLResponse)
async def ver_reglas(request: Request, db: Session = Depends(get_db)):
    """Renderiza la página estática de reglamento y premios."""
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
        
    from database.models import Usuario, Premio
    usuario = db.query(Usuario).filter(Usuario.username == username).first()
    premios = db.query(Premio).order_by(Premio.orden.asc()).all()
        
    return templates.TemplateResponse("reglas.html", {
        "request": request,
        "username": username,
        "usuario": usuario,
        "premios": premios,
        "sidebar_data": get_sidebar_data(username, db)
    })

@router.get("/perfil", response_class=HTMLResponse)
async def ver_perfil(request: Request, db: Session = Depends(get_db)):
    """Renderiza el perfil del usuario activo con su desglose de puntos por partido."""
    username = get_current_user(request)
    if not username:
        return RedirectResponse(url="/login", status_code=303)
        
    from database.models import Usuario, DatosOficiales, Premio
    from core.scoring import ScoringEngine
    
    usuario = db.query(Usuario).filter(Usuario.username == username).first()
    
    premios = db.query(Premio).order_by(Premio.orden.asc()).all()
    
    # Construir historial
    historial = []
    pred = db.query(Prediccion).filter(Prediccion.username == username).first()
    if pred and pred.datos:
        try:
            datos_prediccion = json.loads(pred.datos)
        except:
            datos_prediccion = {}
            
        # Cargar resultados oficiales
        from database.models import DatosOficiales
        resultados_raw = db.query(DatosOficiales).all()

        engine = ScoringEngine()
        
        # Mapear nombres de partidos (incluyendo asignaciones dinámicas)
        conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        knockout_asignaciones = json.loads(conf_asig.valor) if conf_asig else {}

        nombres_partidos = {}
        total_matches = 0
        matches_predicted = 0
        
        # Grupos
        for grupo_name, partidos in GRUPOS.items():
            for p in partidos:
                total_matches += 1
                nombres_partidos[p['id']] = {"desc": f"{p['t1']} vs {p['t2']}", "fase": "GRUPOS"}
                if f"{p['id']}_g1" in datos_prediccion and f"{p['id']}_g2" in datos_prediccion:
                    matches_predicted += 1
        
        # Knockout
        for p in KNOCKOUT:
            total_matches += 1
            asig = knockout_asignaciones.get(p['id'])
            if asig:
                desc = f"{asig['t1']} vs {asig['t2']}"
            else:
                desc = f"TBD ({p.get('desc', p['id'])})"
            nombres_partidos[p['id']] = {"desc": desc, "fase": p.get('phase', 'ELIMINATORIAS').upper()}
            if f"{p['id']}_g1" in datos_prediccion and f"{p['id']}_g2" in datos_prediccion:
                matches_predicted += 1

        for r in resultados_raw:
            try:
                off_data = json.loads(r.datos)
                pts = engine._calcular_partido(r.match_id, datos_prediccion, off_data)
                
                info_p = nombres_partidos.get(r.match_id, {"desc": r.match_id, "fase": ""})
                
                historial.append({
                    "partido": info_p["desc"],
                    "fase": info_p["fase"],
                    "off_g1": off_data.get("g1", "-"),
                    "off_g2": off_data.get("g2", "-"),
                    "pred_g1": datos_prediccion.get(f"{r.match_id}_g1"),
                    "pred_g2": datos_prediccion.get(f"{r.match_id}_g2"),
                    "puntos": pts
                })
            except:
                continue
    else:
        # Fallback if no predictions record exists yet
        total_matches = 0
        for lista in GRUPOS.values(): total_matches += len(lista)
        total_matches += len(KNOCKOUT)
        matches_predicted = 0

    # Identificar el próximo premio por posición
    posicion_actual = get_sidebar_data(username, db)["posicion"]
    proximo_premio = None
    # premios está ordenado por orden asc
    # buscamos el premio con el "mayor" (peor) orden que sea menor a la posicion actual del usuario, 
    # o el premio de 1er lugar si todos los premios tienen orden menor.
    for p in reversed(premios):
        if p.orden < posicion_actual:
            proximo_premio = p
            break
    
    if not proximo_premio and premios and posicion_actual > 1:
        proximo_premio = premios[0]

    return templates.TemplateResponse("perfil.html", {
        "request": request,
        "username": username,
        "usuario": usuario,
        "historial": historial,
        "sidebar_data": get_sidebar_data(username, db),
        "premios": premios,
        "total_matches": total_matches,
        "matches_predicted": matches_predicted,
        "proximo_premio": proximo_premio
    })
