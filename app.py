# ============================================================
# 🍽️ CONTROL DE COMEDOR - CITROLIM PERÚ
# Backend FastAPI + Frontend HTML
# ============================================================

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os
import json
from datetime import datetime
from typing import Optional
import tempfile
import shutil

app = FastAPI(title="Comedor Citrolim PERÚ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ARCHIVOS
# ============================================================

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

ARCHIVO_USUARIOS = os.path.join(DATA_DIR, "usuarios_comedor.json")
ARCHIVO_ATENCIONES = os.path.join(DATA_DIR, "atenciones_comedor.xlsx")
ARCHIVO_LOG_CARGAS = os.path.join(DATA_DIR, "log_cargas.xlsx")

# ============================================================
# ESTADO GLOBAL
# ============================================================

df_colaboradores = pd.DataFrame()
df_turnos = pd.DataFrame()
columna_programacion = None
dnis_dieta = set()

# ============================================================
# USUARIOS
# ============================================================

def cargar_usuarios():
    if os.path.exists(ARCHIVO_USUARIOS):
        with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as f:
            return json.load(f)
    usuarios = {
        "admin": {"clave": "admin123", "rol": "admin", "nombre": "Administrador"},
        "rrhh": {"clave": "1234", "rol": "rrhh", "nombre": "Usuario RRHH"},
        "proveedor": {"clave": "1234", "rol": "proveedor", "nombre": "Usuario Proveedor"}
    }
    guardar_usuarios(usuarios)
    return usuarios

def guardar_usuarios(usuarios):
    with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)

usuarios_db = cargar_usuarios()

# ============================================================
# ATENCIONES
# ============================================================

def cargar_atenciones():
    if os.path.exists(ARCHIVO_ATENCIONES):
        try:
            return pd.read_excel(ARCHIVO_ATENCIONES)
        except Exception:
            pass
    return pd.DataFrame(columns=["Fecha", "Hora", "DNI", "Nombre", "Área", "Servicio", "Tipo"])

atenciones = cargar_atenciones()

def guardar_atencion(dni, nombre, area, servicio, tipo):
    global atenciones
    ahora = datetime.now()
    nueva = pd.DataFrame([{
        "Fecha": ahora.strftime("%Y-%m-%d"),
        "Hora": ahora.strftime("%H:%M:%S"),
        "DNI": str(dni).strip(),
        "Nombre": nombre,
        "Área": area,
        "Servicio": servicio,
        "Tipo": tipo
    }])
    atenciones = pd.concat([atenciones, nueva], ignore_index=True)
    atenciones.to_excel(ARCHIVO_ATENCIONES, index=False)

# ============================================================
# UTILIDADES
# ============================================================

def normalizar_rut(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.lstrip("0") or "0"

def obtener_turno(codigo):
    if df_turnos.empty:
        return None
    res = df_turnos[df_turnos["Siglas"].astype(str).str.strip().str.upper() == str(codigo).strip().upper()]
    return res.iloc[0] if len(res) > 0 else None

def determinar_servicio(hora):
    if pd.isna(hora):
        return None
    try:
        h = int(str(hora).strip().split(":")[0])
        if h in [12, 13]:
            return "ALMUERZO"
        if h == 21:
            return "CENA"
    except Exception:
        pass
    return None

def contar_programados():
    almuerzo = cena = 0
    if df_colaboradores.empty or columna_programacion is None:
        return 0, 0
    for _, row in df_colaboradores.iterrows():
        codigo = row[columna_programacion]
        if pd.isna(codigo):
            continue
        codigo = str(codigo).strip().upper()
        if codigo in ["D", "F", "L", "P", "V", "C"]:
            continue
        turno = obtener_turno(codigo)
        if turno is None:
            continue
        servicio = determinar_servicio(turno.get("Entrada de colación"))
        if servicio == "ALMUERZO":
            almuerzo += 1
        elif servicio == "CENA":
            cena += 1
    return almuerzo, cena

def consultar_dni_interno(dni):
    if not dni or str(dni).strip() == "":
        return None, "⚠️ Ingresa un DNI"
    if df_colaboradores.empty:
        return None, "⚠️ No hay programación cargada"

    dni_norm = normalizar_rut(dni)
    mask = df_colaboradores["RUT"].apply(normalizar_rut) == dni_norm
    if not mask.any():
        return None, "🔴 DNI NO ENCONTRADO"

    persona = df_colaboradores[mask].iloc[0]
    codigo = persona[columna_programacion]

    if pd.isna(codigo) or str(codigo).strip().upper() in ["D", "F", "L", "P", "V", "C"]:
        return {
            "dni": str(persona["RUT"]),
            "nombre": str(persona["Nombre del Colaborador"]),
            "area": str(persona["Área"]),
            "estado": "NO PROGRAMADO",
            "es_dieta": dni_norm in dnis_dieta
        }, "🟠 NO ESTÁ PROGRAMADO PARA HOY"

    turno = obtener_turno(codigo)
    if turno is None:
        return {
            "dni": str(persona["RUT"]),
            "nombre": str(persona["Nombre del Colaborador"]),
            "area": str(persona["Área"]),
            "estado": "TURNO NO ENCONTRADO",
            "es_dieta": dni_norm in dnis_dieta
        }, "⚠️ Turno no encontrado"

    servicio = determinar_servicio(turno.get("Entrada de colación"))
    return {
        "dni": str(persona["RUT"]),
        "nombre": str(persona["Nombre del Colaborador"]),
        "area": str(persona["Área"]),
        "servicio": servicio or "NO DEFINIDO",
        "estado": "PROGRAMADO",
        "es_dieta": dni_norm in dnis_dieta
    }, f"🟢 PROGRAMADO — {servicio or 'NO DEFINIDO'}"

def obtener_pendientes_lista():
    if df_colaboradores.empty or columna_programacion is None:
        return []

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    atendidos = set()
    if len(atenciones) > 0:
        mask = pd.to_datetime(atenciones["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d") == hoy_str
        atendidos = set(atenciones.loc[mask, "DNI"].apply(normalizar_rut).tolist())

    pendientes = []
    for _, row in df_colaboradores.iterrows():
        codigo = row[columna_programacion]
        if pd.isna(codigo) or str(codigo).strip().upper() in ["D", "F", "L", "P", "V", "C"]:
            continue
        turno = obtener_turno(codigo)
        if turno is None:
            continue
        servicio = determinar_servicio(turno.get("Entrada de colación"))
        if servicio not in ["ALMUERZO", "CENA"]:
            continue
        dni_norm = normalizar_rut(row["RUT"])
        if dni_norm in atendidos:
            continue
        pendientes.append({
            "DNI": str(row["RUT"]),
            "Nombre": str(row["Nombre del Colaborador"]),
            "Área": str(row["Área"]),
            "Servicio": servicio,
            "Dieta": "SÍ" if dni_norm in dnis_dieta else ""
        })
    return pendientes

def obtener_resumen():
    pendientes = obtener_pendientes_lista()
    total_pend = len(pendientes)
    pend_dieta = sum(1 for p in pendientes if p.get("Dieta") == "SÍ")
    pend_normal = total_pend - pend_dieta

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    atendidos_hoy = 0
    if len(atenciones) > 0:
        mask = pd.to_datetime(atenciones["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d") == hoy_str
        atendidos_hoy = int(mask.sum())

    return {
        "atendidos": atendidos_hoy,
        "pendientes": total_pend,
        "dieta": pend_dieta,
        "normal": pend_normal
    }

# ============================================================
# API ENDPOINTS
# ============================================================

@app.post("/api/login")
async def api_login(usuario: str = Form(...), clave: str = Form(...)):
    usuario = usuario.strip().lower()
    clave = clave.strip()
    if usuario in usuarios_db and usuarios_db[usuario]["clave"] == clave:
        u = usuarios_db[usuario]
        return {"ok": True, "rol": u["rol"], "nombre": u.get("nombre", usuario)}
    return JSONResponse(status_code=401, content={"ok": False, "mensaje": "Usuario o clave incorrectos"})

@app.post("/api/cargar-programacion")
async def api_cargar_programacion(archivo: UploadFile = File(...), usuario: str = Form("rrhh")):
    global df_colaboradores, df_turnos, columna_programacion

    try:
        suffix = os.path.splitext(archivo.filename or "file.xlsx")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(archivo.file, tmp)
            ruta = tmp.name

        excel = pd.ExcelFile(ruta)
        hojas = excel.sheet_names

        if "turnosColaboradores" not in hojas or "turnosSemanales" not in hojas:
            os.unlink(ruta)
            return {"ok": False, "mensaje": f"Faltan hojas. Tiene: {hojas}"}

        df_colaboradores = pd.read_excel(excel, sheet_name="turnosColaboradores")
        df_turnos = pd.read_excel(excel, sheet_name="turnosSemanales")
        os.unlink(ruta)

        cols = ["Nombre del Colaborador", "RUT", "Área"]
        faltantes = [c for c in cols if c not in df_colaboradores.columns]
        if faltantes:
            return {"ok": False, "mensaje": f"Faltan columnas: {faltantes}"}

        base = ["Nombre del Colaborador", "RUT", "Área", "Supervisor"]
        fechas = [c for c in df_colaboradores.columns if c not in base]
        if not fechas:
            return {"ok": False, "mensaje": "No se encontró columna de programación"}

        columna_programacion = fechas[-1]
        almuerzo, cena = contar_programados()

        # Log
        try:
            log = pd.DataFrame([{
                "Fecha": datetime.now().strftime("%Y-%m-%d"),
                "Hora": datetime.now().strftime("%H:%M:%S"),
                "Usuario": usuario,
                "Archivo": archivo.filename,
                "Colaboradores": len(df_colaboradores),
                "Almuerzos": almuerzo,
                "Cenas": cena
            }])
            if os.path.exists(ARCHIVO_LOG_CARGAS):
                anterior = pd.read_excel(ARCHIVO_LOG_CARGAS)
                log = pd.concat([anterior, log], ignore_index=True)
            log.to_excel(ARCHIVO_LOG_CARGAS, index=False)
        except Exception:
            pass

        return {
            "ok": True,
            "mensaje": f"Programación cargada. Columna: {columna_programacion}",
            "columna": str(columna_programacion),
            "colaboradores": len(df_colaboradores),
            "almuerzo": almuerzo,
            "cena": cena,
            "total": almuerzo + cena
        }
    except Exception as e:
        return {"ok": False, "mensaje": str(e)}

@app.post("/api/cargar-dieta")
async def api_cargar_dieta(archivo: UploadFile = File(...)):
    global dnis_dieta
    try:
        suffix = os.path.splitext(archivo.filename or "file.xlsx")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(archivo.file, tmp)
            ruta = tmp.name

        try:
            df = pd.read_excel(ruta, sheet_name="turnosColaboradores", dtype=str)
        except Exception:
            df = pd.read_excel(ruta, dtype=str)

        os.unlink(ruta)

        if "RUT" not in df.columns:
            return {"ok": False, "mensaje": "No se encontró columna RUT"}

        dnis_dieta = set(df["RUT"].apply(normalizar_rut).tolist())
        return {"ok": True, "mensaje": f"Lista de dieta cargada: {len(dnis_dieta)} personas", "total": len(dnis_dieta)}
    except Exception as e:
        return {"ok": False, "mensaje": str(e)}

@app.get("/api/consultar/{dni}")
async def api_consultar(dni: str):
    info, mensaje = consultar_dni_interno(dni)
    if info is None:
        return {"ok": False, "mensaje": mensaje, "info": None}
    return {"ok": True, "mensaje": mensaje, "info": info}

@app.post("/api/registrar")
async def api_registrar(dni: str = Form(...), tipo: str = Form("PROGRAMADO")):
    global atenciones
    info, mensaje = consultar_dni_interno(dni)
    if info is None or info.get("estado") != "PROGRAMADO":
        return {"ok": False, "mensaje": mensaje or "No se puede registrar"}

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    if len(atenciones) > 0:
        ya = atenciones[
            (atenciones["DNI"].apply(normalizar_rut) == normalizar_rut(dni)) &
            (pd.to_datetime(atenciones["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d") == hoy_str)
        ]
        if len(ya) > 0:
            return {"ok": False, "mensaje": "⚠️ ESTA PERSONA YA FUE ATENDIDA HOY"}

    guardar_atencion(
        info["dni"],
        info["nombre"],
        info["area"],
        info.get("servicio", "ALMUERZO"),
        tipo
    )
    return {
        "ok": True,
        "mensaje": f"✅ ATENCIÓN REGISTRADA — {info['nombre']} — {info.get('servicio', '')}",
        "resumen": obtener_resumen(),
        "pendientes": obtener_pendientes_lista()
    }

@app.post("/api/registrar-adicional")
async def api_registrar_adicional(
    dni: str = Form(...),
    nombre: str = Form(...),
    area: str = Form(...),
    servicio: str = Form("ALMUERZO")
):
    global atenciones
    if not dni.strip() or not nombre.strip() or not area.strip():
        return {"ok": False, "mensaje": "Completa todos los campos"}

    info, _ = consultar_dni_interno(dni)
    if info and info.get("estado") == "PROGRAMADO":
        return {"ok": False, "mensaje": "Este DNI ya está programado. No se puede registrar como adicional."}

    hoy_str = datetime.now().strftime("%Y-%m-%d")
    if len(atenciones) > 0:
        ya = atenciones[
            (atenciones["DNI"].apply(normalizar_rut) == normalizar_rut(dni)) &
            (pd.to_datetime(atenciones["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d") == hoy_str)
        ]
        if len(ya) > 0:
            return {"ok": False, "mensaje": "⚠️ ESTA PERSONA YA FUE ATENDIDA HOY"}

    guardar_atencion(dni, nombre, area, servicio, "ADICIONAL")
    return {
        "ok": True,
        "mensaje": f"✅ ADICIONAL REGISTRADO — {nombre} — {servicio}",
        "resumen": obtener_resumen(),
        "pendientes": obtener_pendientes_lista()
    }

@app.get("/api/resumen")
async def api_resumen():
    return obtener_resumen()

@app.get("/api/pendientes")
async def api_pendientes():
    return {"pendientes": obtener_pendientes_lista()}

@app.get("/api/dashboard-programados")
async def api_dashboard_programados():
    almuerzo, cena = contar_programados()
    return {"almuerzo": almuerzo, "cena": cena, "total": almuerzo + cena}

@app.post("/api/crear-usuario")
async def api_crear_usuario(
    usuario: str = Form(...),
    clave: str = Form(...),
    rol: str = Form(...),
    nombre: str = Form("")
):
    global usuarios_db
    usuario = usuario.strip().lower()
    if not usuario or not clave:
        return {"ok": False, "mensaje": "Usuario y clave obligatorios"}
    if usuario in usuarios_db:
        return {"ok": False, "mensaje": "Ese usuario ya existe"}
    if rol not in ["admin", "rrhh", "proveedor"]:
        return {"ok": False, "mensaje": "Rol inválido"}
    usuarios_db[usuario] = {"clave": clave, "rol": rol, "nombre": nombre or usuario}
    guardar_usuarios(usuarios_db)
    return {"ok": True, "mensaje": f"Usuario {usuario} creado (rol: {rol})"}

@app.get("/api/log-cargas")
async def api_log_cargas():
    if os.path.exists(ARCHIVO_LOG_CARGAS):
        df = pd.read_excel(ARCHIVO_LOG_CARGAS).sort_values(["Fecha", "Hora"], ascending=False)
        return {"log": df.fillna("").to_dict(orient="records")}
    return {"log": []}

@app.get("/api/descargar-reporte")
async def api_descargar_reporte():
    pendientes = obtener_pendientes_lista()
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    if len(atenciones) > 0:
        mask = pd.to_datetime(atenciones["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d") == hoy_str
        atendidos = atenciones[mask].copy()
    else:
        atendidos = pd.DataFrame(columns=["Fecha", "Hora", "DNI", "Nombre", "Área", "Servicio", "Tipo"])

    archivo = os.path.join(DATA_DIR, f"reporte_comedor_{hoy_str}.xlsx")
    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        atendidos.to_excel(writer, sheet_name="Atendidos", index=False)
        pd.DataFrame(pendientes).to_excel(writer, sheet_name="Pendientes", index=False)
    return FileResponse(archivo, filename=f"reporte_comedor_{hoy_str}.xlsx")

@app.get("/api/descargar-dia")
async def api_descargar_dia():
    hoy_str = datetime.now().strftime("%Y-%m-%d")
    if len(atenciones) == 0:
        df = pd.DataFrame(columns=["Fecha", "Hora", "DNI", "Nombre", "Área", "Servicio", "Tipo"])
    else:
        mask = pd.to_datetime(atenciones["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d") == hoy_str
        df = atenciones[mask]
    archivo = os.path.join(DATA_DIR, f"atenciones_{hoy_str}.xlsx")
    df.to_excel(archivo, index=False)
    return FileResponse(archivo, filename=f"atenciones_{hoy_str}.xlsx")

@app.get("/api/fecha")
async def api_fecha():
    return {"fecha": datetime.now().strftime("%d/%m/%Y"), "fecha_completa": datetime.now().strftime("%A %d/%m/%Y")}

# Servir frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")
