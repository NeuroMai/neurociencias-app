# Neurociencias UDP - Sistema de Evaluaciones

Sistema de evaluaciones para la Escuela de Neurociencias UDP.
Backend Flask + App Android nativa con bloqueo de screenshots.

## 📁 Estructura del Proyecto

```
neurociencias-app/
├── backend/               # Backend Flask (desplegar en la nube)
│   ├── app.py            # Aplicación Flask principal
│   ├── requirements.txt   # Dependencias Python
│   ├── Procfile           # Configuración para Railway/Render
│   ├── database.db        # Base de datos SQLite
│   ├── templates/         # Plantillas HTML
│   └── static/            # Archivos estáticos (CSS, imágenes)
├── android/               # App Android nativa
│   └── app/src/main/
│       ├── java/com/neurociencias/udp/MainActivity.java
│       ├── res/layout/activity_main.xml
│       └── AndroidManifest.xml
└── README.md
```

## 🚀 PASO 1: Desplegar Backend en la Nube

### Opción A: Railway (Recomendada - Más fácil)

1. Crea una cuenta en https://railway.app (con GitHub)
2. Instala Railway CLI:
   ```bash
   pip install railway
   ```
3. En Railway, crea un nuevo proyecto → "Deploy from GitHub repo"
4. Sube la carpeta `backend/` a un repositorio de GitHub
5. Conecta Railway a ese repositorio
6. Railway detectará automáticamente el `Procfile` y `requirements.txt`
7. La app quedará disponible en: `https://neurociencias-udp.up.railway.app`

### Opción B: Render

1. Crea cuenta en https://render.com
2. Conecta tu repositorio de GitHub con la carpeta `backend/`
3. Selecciona "Web Service"
4. Configura:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. Render te dará una URL como: `https://neurociencias-udp.onrender.com`

### Variables de Entorno (Opcional)

- `SECRET_KEY`: Para seguridad de sesiones (si no se define, usa una por defecto)
- `PORT`: Puerto del servidor (Railway/Render lo asignan automáticamente)

## 📱 PASO 2: Compilar App Android

### Requisitos
- Android Studio instalado (descargar de https://developer.android.com/studio)
- Java 17+

### Pasos

1. **Abre Android Studio** → "Open an existing project"
2. **Selecciona la carpeta**: `neurociencias-app/android/`
3. **Cambia la URL del backend** en `MainActivity.java`:
   ```java
   private static final String APP_URL = "https://TU-URL-DESPLEGADA.railway.app";
   ```
   Busca esta línea y reemplázala con la URL que te dio Railway o Render.

4. **Conecta tu celular Android** por USB o usa un emulador
5. **Haz clic en "Run"** (▶️) para compilar e instalar la app

### Generar APK para distribuir

1. En Android Studio: Build → Build Bundle(s) / APK(s) → Build APK(s)
2. El APK se generará en: `android/app/build/outputs/apk/debug/app-debug.apk`
3. Comparte ese archivo APK con tus estudiantes para que lo instalen

## 🛡️ Bloqueo de Screenshots

La app Android bloquea screenshots de 3 formas:

1. **FLAG_SECURE**: Android nativo impide capturar la pantalla (en negro)
2. **Detección Android 14+**: Detecta el evento de screenshot y finaliza la prueba
3. **Web**: Detecta teclas PrintScreen/Cmd+Shift+3 y finaliza la prueba

Además, la web finaliza la prueba si el estudiante:
- Cambia de pestaña/aplicación
- Minimiza la ventana
- Pierde el foco de la ventana

## 🎨 Personalización Estética

### Cambiar Colores

Edita el archivo `backend/static/css/estilo.css`:

```css
:root {
  --udp-red: #e31b23;      /* Cambia este color */
  --udp-black: #111111;     /* Cambia este color */
  --udp-gray: #f4f5f7;      /* Cambia este color */
  --udp-white: #ffffff;     /* Cambia este color */
}
```

### Cambiar Logo

Reemplaza los archivos en `backend/static/img/`:
- `logo.png` - Logo principal (header)
- `logo_secundario.png` - Logo secundario (final del examen)

Formatos recomendados: PNG con fondo transparente, 200-400px de ancho.

### Modificar Textos

Los textos están en los archivos HTML dentro de `backend/templates/`:
- `index.html` - Página principal
- `estudiante_portal.html` - Portal de estudiantes
- `estudiante_ingreso.html` - Formulario de ingreso
- `estudiante_disclosure.html` - Instrucciones antes del examen
- `estudiante_examen_page.html` - Página del examen
- `profesor_panel.html` - Panel del profesor
- `resultado_estudiante.html` - Resultado final

## 🔄 Actualizar la App

Cuando hagas cambios en el backend:

1. Sube los cambios a GitHub
2. Railway/Render se actualizarán automáticamente
3. Los estudiantes solo necesitan abrir la app (no necesitan actualizar)

Si cambias la app Android:
1. Haz los cambios en Android Studio
2. Genera un nuevo APK
3. Comparte el nuevo APK con los estudiantes

## ⚙️ Funcionalidades

- ✅ Crear evaluaciones con preguntas de opción múltiple, V/F y desarrollo
- ✅ Códigos de acceso para estudiantes
- ✅ Temporizador con envío automático
- ✅ Bloqueo de botón "Atrás" del navegador
- ✅ Detección de cambio de pestaña/pérdida de foco
- ✅ Corrección automática (opción múltiple y V/F)
- ✅ Revisión manual de preguntas de desarrollo
- ✅ Panel de profesor con resultados
- ✅ Bloqueo de screenshots (App Android)
- ✅ Pantalla negra al detectar captura