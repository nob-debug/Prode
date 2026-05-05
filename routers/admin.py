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

    # Extraer si el torneo ya terminó y se bloquea para el reclamo
    conf_torneo = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "torneo_finalizado").first()
    torneo_finalizado = json.loads(conf_torneo.valor) if conf_torneo else False

    # Extraer premios (Primero por categoría para que en el admin se vean agrupados, luego orden)
    from database.models import Premio, Usuario
    import csv
    import os

    premios = db.query(Premio).order_by(Premio.categoria.asc(), Premio.orden.asc()).all()

    # --- CALCULO DEL PODIUM Y PREMIOS ESPECIALES (SOLO ADMIN) ---
    usuarios_rank = db.query(Usuario).order_by(Usuario.puntos_totales.desc()).all()
    
    # Cargar nombres reales desde el CSV
    csv_path = "database/id-nombre-prode.csv"
    cod_to_name = {}
    if os.path.exists(csv_path):
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=';')
            try:
                next(reader) # skip header
            except:
                pass
            for row in reader:
                if len(row) >= 2:
                    cod_to_name[row[0].strip()] = row[1].strip()

    # Asignar display_name a la vista del admin
    for u in usuarios_rank:
        ext_id = u.external_id or ""
        real_name = cod_to_name.get(ext_id, "")
        if ext_id and real_name:
            # Quitamos los asteriscos y exclamaciones molestos que vienen en el CSV original a veces
            clean_real_name = real_name.split('*')[0].split('!')[0].strip()
            u.display_name = f"{ext_id} - {clean_real_name} ({u.username})"
        else:
            u.display_name = u.username

    # --- CALCULO DE ESTADISTICAS DE JUEGO (Jugados, Aciertos, Fallos) ---
    from database.models import Prediccion
    from core.scoring import ScoringEngine
    
    engine = ScoringEngine()
    predicciones_raw = db.query(Prediccion).all()
    pred_map = {p.username: json.loads(p.datos) if p.datos else {} for p in predicciones_raw}
    
    for u in usuarios_rank:
        u.jugados = 0
        u.aciertos = 0
        u.fallos = 0
        u.aciertos_exactos = 0
        u.aciertos_tendencia = 0
        
        user_preds = pred_map.get(u.username, {})
        for match_id, off_data in resultados_dict.items():
            if off_data.get("g1") is not None and off_data.get("g2") is not None:
                pred_g1 = user_preds.get(f"{match_id}_g1")
                pred_g2 = user_preds.get(f"{match_id}_g2")
                pred_winner = user_preds.get(f"{match_id}_penales")
                
                # Check if the user predicted this match
                if (pred_g1 is not None and str(pred_g1).strip() != "") or \
                   (pred_g2 is not None and str(pred_g2).strip() != "") or \
                   (pred_winner):
                    u.jugados += 1
                    pts = engine._calcular_partido(match_id, user_preds, off_data)
                    if pts > 0:
                        u.aciertos += 1
                        if pts in [6, 7]:
                            u.aciertos_exactos += 1
                        elif pts in [3, 4]:
                            u.aciertos_tendencia += 1
                    else:
                        u.fallos += 1

    # Para la Cuchara de Madera: solo cuentan los que jugaron al menos 1 vez
    # El ganador es el que tenga menos puntos, y a igualdad de puntos, el que más haya jugado.
    participantes_activos = [u for u in usuarios_rank if u.jugados > 0]
    if participantes_activos:
        # Ordenar: puntos asc, luego jugados desc
        madera_candidato = sorted(participantes_activos, key=lambda x: (x.puntos_totales, -x.jugados))[0]
    else:
        madera_candidato = None

    # Para El Casi-Casi: El candidato debe estar del 4to puesto en adelante (índice 3+)
    # y cumplir la condición de NO haber acertado resultado exacto (0 aciertos exactos).
    casi_casi_ganador = None
    if len(usuarios_rank) > 3:
        for u in usuarios_rank[3:]:
            if getattr(u, 'aciertos_exactos', 0) == 0 and getattr(u, 'aciertos_tendencia', 0) > 0:
                casi_casi_ganador = u
                break

    podium = {
        "primero": usuarios_rank[0] if len(usuarios_rank) > 0 else None,
        "segundo": usuarios_rank[1] if len(usuarios_rank) > 1 else None,
        "tercero": usuarios_rank[2] if len(usuarios_rank) > 2 else None,
        "casi_casi": casi_casi_ganador,
        "madera": madera_candidato
    }

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
        "premios": premios,
        "podium": podium,
        "usuarios_rank": usuarios_rank,
        "torneo_finalizado": torneo_finalizado
    })

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
    slot: int = Form(...),
    image: UploadFile = File(...)
):
    """Sube y reemplaza un banner de la página de inicio."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    if slot not in [1, 2, 3, 4]:
        return "<div style='color:red;'>Slot inválido</div>"
        
    if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
        return "<div style='color:red;'>Formato de imagen no soportado.</div>"

    # Define the path to save the banner
    banner_dir = "static/banner"
    os.makedirs(banner_dir, exist_ok=True)
    file_path = os.path.join(banner_dir, f"slide{slot}.jpg")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        return f'''
            <div style="color: green; font-weight: bold;">
                ✅ Banner {slot} actualizado correctamente.
            </div>
        '''
    except Exception as e:
        return f'''
            <div style="color: red; font-weight: bold;">
                ❌ Error al subir el banner: {str(e)}
            </div>
        '''

@router.post("/config/banner_login", response_class=HTMLResponse)
async def upload_login_banner(
    request: Request,
    image: UploadFile = File(...)
):
    """Sube y reemplaza el banner del sponsor del login."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
        return "<div style='color:red;'>Formato de imagen no soportado.</div>"

    banner_dir = "static/banner"
    os.makedirs(banner_dir, exist_ok=True)
    file_path = os.path.join(banner_dir, "login_sponsor.jpg")
    
    try:
        import shutil
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        return f'''
            <div style="color: green; font-weight: bold; padding: 5px;">
                ✅ Banner de Login actualizado.
            </div>
        '''
    except Exception as e:
        return f'''
            <div style="color: red; font-weight: bold; padding: 5px;">
                ❌ Error: {str(e)}
            </div>
        '''

@router.post("/config/banner_fijo", response_class=HTMLResponse)
async def upload_fixed_banner(
    request: Request,
    slot: int = Form(...),
    image: UploadFile = File(...)
):
    """Sube y reemplaza uno de los 4 banners de publicidad fijos."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    if slot not in [1, 2, 3, 4]:
        return "<div style='color:red;'>Slot inválido</div>"
        
    if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
        return "<div style='color:red;'>Formato de imagen no soportado.</div>"

    banner_dir = "static/banner"
    os.makedirs(banner_dir, exist_ok=True)
    file_path = os.path.join(banner_dir, f"pub{slot}.png")
    
    # Mantener PUBLICIDAD_PRODE.png como alias del slot 1 para compatibilidad
    legacy_path = os.path.join(banner_dir, "PUBLICIDAD_PRODE.png")
    
    try:
        import shutil
        content = await image.read()
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        if slot == 1:
            with open(legacy_path, "wb") as buffer:
                buffer.write(content)
                
        return f'''
            <div style="color: green; font-weight: bold; padding: 5px;">
                ✅ Auspiciante Fijo {slot} actualizado.
            </div>
        '''
    except Exception as e:
        return f'''
            <div style="color: red; font-weight: bold; padding: 5px;">
                ❌ Error: {str(e)}
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
    from database.models import DatosOficiales, ConfigGlobal
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
    
    # Agregar a partidos_finalizados para reflejar estado visual
    conf_fin = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_finalizados").first()
    if not conf_fin:
        conf_fin = ConfigGlobal(clave="partidos_finalizados", valor="[]")
        db.add(conf_fin)
        db.commit()
        
    finalizados_list = json.loads(conf_fin.valor)
    if match_id not in finalizados_list:
        finalizados_list.append(match_id)
        conf_fin.valor = json.dumps(finalizados_list)
    
    # AUTO-BLOQUEO: También agregar a partidos_cerrados para que el usuario no pueda editar
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
        <div style="color: #3182ce; font-weight: bold; padding: 5px;">
            🏁 Finalizado: {g1} - {g2} {f"(Penales: {winner})" if winner else ""}
        </div>
        <script>
            // Recargar la página después de 1 segundo para mostrar el nuevo color azul
            setTimeout(function() {{
                window.location.reload();
            }}, 1000);
        </script>
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
        <script>setTimeout(() => window.location.reload(), 500);</script>
    '''

@router.post("/knockout/unassign", response_class=HTMLResponse)
async def unassign_knockout_teams(
    request: Request,
    match_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Elimina la asignación de equipos para un partido de eliminatorias, regresándolo a Etapa 1."""
    username = get_current_user(request)
    if username != "admin":
        return "<div style='color:red;'>Acceso denegado</div>"
        
    from database.models import ConfigGlobal
    import json
    
    conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
    if conf:
        asignaciones = json.loads(conf.valor)
        if match_id in asignaciones:
            del asignaciones[match_id]
            conf.valor = json.dumps(asignaciones)
            db.commit()
    
    return f'''
        <div style="color: #6c757d; font-weight: bold; padding: 5px;">
            🔄 Reestableciendo partido...
        </div>
        <script>setTimeout(() => window.location.reload(), 500);</script>
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

@router.post("/premio/add", response_class=HTMLResponse)
async def add_premio(
    request: Request,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    puntos_requeridos: int = Form(0),
    orden: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Agrega un nuevo premio con su imagen."""
    username = get_current_user(request)
    if username != "admin":
        return "<div class='alert alert-danger'>Acceso denegado</div>"
        
    try:
        from database.models import Premio
        import time
        import os
        import shutil
        
        # Validar imagen
        if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            return "<div style='color:red;'>Formato de imagen no soportado.</div>"
            
        # Guardar imagen con nombre único
        premios_dir = "static/premios"
        os.makedirs(premios_dir, exist_ok=True)
        ext = image.filename.split(".")[-1]
        timestamp = int(time.time())
        filename = f"premio_{timestamp}.{ext}"
        file_path = os.path.join(premios_dir, filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
            
        # Generar categoría en base al orden para uso visual
        if orden == 1:
            categoria = "1er Lugar"
        elif orden == 2:
            categoria = "2do Lugar"
        elif orden == 3:
            categoria = "3er Lugar"
        elif orden == 0:
            categoria = "Premio Consuelo"
        else:
            categoria = f"Puesto {orden}"

        # Crear registro en BD
        nuevo_premio = Premio(
            nombre=nombre,
            descripcion=descripcion,
            puntos_requeridos=puntos_requeridos,
            imagen_url=f"/{file_path}",
            orden=orden,
            categoria=categoria
        )
        db.add(nuevo_premio)
        db.commit()
        
        return '''
            <div style="background-color: #d1e7dd; color: #0f5132; padding: 10px; border-radius: 5px; margin-top: 10px;">
                ✅ Premio agregado exitosamente. Actualiza la página para verlo.
            </div>
            <script>setTimeout(() => window.location.reload(), 1500);</script>
        '''
    except Exception as e:
        return f"<div style='color:red;'>Error al guardar premio: {str(e)}</div>"

@router.post("/premio/delete", response_class=HTMLResponse)
async def delete_premio(
    request: Request,
    premio_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """Elimina un premio y su imagen."""
    username = get_current_user(request)
    if username != "admin":
        return "<div class='alert alert-danger'>Acceso denegado</div>"
        
    try:
        from database.models import Premio
        premio = db.query(Premio).filter(Premio.id == premio_id).first()
        if not premio:
            return "<div style='color:red;'>Premio no encontrado.</div>"
            
        # Intentar borrar el archivo de imagen
        import os
        image_path = premio.imagen_url.lstrip("/") # remover slash inicial para ruta local
        if os.path.exists(image_path):
            os.remove(image_path)
            
        db.delete(premio)
        db.commit()
        
        return '''
            <div style="background-color: #d1e7dd; color: #0f5132; padding: 10px; border-radius: 5px; margin-top: 10px;">
                ✅ Premio eliminado correctamente.
            </div>
            <script>setTimeout(() => window.location.reload(), 1000);</script>
        '''
    except Exception as e:
        return f"<div style='color:red;'>Error al eliminar premio: {str(e)}</div>"

@router.post("/reiniciar_oficiales", response_class=HTMLResponse)
async def reiniciar_oficiales(request: Request, db: Session = Depends(get_db)):
    """Reinicia SOLO los resultados oficiales del torneo, dejando intactas las predicciones de los usuarios."""
    username = get_current_user(request)
    if username != "admin":
        return "<div class='alert alert-danger'>Acceso denegado</div>"
        
    try:
        from database.models import DatosOficiales, Usuario, ConfigGlobal
        
        # 1. Borrar todos los resultados oficiales
        db.query(DatosOficiales).delete()
        
        # 2. Restablecer los puntos de los usuarios a cero
        db.query(Usuario).update({Usuario.puntos_totales: 0})
        
        # 3. Restablecer estados de fases y partidos cerrados en ConfigGlobal
        estados_iniciales = {"Grupos": True, "Dieciseisavos": False, "Octavos": False, "Cuartos": False, "Semis": False, "Finales": False}
        import json
        
        conf_fases = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "fases_estado").first()
        if conf_fases:
            conf_fases.valor = json.dumps(estados_iniciales)
            
        conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
        if conf_cerrados:
            conf_cerrados.valor = "[]"
            
        conf_finalizados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_finalizados").first()
        if conf_finalizados:
            conf_finalizados.valor = "[]"
            
        conf_knockout = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        if conf_knockout:
            conf_knockout.valor = "{}"
            
        db.commit()
        
        return '''
            <div style="background-color: #d1e7dd; color: #0f5132; padding: 15px; border-radius: 5px; margin-top: 15px; font-weight: bold;">
                ⚠️ ✅ ¡RESULTADOS OFICIALES REINICIADOS! Las predicciones de los usuarios siguen intactas.
            </div>
            <script>setTimeout(() => window.location.reload(), 3000);</script>
        '''
    except Exception as e:
        db.rollback()
        return f"<div style='color:red;'>❌ Error al reiniciar: {str(e)}</div>"

@router.post("/reiniciar_datos", response_class=HTMLResponse)
async def reiniciar_datos(request: Request, db: Session = Depends(get_db)):
    """Reinicia todo el torneo (predicciones, resultados oficiales y puntajes a cero)."""
    username = get_current_user(request)
    if username != "admin":
        return "<div class='alert alert-danger'>Acceso denegado</div>"
        
    try:
        from database.models import Prediccion, DatosOficiales, Usuario, ConfigGlobal
        
        # 1. Borrar todas las predicciones
        db.query(Prediccion).delete()
        
        # 2. Borrar todos los resultados oficiales
        db.query(DatosOficiales).delete()
        
        # 3. Restablecer los puntos de los usuarios a cero (sin borrarlos)
        db.query(Usuario).update({Usuario.puntos_totales: 0})
        
        # 4. Restablecer estados de fases, partidos cerrados y eliminatorias en ConfigGlobal
        estados_iniciales = {"Grupos": True, "Dieciseisavos": False, "Octavos": False, "Cuartos": False, "Semis": False, "Finales": False}
        import json
        
        conf_fases = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "fases_estado").first()
        if conf_fases:
            conf_fases.valor = json.dumps(estados_iniciales)
            
        conf_cerrados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_cerrados").first()
        if conf_cerrados:
            conf_cerrados.valor = "[]"
            
        conf_finalizados = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "partidos_finalizados").first()
        if conf_finalizados:
            conf_finalizados.valor = "[]"
            
        conf_knockout = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "knockout_asignaciones").first()
        if conf_knockout:
            conf_knockout.valor = "{}"
            
        db.commit()
        
        return '''
            <div style="background-color: #d1e7dd; color: #0f5132; padding: 15px; border-radius: 5px; margin-top: 15px; font-weight: bold;">
                ⚠️ ✅ ¡TORNEO REINICIADO CON ÉXITO! Las predicciones y puntajes han vuelto a CERO.
            </div>
            <script>setTimeout(() => window.location.reload(), 3000);</script>
        '''
    except Exception as e:
        db.rollback()
        return f"<div style='color:red;'>❌ Error al reiniciar: {str(e)}</div>"

@router.post("/toggle_torneo_finalizado", response_class=HTMLResponse)
async def toggle_torneo_finalizado(request: Request, db: Session = Depends(get_db)):
    """Marca o desmarca el torneo como finalizado para habilitar los reclamos de premios."""
    username = get_current_user(request)
    if username != "admin":
        return "<div class='alert alert-danger'>Acceso denegado</div>"
        
    try:
        from database.models import ConfigGlobal
        import json
        
        conf = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "torneo_finalizado").first()
        if not conf:
            conf = ConfigGlobal(clave="torneo_finalizado", valor="true")
            db.add(conf)
            act = True
        else:
            act = not json.loads(conf.valor)
            conf.valor = json.dumps(act)
            
        db.commit()
        
        if act:
            return '''
                <div style="background-color: #d1e7dd; color: #0f5132; padding: 15px; border-radius: 5px; margin-top: 15px; font-weight: bold; text-align: center;">
                    ✅ EL TORNEO SE HA DADO POR FINALIZADO Y LOS PREMIOS HAN SIDO LIBERADOS
                </div>
                <script>setTimeout(() => window.location.reload(), 2000);</script>
            '''
        else:
            return '''
                <div style="background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; margin-top: 15px; font-weight: bold; text-align: center;">
                    🔄 TORNEO PUESTO EN JUEGO NUEVAMENTE (Premios Ocultos)
                </div>
                <script>setTimeout(() => window.location.reload(), 2000);</script>
            '''
    except Exception as e:
        db.rollback()
        return f"<div style='color:red;'>❌ Error: {str(e)}</div>"

@router.get("/descargar_reclamos_csv")
async def descargar_reclamos_csv(request: Request, db: Session = Depends(get_db)):
    username = get_current_user(request)
    if username != "admin":
        return RedirectResponse(url="/login")
        
    from database.models import ReclamoPremio, Premio, Usuario
    import csv
    import os
    from io import StringIO
    from fastapi.responses import StreamingResponse
    
    # Cargar nombres reales desde el CSV
    csv_path = "database/id-nombre-prode.csv"
    cod_to_name = {}
    if os.path.exists(csv_path):
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=';')
            try:
                next(reader) # skip header
            except:
                pass
            for row in reader:
                if len(row) >= 2:
                    cod_to_name[row[0].strip()] = row[1].strip()

    # Consultar reclamos ordenados por el puntaje del usuario (Ranking)
    reclamos = db.query(ReclamoPremio).join(
        Usuario, ReclamoPremio.username == Usuario.username
    ).order_by(Usuario.puntos_totales.desc()).all()
    
    premios_dict = {p.id: p for p in db.query(Premio).all()}
    usuarios_dict = {u.username: u for u in db.query(Usuario).all()}
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Username", "ID", "Nombre Real", "Premio Elegido", "Categoria"])
    
    for r in reclamos:
        p = premios_dict.get(r.premio_id)
        u = usuarios_dict.get(r.username)
        
        premio_nombre = p.nombre if p else "Desconocido"
        premio_cat = p.categoria if p else "-"
        
        ext_id = u.external_id if u else ""
        real_name = cod_to_name.get(ext_id, "")
        if ext_id and real_name:
            clean_real_name = real_name.split('*')[0].split('!')[0].strip()
        else:
            clean_real_name = ""
            
        writer.writerow([r.username, ext_id, clean_real_name, premio_nombre, premio_cat])
        
    output.seek(0)
    
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=reclamos_premios.csv"
    
    return response
