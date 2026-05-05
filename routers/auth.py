from fastapi import APIRouter, Request, Depends, Form, Response, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Usuario
from core.sso import verify_sso_signature

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Renderiza la pantalla de Login."""
    return templates.TemplateResponse("login.html", {"request": request})

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

@router.post("/register", response_class=HTMLResponse)
async def register_process(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa el registro de un nuevo usuario."""
    # Verificar si el usuario ya existe
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return f'<div style="color: #dc3545; background-color: #f8d7da; padding: 10px; border-radius: 5px; margin-top: 10px; border: 1px solid #f5c2c7;">El usuario "{username}" ya existe. Elige otro.</div>'
    
    # Crear nuevo usuario
    nuevo_usuario = Usuario(username=username, password=password, is_admin=False, puntos_totales=0)
    db.add(nuevo_usuario)
    db.commit()
    
    # Devolver alerta de éxito y limpiar formulario (usando hx-swap-oob o simplemente un mensaje)
    return f'''
        <div id="auth-error" hx-swap-oob="true" style="color: #0f5132; background-color: #d1e7dd; padding: 15px; border-radius: 8px; margin-top: 10px; border: 1px solid #badbcc; font-weight: bold;">
            ✅ ¡Usuario "{username}" creado con éxito! Ya puedes ingresar.
        </div>
        <script>
            // Pequeño truco para limpiar los inputs después de registrar
            document.querySelectorAll("#register-section input").forEach(i => i.value = "");
            setTimeout(() => toggleAuth(), 2000); // Volver al login automáticamente
        </script>
    '''

@router.post("/logout")
async def logout(response: Response):
    response = RedirectResponse(url="https://clientes.dfvsrl.com.ar", status_code=303)
    response.delete_cookie("session_token")
    return response

@router.get("/api/auth/external-login", response_class=HTMLResponse)
async def external_login(
    request: Request,
    id: str = Query(...),
    signature: str = Query(...),
    db: Session = Depends(get_db)
):
    """Recibe al usuario desde el sistema central redireccionado por SSO."""
    if not verify_sso_signature(id, signature):
        raise HTTPException(status_code=401, detail="Firma de seguridad inválida")
        
    usuario = db.query(Usuario).filter(Usuario.external_id == id).first()
    
    if usuario:
        # Ya existe, lo logueamos
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="session_token", value=usuario.username, httponly=True, max_age=86400)
        return response
    else:
        # No existe, pedirle que elija un alias
        return templates.TemplateResponse("alias_selection.html", {
            "request": request,
            "id": id,
            "signature": signature
        })

@router.post("/api/auth/external-register", response_class=HTMLResponse)
async def external_register(
    request: Request,
    id: str = Form(...),
    signature: str = Form(...),
    username: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa el formulario del alias para crear al usuario."""
    if not verify_sso_signature(id, signature):
        return f'<div style="color: #dc3545;">Firma de seguridad inválida.</div>'
        
    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        return f'<div style="color: #dc3545;">El alias "{username}" ya está en uso. ¡Elige otro!</div>'
        
    nuevo_usuario = Usuario(
        username=username, 
        password="", 
        external_id=id, 
        is_admin=False, 
        puntos_totales=0
    )
    db.add(nuevo_usuario)
    db.commit()
    
    # Éxito: setear cookie y redirigir
    response = HTMLResponse(content='<script>window.location.href="/";</script>')
    response.set_cookie(key="session_token", value=nuevo_usuario.username, httponly=True, max_age=86400)
    return response

# Dependencia para requerir autenticación en otras rutas
def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        return None
    return token # Devolvemos el username directamente
