# Comedor Citrolim PERÚ

Aplicación de control de comedor con interfaz Citrolim + backend FastAPI.

## Cómo ejecutar (en tu PC)

1. Instala Python 3.10 o superior
2. Abre la terminal en esta carpeta
3. Ejecuta:

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

4. Abre en el navegador: http://127.0.0.1:8000

## Usuarios por defecto

| Usuario    | Clave     | Rol        |
|------------|-----------|------------|
| rrhh       | 1234      | RRHH       |
| proveedor  | 1234      | Proveedor  |
| admin      | admin123  | Admin      |

## Funciones

- **RRHH**: cargar programación diaria, cargar dieta, consultar DNI
- **Proveedor**: registrar programados y adicionales, ver pendientes, resumen del día
- **Admin**: crear usuarios, trazabilidad de cargas, descargar reportes
- **Público**: registro sin login

## Estructura

```
comedor-citrolim-app/
├── app.py              # Backend FastAPI
├── requirements.txt
├── README.md
├── data/               # Se crea solo (atenciones, usuarios, logs)
└── static/
    ├── index.html      # Interfaz
    ├── logo.png
    └── mascota.png
```
