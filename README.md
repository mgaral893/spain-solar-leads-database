# Spain Solar Leads Database (B2B Scraper & Sync)

Este repositorio contiene una tubería (pipeline) de automatización robusta en Python para recopilar contactos comerciales (B2B leads) de instaladores autorizados de placas solares en España y sincronizar automáticamente la base de datos resultante con un producto de venta en **Gumroad**.

El Beelink actúa como un programador semanal que ejecuta el scraper en 2 minutos y actualiza el archivo descargable sin consumir recursos persistentes del sistema.

---

## 🛠️ Arquitectura del Sistema

```
[Beelink Server (AgiCron)]
         ↓ (Semanal / Cron)
   [scraper.py] ────→ Consulta DuckDuckGo Lite & Crawlea webs locales
         ↓
   [instaladores_solares_espana.csv] (leads limpios: Nombre, Email, Teléfono, Web)
         ↓
   [gumroad_export.py] ─── (API Gumroad v2) ───→ [Tu Producto en Gumroad Nube]
                                                          ↓
                                                   [Cliente Final (Venta)]
```

---

## 📋 Estructura de Archivos

*   `scraper.py`: El crawler principal. Busca instaladores en múltiples provincias españolas, extrae nombres, teléfonos de contacto e inspecciona sus sitios web oficiales para recuperar direcciones de correo electrónico corporativas verificadas.
*   `gumroad_export.py`: Realiza el registro automático del producto en Gumroad y la subida de los archivos CSV compilados.
*   `requirements.txt`: Dependencias de librerías Python.
*   `gumroad_config.json`: Guarda de forma local el identificador del producto en Gumroad tras su primera creación.

---

## 🚀 Instrucciones de Uso

### 1. Preparación del Entorno
Clona el repositorio e instala las dependencias necesarias:
```bash
pip install -r requirements.txt
```

### 2. Ejecutar el Scraper
Para generar o actualizar la base de datos local en formato CSV:
```bash
python3 scraper.py
```

### 3. Sincronizar con Gumroad
Exporta tu Token de Acceso Personal de Gumroad a tus variables de entorno y ejecuta el sincronizador. Si el producto no existe en tu tienda, el script lo creará y guardará su ID en `gumroad_config.json`:
```bash
export GUMROAD_TOKEN="tu_token_de_gumroad_aqui"
python3 gumroad_export.py
```

### 📅 Automatización en AgiCron
Puedes programar el pipeline para que se ejecute de forma autónoma todos los domingos a las 00:00 añadiendo la tarea a `AgiCron` o a tu programador local del sistema.
