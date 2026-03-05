from fastapi import APIRouter, Request, Depends, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import os
import shutil
from sqlalchemy.orm import Session
from database.database import get_db
from routers.auth import get_current_user
from core.constantes import GRUPOS, KNOCKOUT, COUNTRIES
import json


router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    """Renderiza el Panel Admin Principal utilizando una plantilla Jinja2."""
    username = get_current_user(request)
    if username != "admin":
        return RedirectResponse(url="/login", status_code=303)
        
    # Cargar estado de fases desde la BD (bloqueos)
    from database.models import ConfigGlobal
    conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "fases_estado").first()
    if not conf:
        estados_fases = {"Grupos": True, "Dieciseisavos": False, "Octavos": False, "Cuartos": False, "Semis": False, "Finales": False}
        nueva_conf = ConfigGlobal(clave="fases_estado", valor=json.dumps(estados_fases))
        db.add(nueva_conf)
        db.commit()
    else:
        estados_fases = json.loads(conf.valor)

    # Agrupar partidos KNOCKOUT por fase
    knockout_por_fase = {}
    for p in KNOCKOUT:
        fase = p.get('phase', 'Eliminatorias')
        if fase not in knockout_por_fase:
            knockout_por_fase[fase] = []
        knockout_por_fase[fase].append(p)

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
    resultados_raw = db.query(DatosOficiales).all()
    resultados_dict = {}
    for r in resultados_raw:
        try:
            resultados_dict[r.match_id] = json.loads(r.datos)
        except:
            pass

    # Extraer partidos cerrados
    conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
    partidos_cerrados = json.loads(conf_cerrados.valor) if conf_cerrados else []

    # Extraer asignaciones de equipos para knockout
    conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
    knockout_asignaciones = json.loads(conf_asig.valor) if conf_asig else {}

    # Extraer partidos finalizados (completamente terminados)
    conf_fin = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_finalizados").first()
    partidos_finalizados = json.loads(conf_fin.valor) if conf_fin else []

    # Extraer configuración de ranking
    conf_ranking = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "ranking_config").first()
    if not conf_ranking:
        ranking_config = {
            "title": "🏆 Clasificación General",
            "desc_title": "🚀 ¡La Carrera por la Gloria! ⚽",
            "desc_body": "¡Acá se definen los campeones del Prode! Peleá por los premios más zarpados: desde un **iPhone 15 Pro** o una **MacBook** pal' 1°, hasta la **PS5 Slim**, **iPads** o la **Camiseta de la Scaloneta** para los que siguen. ¡Mucha suerte y que gane el mejor! 🏆✨"
        }
        nueva_conf = ConfigGlobal(clave="ranking_config", valor=json.dumps(ranking_config))
        db.add(nueva_conf)
        db.commit()
    else:
        ranking_config = json.loads(conf_ranking.valor)

    # Extraer configuración de reglamentos
    conf_reglas = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "reglas_dinamicas").first()
    if not conf_reglas:
        reglas_dinamicas = [
            {
                "title": "Puntajes Regulares",
                "items": [
                    {"icon": "🎯", "title": "Marcador Exacto (6 Puntos)", "desc": "Si aciertas exactamente los goles que hace cada equipo, ganas el máximo de puntos. (Ej: Predices 2-1 y el partido sale 2-1)."},
                    {"icon": "🤝", "title": "Acierto de Tendencia (3 Puntos)", "desc": "Si aciertas quién gana (o el empate) pero no el resultado exacto, sumas 3 puntos. (Ej: Predices 2-0 y el partido sale 1-0)."},
                    {"icon": "⚖️", "title": "Bonus de Penales (+1 Punto)", "desc": "En caso de acertar un empate durante las rondas KO, si también adivinas quién gana en los tiros desde el punto penal, obtienes un punto extra."},
                    {"icon": "✖️", "title": "Multiplicadores de Fase", "desc": "Los puntos base se multiplican según la importancia del partido: Grupos (x1), Dieciseisavos (x1.25), Octavos (x1.5), Cuartos (x2.0), Semifinales (x3.0), Final (x4.0)."}
                ]
            },
            {
                "title": "Premios Oficiales 🏆",
                "items": [
                    {"icon": "🥇", "title": "1° Puesto", "desc": "Apple iPhone 16 Pro Max + Trofeo Oficial del Torneo."},
                    {"icon": "🥈", "title": "2° Puesto", "desc": "PlayStation 5 Slim + Medalla de Plata."},
                    {"icon": "🥉", "title": "3er Puesto", "desc": "Camiseta Oficial Argentina 3 Estrellas + Medalla de Bronce."}
                ]
            }
        ]
        nueva_conf = ConfigGlobal(clave="reglas_dinamicas", valor=json.dumps(reglas_dinamicas))
        db.add(nueva_conf)
        db.commit()
    else:
        reglas_dinamicas = json.loads(conf_reglas.valor)

    # Extraer cache buster
    conf_cache = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "cache_buster").first()
    cache_buster = conf_cache.valor if conf_cache else "1"

    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "estados": estados_fases,
        "partidos_agrupados_fecha": partidos_agrupados_fecha,
        "knockout_por_fase": knockout_por_fase,
        "resultados_dict": resultados_dict,
        "partidos_cerrados": partidos_cerrados,
        "knockout_asignaciones": knockout_asignaciones,
        "partidos_finalizados": partidos_finalizados,
        "countries": COUNTRIES,
        "ranking_config": ranking_config,
        "reglas_dinamicas": reglas_dinamicas,
        "cache_buster": cache_buster
    })

@router.post("/reglas/save")
async def save_reglas(request: Request, db: Session = Depends(get_db)):
    """Guarda la configuración del reglamento enviada como JSON."""
    username = get_current_user(request)
    if username != "admin":
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        body = await request.body()
        data = json.loads(body)
        
        from database.models import ConfigGlobal
        conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "reglas_dinamicas").first()
        if conf:
            conf.valor = json.dumps(data)
        else:
            conf = ConfigGlobal(clave="reglas_dinamicas", valor=json.dumps(data))
            db.add(conf)
            
        db.commit()
        return {"status": "success", "message": "Reglamento guardado correctamente"}
    except Exception as e:
        print(f"Error guardando reglas: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/reset-scores")
async def reset_scores(request: Request, db: Session = Depends(get_db)):
    """Borra todos los resultados oficiales y resetea los puntos de todos los usuarios."""
    username = get_current_user(request)
    if username != "admin":
        return RedirectResponse(url="/login", status_code=303)
    
    try:
        from database.models import DatosOficiales, Usuario, ConfigGlobal
        
        # 1. Borrar todos los resultados oficiales
        db.query(DatosOficiales).delete()
        
        # 2. Limpiar listas de partidos cerrados y finalizados
        conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
        if conf_cerrados:
            conf_cerrados.valor = json.dumps([])
            
        conf_fin = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_finalizados").first()
        if conf_fin:
            conf_fin.valor = json.dumps([])

        # 4. Limpiar asignaciones de knockout (opcional, pero recomendado para reset total)
        conf_asig = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        if conf_asig:
            conf_asig.valor = json.dumps({})
            
        db.commit()
        return {"status": "success", "message": "Todos los puntajes y resultados han sido reseteados."}
    except Exception as e:
        db.rollback()
        print(f"Error en reset_scores: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/config/fase", response_class=HTMLResponse)
async def update_fase(
    request: Request,
    fase: str = Form(...),
    active: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Actualiza el estado de una fase desde un toggle HTMX y devuelve el nuevo estado HTML."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    # Lógica de actualización de BD aquí
    from database.models import ConfigGlobal
    import json
    
    conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "fases_estado").first()
    if not conf:
        estados_fases = {"Grupos": True, "Dieciseisavos": False, "Octavos": False, "Cuartos": False, "Semis": False, "Finales": False}
        conf = ConfigGlobal(clave="fases_estado", valor=json.dumps(estados_fases))
        db.add(conf)
    else:
        estados_fases = json.loads(conf.valor)

    fase_key = fase.capitalize()
    estados_fases[fase_key] = active
    conf.valor = json.dumps(estados_fases)
    db.commit()
    color = "green" if active else "red"
    estado_texto = "Activada" if active else "Cerrada"
    
    # Devolvemos un fragmento HTML para que HTMX reemplace el toggle
    return f'''
        <div style="color: {color}; font-weight: bold;">
            La fase {fase.capitalize()} ahora está {estado_texto}
        </div>
    '''

@router.post("/config/banner", response_class=HTMLResponse)
async def upload_banner(
    request: Request,
    slot: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Sube y reemplaza un banner de sponsor o premio."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
        return "<div style='color:red;'>Formato de imagen no soportado. Usa JPG o PNG.</div>"

    # Determinar la ruta de destino según el slot
    file_path = ""
    if slot == "sponsor":
        os.makedirs("static/banner", exist_ok=True)
        file_path = "static/banner/sponsor_banner.jpg"
    elif slot == "login_sponsor":
        os.makedirs("static/banner", exist_ok=True)
        file_path = "static/banner/login_sponsor.jpg"
    elif slot.startswith("prize_"):
        os.makedirs("static/img/prizes", exist_ok=True)
        file_path = f"static/img/prizes/{slot}.png"
    else:
        return "<div style='color:red;'>Slot inválido</div>"
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
            
        # Actualizar el cache_buster
        from database.models import ConfigGlobal
        import time
        import json
        conf_cache = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "cache_buster").first()
        if not conf_cache:
            conf_cache = ConfigGlobal(clave="cache_buster", valor=str(int(time.time())))
            db.add(conf_cache)
        else:
            conf_cache.valor = str(int(time.time()))
        db.commit()

        return f'''
            <div style="color: green; font-weight: bold;">
                ✅ ¡Imagen subida y caché actualizada!
            </div>
        '''
    except Exception as e:
        return f'''
            <div style="color: red; font-weight: bold;">
                ❌ Error al subir el banner: {str(e)}
            </div>
        '''


@router.post("/match/save", response_class=HTMLResponse)
async def save_match_result(
    request: Request,
    match_id: str = Form(...),
    g1: int = Form(...),
    g2: int = Form(...),
    winner: str = Form(None),
    db: Session = Depends(get_db)
):
    """Guarda el resultado oficial de un partido vía HTMX."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    # Lógica de guardado en BD oficial
    from database.models import DatosOficiales
    import json
    
    oficial = db.query(DatosOficiales).filter(DatosOficiales.match_id == match_id).first()
    if not oficial:
        oficial = DatosOficiales(match_id=match_id, datos="{}")
        db.add(oficial)
        db.commit()
        
    resultado_json = {
        "g1": g1,
        "g2": g2,
        "winner": winner if winner else None
    }
    oficial.datos = json.dumps(resultado_json)
    db.commit()

    return f'''
        <div style="color: green; font-weight: bold; padding: 5px;">
            ✅ Guardado: {g1} - {g2} {f"(Penales: {winner})" if winner else ""}
        </div>
    '''

@router.post("/match/lock", response_class=HTMLResponse)
async def lock_match(
    request: Request,
    match_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Cierra y finaliza un partido para que no se puedan modificar más predicciones."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    # Lógica de bloqueo en BD oficial
    from database.models import ConfigGlobal
    import json
    
    conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
    if not conf_cerrados:
        conf_cerrados = ConfigGlobal(clave="partidos_cerrados", valor="[]")
        db.add(conf_cerrados)
        db.commit()
    
    cerrados_list = json.loads(conf_cerrados.valor)
    if match_id not in cerrados_list:
        cerrados_list.append(match_id)
        conf_cerrados.valor = json.dumps(cerrados_list)
        db.commit()

    return f'''
        <div style="color: #dc3545; font-weight: bold; padding: 5px;">
            🔒 Partido {match_id} Finalizado y Bloqueado
        </div>
    '''


@router.post("/recalcular", response_class=HTMLResponse)
async def procesar_puntajes(request: Request, db: Session = Depends(get_db)):
    """Ejecuta el motor de scoring sobre todas las predicciones."""
    username = get_current_user(request)
    if username != "admin":
        return "<div class='alert alert-danger'>Acceso denegado</div>"
        
    try:
        from core.scoring import ScoringEngine
        engine = ScoringEngine()
        engine.recalcular_todo(db)
        
        return f'''
            <div style="background-color: #d1e7dd; color: #0f5132; padding: 10px; border-radius: 5px; margin-top: 10px;">
                ✅ ¡Puntajes recalculados con éxito para todos los usuarios!
            </div>
        '''
    except Exception as e:
        return f'''
            <div style="background-color: #f8d7da; color: #842029; padding: 10px; border-radius: 5px; margin-top: 10px;">
                ❌ Error al procesar: {str(e)}
            </div>
        '''

@router.post("/knockout/assign", response_class=HTMLResponse)
async def assign_knockout_teams(
    request: Request,
    match_id: str = Form(...),
    t1: str = Form(...),
    t2: str = Form(...),
    db: Session = Depends(get_db)
):
    """Guarda la asignación de equipos para un partido de eliminatorias."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    from database.models import ConfigGlobal
    import json
    
    conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
    if not conf:
        conf = ConfigGlobal(clave="knockout_asignaciones", valor="{}")
        db.add(conf)
    
    asignaciones = json.loads(conf.valor)
    
    # Buscar banderas en COUNTRIES
    from core.constantes import COUNTRIES
    b1 = next((c['flag'] for c in COUNTRIES if c['name'] == t1), "🏳️")
    b2 = next((c['flag'] for c in COUNTRIES if c['name'] == t2), "🏳️")
    
    asignaciones[match_id] = {
        "t1": t1, "bandera1": b1,
        "t2": t2, "bandera2": b2
    }
    
    conf.valor = json.dumps(asignaciones)
    db.commit()
    
    return f'''
        <div style="color: green; font-weight: bold; padding: 5px;">
            ✅ Equipos Asignados: {b1} {t1} vs {t2} {b2}
        </div>
    '''

@router.post("/knockout/finish", response_class=HTMLResponse)
async def finish_knockout_match(
    request: Request,
    match_id: str = Form(...),
    g1: int = Form(...),
    g2: int = Form(...),
    winner: str = Form(None),
    db: Session = Depends(get_db)
):
    """Guarda el resultado oficial y marca el partido como completamente finalizado."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    # 1. Guardar el resultado (reutilizando save_match_result logic)
    from database.models import DatosOficiales, ConfigGlobal
    import json
    
    oficial = db.query(DatosOficiales).filter(DatosOficiales.match_id == match_id).first()
    if not oficial:
        oficial = DatosOficiales(match_id=match_id, datos="{}")
        db.add(oficial)
        
    resultado_json = {
        "g1": g1, "g2": g2, "winner": winner if winner else None
    }
    oficial.datos = json.dumps(resultado_json)
    
    # 2. Marcar como finalizado
    conf_fin = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_finalizados").first()
    if not conf_fin:
        conf_fin = ConfigGlobal(clave="partidos_finalizados", valor="[]")
        db.add(conf_fin)
    
    finalizados = json.loads(conf_fin.valor)
    if match_id not in finalizados:
        finalizados.append(match_id)
        conf_fin.valor = json.dumps(finalizados)
    
    db.commit()

    return f'''
        <div style="color: #1a73e8; font-weight: bold; padding: 5px;">
            🏁 Evento Finalizado: {g1} - {g2} {f"({winner})" if winner else ""}
        </div>
    '''

@router.post("/ranking/text", response_class=HTMLResponse)
async def update_ranking_text(
    request: Request,
    title: str = Form(...),
    desc_title: str = Form(...),
    desc_body: str = Form(...),
    db: Session = Depends(get_db)
):
    """Actualiza el texto del ranking desde el panel admin."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    from database.models import ConfigGlobal
    import json
    
    conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "ranking_config").first()
    ranking_config = {
        "title": title,
        "desc_title": desc_title,
        "desc_body": desc_body
    }
    
    if not conf:
        conf = ConfigGlobal(clave="ranking_config", valor=json.dumps(ranking_config))
        db.add(conf)
    else:
        conf.valor = json.dumps(ranking_config)
    
    db.commit()
    
    return '<div style="color: green; font-weight: bold;">✅ Texto del ranking actualizado.</div>'

@router.post("/ranking/prize-image", response_class=HTMLResponse)
async def upload_prize_image(
    request: Request,
    category: int = Form(...),
    slot: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Sube una imagen de premio para el ranking."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return "<div style='color:red;'>Formato no soportado.</div>"

    prize_dir = "static/img/prizes"
    os.makedirs(prize_dir, exist_ok=True)
    # Ejemplo: prize_1_1.png, prize_2_1.png, etc.
    file_path = os.path.join(prize_dir, f"prize_{category}_{slot}.png")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # update cache buster
        from database.models import ConfigGlobal
        import time
        buster = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "cache_buster").first()
        if not buster:
            buster = ConfigGlobal(clave="cache_buster", valor=str(int(time.time())))
            db.add(buster)
        else:
            buster.valor = str(int(time.time()))
        db.commit()

        return f'<div style="color: green; font-size: 0.8rem;">✅ Premio {category}-{slot} OK.</div>'
    except Exception as e:
        return f'<div style="color: red; font-size: 0.8rem;">❌ Error: {str(e)}</div>'

@router.post("/ranking/sponsor-banner", response_class=HTMLResponse)
async def upload_sponsor_banner(
    request: Request,
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Sube el banner de sponsors para el ranking."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return "<div style='color:red;'>Formato no soportado.</div>"

    banner_dir = "static/banner"
    os.makedirs(banner_dir, exist_ok=True)
    file_path = os.path.join(banner_dir, "sponsor_banner.jpg")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # update cache buster
        from database.models import ConfigGlobal
        import time
        buster = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "cache_buster").first()
        if not buster:
            buster = ConfigGlobal(clave="cache_buster", valor=str(int(time.time())))
            db.add(buster)
        else:
            buster.valor = str(int(time.time()))
        db.commit()
        
        return '<div style="color: green; font-weight: bold;">✅ Banner de Sponsors actualizado exitosamente.</div>'
    except Exception as e:
        return f'<div style="color: red; font-weight: bold;">❌ Error: {str(e)}</div>'
