from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Usuario

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza la pantalla de Login."""
    from database.models import ConfigGlobal
    import time
    conf_cache = db.query(ConfigGlobal).filter(ConfigGlobal.clave == "cache_buster").first()
    cache_buster = conf_cache.valor if conf_cache else str(int(time.time()))
    return templates.TemplateResponse("login.html", {"request": request, "cache_buster": cache_buster})

@router.post("/login", response_class=HTMLResponse)
async def login_process(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa el formulario de Login vía HTMX y establece la cookie HTTPOnly."""
    # Buscamos al usuario en la BD
    usuario = db.query(Usuario).filter(Usuario.username == username).first()
    
    if not usuario or usuario.password != password:
        # Credenciales inválidas: devolvemos un mensaje de error HTML para insertar en la UI
        return f'<div style="color: red; margin-top: 10px;">Usuario o contraseña incorrectos.</div>'
    
    # Credenciales válidas: preparamos un header HX-Redirect para decirle a HTMX que cambie de página
    # Establecemos una simple cookie de sesión para identificar al usuario
    response = HTMLResponse(content="")
    response.set_cookie(key="session_token", value=usuario.username, httponly=True, max_age=86400) # 1 día de sesión
    response.headers["HX-Redirect"] = "/"
    
    return response

@router.post("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_token")
    response.headers["HX-Redirect"] = "/login"
    return response

@router.post("/register", response_class=HTMLResponse)
async def register_process(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa el registro de un nuevo usuario."""
    # Verificar si el usuario ya existe
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return f'<div style="color: red; margin-top: 10px;">El nombre de usuario ya está en uso.</div>'
    
    # Crear nuevo usuario
    nuevo_usuario = Usuario(username=username, password=password)
    db.add(nuevo_usuario)
    db.commit()
    
    # Iniciar sesión automáticamente
    response = HTMLResponse(content="")
    response.set_cookie(key="session_token", value=username, httponly=True, max_age=86400)
    response.headers["HX-Redirect"] = "/"
    return response

# Dependencia para requerir autenticación en otras rutas
def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        return None
    return token # Devolvemos el username directamente
