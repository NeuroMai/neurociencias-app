import os
import random
import string
import sqlite3
import sys
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash

base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get('SECRET_KEY', 'neurociencias_udp_secret_key_2026_v5')

# --- Database configuration ---
# Supports SQLite (local) and PostgreSQL (Heroku/production)
DATABASE_URL = os.environ.get('DATABASE_URL', os.path.join(base_dir, 'database.db'))
DB_IS_POSTGRES = DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://')

if DATABASE_URL.startswith('sqlite:///'):
    DATABASE_PATH = DATABASE_URL.replace('sqlite:///', '')
elif DATABASE_URL.startswith('sqlite://'):
    DATABASE_PATH = DATABASE_URL.replace('sqlite://', '')
else:
    DATABASE_PATH = DATABASE_URL

def get_db():
    if DB_IS_POSTGRES:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(DATABASE_PATH)
        conn.cursor_factory = RealDictCursor
        return conn
    else:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

def db_execute(conn, sql, params=None):
    """Execute a query and return the cursor. Converts ? to %s for PostgreSQL."""
    if DB_IS_POSTGRES:
        sql = sql.replace('?', '%s')
    cursor = conn.cursor()
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    return cursor

def db_execute_insert(conn, sql, params=None):
    """Execute INSERT and return the new row id using RETURNING for PostgreSQL."""
    if DB_IS_POSTGRES:
        sql = sql.replace('?', '%s')
        cursor = conn.cursor()
        if params:
            cursor.execute(sql + ' RETURNING id', params)
        else:
            cursor.execute(sql + ' RETURNING id')
        result = cursor.fetchone()
        return result['id'] if result else None
    else:
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor.lastrowid

def generar_codigo_acceso():
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(6))

def init_db():
    with get_db() as conn:
        # Create tables (IF NOT EXISTS works for both SQLite and PostgreSQL)
        db_execute(conn, '''
            CREATE TABLE IF NOT EXISTS evaluaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                seccion TEXT NOT NULL,
                duracion_minutos INTEGER DEFAULT 60,
                codigo_acceso TEXT NOT NULL
            )
        ''')
        db_execute(conn, '''
            CREATE TABLE IF NOT EXISTS preguntas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluacion_id INTEGER,
                tipo TEXT NOT NULL,
                enunciado TEXT NOT NULL,
                opcion_a TEXT, opcion_b TEXT, opcion_c TEXT, opcion_d TEXT,
                respuesta_correcta TEXT,
                puntaje REAL DEFAULT 1,
                orden INTEGER DEFAULT 0,
                FOREIGN KEY (evaluacion_id) REFERENCES evaluaciones (id) ON DELETE CASCADE
            )
        ''')
        db_execute(conn, '''
            CREATE TABLE IF NOT EXISTS intentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evaluacion_id INTEGER,
                estudiante_nombre TEXT NOT NULL,
                estudiante_rut TEXT NOT NULL,
                seccion TEXT NOT NULL,
                puntaje_autocorregido REAL DEFAULT 0,
                puntaje_desarrollo REAL DEFAULT 0,
                puntaje_total_auto REAL DEFAULT 0,
                estado TEXT DEFAULT 'Completado',
                estado_revision TEXT DEFAULT 'sin_desarrollo',
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evaluacion_id) REFERENCES evaluaciones (id) ON DELETE CASCADE
            )
        ''')
        db_execute(conn, '''
            CREATE TABLE IF NOT EXISTS respuestas_desarrollo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intento_id INTEGER,
                pregunta_id INTEGER,
                respuesta_texto TEXT,
                puntaje_asignado REAL DEFAULT NULL,
                FOREIGN KEY (intento_id) REFERENCES intentos (id) ON DELETE CASCADE,
                FOREIGN KEY (pregunta_id) REFERENCES preguntas (id) ON DELETE CASCADE
            )
        ''')
        db_execute(conn, '''
            CREATE TABLE IF NOT EXISTS respuestas_estudiante (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intento_id INTEGER,
                pregunta_id INTEGER,
                respuesta TEXT DEFAULT '',
                es_correcta INTEGER DEFAULT 0,
                FOREIGN KEY (intento_id) REFERENCES intentos (id) ON DELETE CASCADE,
                FOREIGN KEY (pregunta_id) REFERENCES preguntas (id) ON DELETE CASCADE
            )
        ''')
        # Add estado_revision column if it doesn't exist (for databases created before this migration)
        try:
            if DB_IS_POSTGRES:
                db_execute(conn, "ALTER TABLE intentos ADD COLUMN IF NOT EXISTS estado_revision TEXT DEFAULT 'sin_desarrollo'")
            else:
                db_execute(conn, "ALTER TABLE intentos ADD COLUMN estado_revision TEXT DEFAULT 'sin_desarrollo'")
        except Exception:
            pass  # Column already exists
        conn.commit()

init_db()

# --- PREVENIR CACHÉ EN EL NAVEGADOR ---
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/')
def index():
    return render_template('index.html')

# --- RUTAS ESTUDIANTE ---

@app.route('/estudiante')
def estudiante_portal():
    conn = get_db()
    evaluaciones = db_execute(conn, 'SELECT * FROM evaluaciones').fetchall()
    return render_template('estudiante_portal.html', evaluaciones=evaluaciones)

@app.route('/estudiante/ingreso/<int:eval_id>', methods=['GET', 'POST'])
def estudiante_ingreso(eval_id):
    conn = get_db()
    evaluacion = db_execute(conn, 'SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    if not evaluacion:
        return redirect(url_for('estudiante_portal'))

    error = None
    if request.method == 'POST':
        codigo_ingresado = request.form.get('codigo_acceso', '').strip().upper()
        if codigo_ingresado == evaluacion['codigo_acceso'].strip().upper():
            session['estudiante_nombre'] = request.form.get('nombre')
            session['estudiante_rut'] = request.form.get('rut')
            session['estudiante_seccion'] = request.form.get('seccion')
            session[f'acceso_autorizado_{eval_id}'] = True
            return redirect(url_for('estudiante_disclosure', eval_id=eval_id))
        else:
            error = "Código de acceso incorrecto. Solicita el código al docente."
        
    return render_template('estudiante_ingreso.html', evaluacion=evaluacion, error=error)

@app.route('/estudiante/disclosure/<int:eval_id>')
def estudiante_disclosure(eval_id):
    if not session.get(f'acceso_autorizado_{eval_id}'):
        return redirect(url_for('estudiante_portal'))

    conn = get_db()
    evaluacion = db_execute(conn, 'SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    preguntas = db_execute(conn, 'SELECT * FROM preguntas WHERE evaluacion_id = ?', (eval_id,)).fetchall()
    
    total_preguntas = len(preguntas)
    cant_opcion_multiple = sum(1 for p in preguntas if p['tipo'] == 'opcion_multiple')
    cant_vf = sum(1 for p in preguntas if p['tipo'] == 'verdadero_falso')
    cant_desarrollo = sum(1 for p in preguntas if p['tipo'] == 'desarrollo')
    
    return render_template('estudiante_disclosure.html', 
                           evaluacion=evaluacion,
                           total_preguntas=total_preguntas,
                           cant_opcion_multiple=cant_opcion_multiple,
                           cant_vf=cant_vf,
                           cant_desarrollo=cant_desarrollo)

@app.route('/estudiante/rendir/<int:eval_id>')
def estudiante_rendir(eval_id):
    # SI NO TIENE ACCESO AUTORIZADO, REDIRIGIR AL PORTAL
    if not session.get(f'acceso_autorizado_{eval_id}'):
        return redirect(url_for('estudiante_portal'))

    conn = get_db()
    evaluacion = db_execute(conn, 'SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    
    session_key = f'orden_preguntas_{eval_id}'
    if session_key not in session:
        om = [dict(p) for p in db_execute(conn, "SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'opcion_multiple' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
        vf = [dict(p) for p in db_execute(conn, "SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'verdadero_falso' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
        des = [dict(p) for p in db_execute(conn, "SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'desarrollo' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
        
        random.shuffle(om)
        random.shuffle(vf)
        random.shuffle(des)
        
        preguntas_ordenadas = om + vf + des
        session[session_key] = preguntas_ordenadas

        # Crear el intento en la base de datos al iniciar la prueba
        nombre = session.get('estudiante_nombre', 'Estudiante Desconocido')
        rut = session.get('estudiante_rut', 'Sin RUT')
        seccion = session.get('estudiante_seccion', 'Sin Sección')
        
        # Determinar estado_revision inicial
        tiene_desarrollo = any(p['tipo'] == 'desarrollo' for p in preguntas_ordenadas)
        estado_revision = 'pendiente' if tiene_desarrollo else 'sin_desarrollo'
        
        intento_id = db_execute_insert(conn, '''
            INSERT INTO intentos (evaluacion_id, estudiante_nombre, estudiante_rut, seccion, estado, estado_revision)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (eval_id, nombre, rut, seccion, 'En Progreso', estado_revision))
        conn.commit()
        
        session[f'intento_id_{eval_id}'] = intento_id

    preguntas_ordenadas = session[session_key]
    total_p = len(preguntas_ordenadas)
    
    page = request.args.get('page', 1, type=int)
    if page < 1 or page > total_p:
        page = 1
        
    pregunta_actual = preguntas_ordenadas[page - 1] if total_p > 0 else None
    
    # Obtener respuestas guardadas desde la base de datos
    intento_id = session.get(f'intento_id_{eval_id}')
    respuestas_guardadas = {}
    if intento_id:
        saved = db_execute(conn, 'SELECT pregunta_id, respuesta FROM respuestas_estudiante WHERE intento_id = ?', (intento_id,)).fetchall()
        for r in saved:
            respuestas_guardadas[str(r['pregunta_id'])] = r['respuesta']

    # Si es una solicitud AJAX, solo devolver el partial de la pregunta
    if request.args.get('ajax') == '1':
        return render_template('_pregunta_card.html', 
                               pregunta=pregunta_actual, 
                               page=page, 
                               total_p=total_p,
                               respuestas_guardadas=respuestas_guardadas)

    return render_template('estudiante_examen_page.html', 
                           evaluacion=evaluacion, 
                           pregunta=pregunta_actual, 
                           page=page, 
                           total_p=total_p,
                           respuestas_guardadas=respuestas_guardadas)

@app.route('/estudiante/guardar_respuesta/<int:eval_id>', methods=['POST'])
def guardar_respuesta(eval_id):
    if not session.get(f'acceso_autorizado_{eval_id}'):
        return jsonify({'status': 'unauthorized'}), 403

    data = request.json
    p_id = data.get('pregunta_id')
    resp = data.get('respuesta', '')
    intento_id = session.get(f'intento_id_{eval_id}')
    
    if not intento_id:
        return jsonify({'status': 'error', 'message': 'No hay intento activo'}), 400

    conn = get_db()
    # Eliminar respuesta previa y reinsertar (funciona en SQLite y PostgreSQL)
    db_execute(conn, 'DELETE FROM respuestas_estudiante WHERE intento_id = ? AND pregunta_id = ?', (intento_id, p_id))
    db_execute(conn, 'INSERT INTO respuestas_estudiante (intento_id, pregunta_id, respuesta) VALUES (?, ?, ?)', (intento_id, p_id, resp))
    conn.commit()
    return jsonify({'status': 'ok'})

@app.route('/estudiante/finalizar/<int:eval_id>', methods=['POST'])
def estudiante_finalizar(eval_id):
    conn = get_db()
    intento_id = session.get(f'intento_id_{eval_id}')
    # Aceptar tanto form-data como JSON
    if request.is_json:
        razon = request.json.get('razon_finalizacion', 'Completado Normal')
    else:
        razon = request.form.get('razon_finalizacion', 'Completado Normal')
    
    if not intento_id:
        return redirect(url_for('estudiante_portal'))
    
    preguntas = db_execute(conn, 'SELECT * FROM preguntas WHERE evaluacion_id = ?', (eval_id,)).fetchall()

    puntaje_obtenido_auto = 0
    puntaje_total_prueba = 0
    tiene_desarrollo = False
    preguntas_correctas = 0
    total_preguntas_auto = 0

    for p in preguntas:
        p_id = p['id']
        # Obtener respuesta del estudiante desde la base de datos
        re = db_execute(conn, 'SELECT respuesta FROM respuestas_estudiante WHERE intento_id = ? AND pregunta_id = ?', (intento_id, p_id)).fetchone()
        resp_estudiante = re['respuesta'] if re else ''
        
        puntaje_total_prueba += p['puntaje']
        es_correcta = 0

        if p['tipo'] == 'opcion_multiple':
            total_preguntas_auto += 1
            if resp_estudiante and resp_estudiante.strip().upper() == str(p['respuesta_correcta']).strip().upper():
                puntaje_obtenido_auto += p['puntaje']
                es_correcta = 1
                preguntas_correctas += 1
        elif p['tipo'] == 'verdadero_falso':
            total_preguntas_auto += 1
            resp_correcta = str(p['respuesta_correcta'] or '').strip().upper()
            resp_estudiante_norm = resp_estudiante.strip().upper() if resp_estudiante else ''
            if resp_correcta == 'A':  # Verdadero
                if resp_estudiante_norm == 'V':
                    puntaje_obtenido_auto += p['puntaje']
                    es_correcta = 1
                    preguntas_correctas += 1
            else:  # Falso (B, vacío, etc.)
                if resp_estudiante_norm == 'F':
                    puntaje_obtenido_auto += p['puntaje']
                    es_correcta = 1
                    preguntas_correctas += 1
        elif p['tipo'] == 'desarrollo':
            tiene_desarrollo = True
            # Insertar en respuestas_desarrollo para su revisión manual
            db_execute(conn, '''
                INSERT INTO respuestas_desarrollo (intento_id, pregunta_id, respuesta_texto)
                VALUES (?, ?, ?)
            ''', (intento_id, p_id, resp_estudiante))

        # Actualizar es_correcta en respuestas_estudiante
        db_execute(conn, 'UPDATE respuestas_estudiante SET es_correcta = ? WHERE intento_id = ? AND pregunta_id = ?', (es_correcta, intento_id, p_id))

    # Determinar estado_revision
    estado_revision = 'pendiente' if tiene_desarrollo else 'sin_desarrollo'

    db_execute(conn, '''
        UPDATE intentos 
        SET puntaje_autocorregido = ?, puntaje_total_auto = ?, estado = ?, estado_revision = ?
        WHERE id = ?
    ''', (puntaje_obtenido_auto, puntaje_total_prueba, razon, estado_revision, intento_id))
    conn.commit()

    # DESTRUIR LAS SESIONES PARA BLOQUEAR REINGRESO
    session.pop(f'orden_preguntas_{eval_id}', None)
    session.pop(f'acceso_autorizado_{eval_id}', None)
    session.pop(f'intento_id_{eval_id}', None)

    # Si es una solicitud AJAX (JSON), devolver JSON con el resultado
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'ok',
            'puntaje_obtenido': puntaje_obtenido_auto,
            'puntaje_total': puntaje_total_prueba,
            'preguntas_correctas': preguntas_correctas,
            'total_preguntas_auto': total_preguntas_auto,
            'intento_id': intento_id
        })

    return redirect(url_for('resultado_estudiante', intento_id=intento_id))

@app.route('/estudiante/resultado/<int:intento_id>')
def resultado_estudiante(intento_id):
    conn = get_db()
    intento = db_execute(conn, 'SELECT * FROM intentos WHERE id = ?', (intento_id,)).fetchone()
    if not intento:
        return redirect(url_for('index'))
    return render_template('resultado_estudiante.html', intento=intento)

# --- RUTAS PROFESOR ---

@app.route('/profesor')
def profesor_panel():
    conn = get_db()
    evaluaciones = db_execute(conn, 'SELECT * FROM evaluaciones').fetchall()
    
    # Para cada evaluación, contar intentos y estado de revisión
    evaluaciones_con_info = []
    for ev in evaluaciones:
        total_intentos = db_execute(conn, 'SELECT COUNT(*) as cnt FROM intentos WHERE evaluacion_id = ?', (ev['id'],)).fetchone()['cnt']
        completados = db_execute(conn, "SELECT COUNT(*) as cnt FROM intentos WHERE evaluacion_id = ? AND estado_revision = 'completado'", (ev['id'],)).fetchone()['cnt']
        pendientes = db_execute(conn, "SELECT COUNT(*) as cnt FROM intentos WHERE evaluacion_id = ? AND estado_revision = 'pendiente'", (ev['id'],)).fetchone()['cnt']
        sin_desarrollo = db_execute(conn, "SELECT COUNT(*) as cnt FROM intentos WHERE evaluacion_id = ? AND estado_revision = 'sin_desarrollo'", (ev['id'],)).fetchone()['cnt']
        
        evaluaciones_con_info.append({
            'id': ev['id'],
            'titulo': ev['titulo'],
            'seccion': ev['seccion'],
            'duracion_minutos': ev['duracion_minutos'],
            'codigo_acceso': ev['codigo_acceso'],
            'total_intentos': total_intentos,
            'completados': completados,
            'pendientes': pendientes,
            'sin_desarrollo': sin_desarrollo
        })
    
    return render_template('profesor_panel.html', evaluaciones=evaluaciones_con_info)

@app.route('/profesor/crear_evaluacion', methods=['POST'])
def crear_evaluacion():
    titulo = request.form.get('titulo')
    seccion = request.form.get('seccion')
    duracion = request.form.get('duracion_minutos', 60)
    codigo = generar_codigo_acceso()
    
    conn = get_db()
    db_execute(conn, '''
        INSERT INTO evaluaciones (titulo, seccion, duracion_minutos, codigo_acceso) 
        VALUES (?, ?, ?, ?)
    ''', (titulo, seccion, duracion, codigo))
    conn.commit()
    return redirect(url_for('profesor_panel'))

@app.route('/profesor/eliminar_evaluacion/<int:eval_id>', methods=['POST'])
def eliminar_evaluacion(eval_id):
    conn = get_db()
    db_execute(conn, 'DELETE FROM evaluaciones WHERE id = ?', (eval_id,))
    conn.commit()
    return redirect(url_for('profesor_panel'))

@app.route('/profesor/evaluacion/<int:eval_id>')
def editar_evaluacion(eval_id):
    conn = get_db()
    evaluacion = db_execute(conn, 'SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    
    preguntas_om = [dict(p) for p in db_execute(conn, "SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'opcion_multiple' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
    preguntas_vf = [dict(p) for p in db_execute(conn, "SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'verdadero_falso' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
    preguntas_des = [dict(p) for p in db_execute(conn, "SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'desarrollo' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]

    return render_template('editar_evaluacion.html', 
                           evaluacion=evaluacion, 
                           preguntas_om=preguntas_om,
                           preguntas_vf=preguntas_vf,
                           preguntas_des=preguntas_des)

@app.route('/profesor/evaluacion/<int:eval_id>/guardar_pregunta', methods=['POST'])
def guardar_pregunta(eval_id):
    pregunta_id = request.form.get('pregunta_id')
    tipo = request.form.get('tipo')
    enunciado = request.form.get('enunciado')
    puntaje = request.form.get('puntaje', 1)
    op_a = request.form.get('opcion_a')
    op_b = request.form.get('opcion_b')
    op_c = request.form.get('opcion_c')
    op_d = request.form.get('opcion_d')
    resp_correcta = request.form.get('respuesta_correcta')

    conn = get_db()
    if pregunta_id:
        db_execute(conn, '''
            UPDATE preguntas 
            SET tipo = ?, enunciado = ?, opcion_a = ?, opcion_b = ?, opcion_c = ?, opcion_d = ?, respuesta_correcta = ?, puntaje = ?
            WHERE id = ?
        ''', (tipo, enunciado, op_a, op_b, op_c, op_d, resp_correcta, puntaje, pregunta_id))
    else:
        max_orden = db_execute(conn, 'SELECT MAX(orden) as max_o FROM preguntas WHERE evaluacion_id = ? AND tipo = ?', (eval_id, tipo)).fetchone()['max_o']
        nuevo_orden = (max_orden + 1) if max_orden is not None else 1
        db_execute(conn, '''
            INSERT INTO preguntas (evaluacion_id, tipo, enunciado, opcion_a, opcion_b, opcion_c, opcion_d, respuesta_correcta, puntaje, orden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (eval_id, tipo, enunciado, op_a, op_b, op_c, op_d, resp_correcta, puntaje, nuevo_orden))
        
    conn.commit()
    return redirect(url_for('editar_evaluacion', eval_id=eval_id))

@app.route('/profesor/eliminar_pregunta/<int:pregunta_id>', methods=['POST'])
def eliminar_pregunta(pregunta_id):
    conn = get_db()
    pregunta = db_execute(conn, 'SELECT evaluacion_id FROM preguntas WHERE id = ?', (pregunta_id,)).fetchone()
    eval_id = pregunta['evaluacion_id'] if pregunta else None
    
    db_execute(conn, 'DELETE FROM preguntas WHERE id = ?', (pregunta_id,))
    conn.commit()
    if eval_id:
        return redirect(url_for('editar_evaluacion', eval_id=eval_id))
    return redirect(url_for('profesor_panel'))

@app.route('/profesor/mover_pregunta/<int:pregunta_id>/<direccion>', methods=['POST'])
def mover_pregunta(pregunta_id, direccion):
    conn = get_db()
    p_actual = db_execute(conn, 'SELECT * FROM preguntas WHERE id = ?', (pregunta_id,)).fetchone()
    if not p_actual:
        return redirect(url_for('profesor_panel'))

    eval_id = p_actual['evaluacion_id']
    tipo = p_actual['tipo']
    orden_actual = p_actual['orden']

    if direccion == 'subir':
        p_vecina = db_execute(conn, '''
            SELECT * FROM preguntas 
            WHERE evaluacion_id = ? AND tipo = ? AND orden < ? 
            ORDER BY orden DESC LIMIT 1
        ''', (eval_id, tipo, orden_actual)).fetchone()
    else:
        p_vecina = db_execute(conn, '''
            SELECT * FROM preguntas 
            WHERE evaluacion_id = ? AND tipo = ? AND orden > ? 
            ORDER BY orden ASC LIMIT 1
        ''', (eval_id, tipo, orden_actual)).fetchone()

    if p_vecina:
        db_execute(conn, 'UPDATE preguntas SET orden = ? WHERE id = ?', (p_vecina['orden'], p_actual['id']))
        db_execute(conn, 'UPDATE preguntas SET orden = ? WHERE id = ?', (orden_actual, p_vecina['id']))
        conn.commit()

    return redirect(url_for('editar_evaluacion', eval_id=eval_id))

# --- RUTA PARA VER INTENTOS DE UNA EVALUACIÓN ESPECÍFICA (CARPETA) ---

@app.route('/profesor/evaluacion/<int:eval_id>/intentos')
def intentos_evaluacion(eval_id):
    conn = get_db()
    evaluacion = db_execute(conn, 'SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    if not evaluacion:
        return redirect(url_for('profesor_panel'))
    
    intentos = db_execute(conn, '''
        SELECT i.*, e.titulo as evaluacion_titulo
        FROM intentos i JOIN evaluaciones e ON i.evaluacion_id = e.id
        WHERE i.evaluacion_id = ?
        ORDER BY i.fecha DESC
    ''', (eval_id,)).fetchall()
    
    # Para cada intento, contar respuestas correctas e incorrectas
    intentos_con_info = []
    for intento in intentos:
        correctas = db_execute(conn, 'SELECT COUNT(*) as cnt FROM respuestas_estudiante WHERE intento_id = ? AND es_correcta = 1', (intento['id'],)).fetchone()['cnt']
        total_respondidas = db_execute(conn, 'SELECT COUNT(*) as cnt FROM respuestas_estudiante WHERE intento_id = ?', (intento['id'],)).fetchone()['cnt']
        intentos_con_info.append({
            'id': intento['id'],
            'estudiante_nombre': intento['estudiante_nombre'],
            'estudiante_rut': intento['estudiante_rut'],
            'puntaje_autocorregido': intento['puntaje_autocorregido'],
            'puntaje_total_auto': intento['puntaje_total_auto'],
            'puntaje_desarrollo': intento['puntaje_desarrollo'],
            'estado_revision': intento['estado_revision'],
            'correctas': correctas,
            'total_respondidas': total_respondidas
        })
    
    return render_template('intentos_evaluacion.html', evaluacion=evaluacion, intentos=intentos_con_info)

# --- RUTAS DE REVISIÓN ---

@app.route('/profesor/revisar/<int:intento_id>', methods=['GET', 'POST'])
def revisar_desarrollo(intento_id):
    conn = get_db()
    if request.method == 'POST':
        puntaje_total_desarrollo = 0
        for key, value in request.form.items():
            if key.startswith('puntaje_'):
                resp_id = key.split('_')[1]
                pts = float(value) if value else 0
                db_execute(conn, 'UPDATE respuestas_desarrollo SET puntaje_asignado = ? WHERE id = ?', (pts, resp_id))
                puntaje_total_desarrollo += pts
        
        db_execute(conn, 'UPDATE intentos SET puntaje_desarrollo = ? WHERE id = ?', (puntaje_total_desarrollo, intento_id))
        
        # Verificar si todas las preguntas de desarrollo están calificadas
        sin_calificar = db_execute(conn, '''
            SELECT COUNT(*) as cnt FROM respuestas_desarrollo 
            WHERE intento_id = ? AND puntaje_asignado IS NULL
        ''', (intento_id,)).fetchone()['cnt']
        
        if sin_calificar == 0:
            # Todas calificadas → marcar como completado
            db_execute(conn, "UPDATE intentos SET estado_revision = 'completado' WHERE id = ?", (intento_id,))
        else:
            db_execute(conn, "UPDATE intentos SET estado_revision = 'pendiente' WHERE id = ?", (intento_id,))
        
        conn.commit()
        return redirect(url_for('profesor_panel'))

    intento = db_execute(conn, '''
        SELECT i.*, e.titulo FROM intentos i JOIN evaluaciones e ON i.evaluacion_id = e.id WHERE i.id = ?
    ''', (intento_id,)).fetchone()
    
    respuestas = db_execute(conn, '''
        SELECT rd.*, p.enunciado, p.puntaje as puntaje_maximo 
        FROM respuestas_desarrollo rd JOIN preguntas p ON rd.pregunta_id = p.id 
        WHERE rd.intento_id = ?
    ''', (intento_id,)).fetchall()

    return render_template('revisar_desarrollo.html', intento=intento, respuestas=respuestas)

@app.route('/profesor/ver_prueba/<int:intento_id>')
def ver_prueba_estudiante(intento_id):
    conn = get_db()
    
    intento = db_execute(conn, '''
        SELECT i.*, e.titulo as evaluacion_titulo, e.seccion as evaluacion_seccion
        FROM intentos i JOIN evaluaciones e ON i.evaluacion_id = e.id WHERE i.id = ?
    ''', (intento_id,)).fetchone()
    
    if not intento:
        return redirect(url_for('profesor_panel'))
    
    # Obtener preguntas de la evaluación con las respuestas del estudiante
    preguntas_om = db_execute(conn, '''
        SELECT p.*, re.respuesta as respuesta_estudiante, re.es_correcta
        FROM preguntas p
        LEFT JOIN respuestas_estudiante re ON re.pregunta_id = p.id AND re.intento_id = ?
        WHERE p.evaluacion_id = ? AND p.tipo = 'opcion_multiple'
        ORDER BY p.orden ASC, p.id ASC
    ''', (intento_id, intento['evaluacion_id'])).fetchall()
    
    preguntas_vf = db_execute(conn, '''
        SELECT p.*, re.respuesta as respuesta_estudiante, re.es_correcta
        FROM preguntas p
        LEFT JOIN respuestas_estudiante re ON re.pregunta_id = p.id AND re.intento_id = ?
        WHERE p.evaluacion_id = ? AND p.tipo = 'verdadero_falso'
        ORDER BY p.orden ASC, p.id ASC
    ''', (intento_id, intento['evaluacion_id'])).fetchall()
    
    preguntas_des = db_execute(conn, '''
        SELECT p.*, re.respuesta as respuesta_estudiante, re.es_correcta
        FROM preguntas p
        LEFT JOIN respuestas_estudiante re ON re.pregunta_id = p.id AND re.intento_id = ?
        WHERE p.evaluacion_id = ? AND p.tipo = 'desarrollo'
        ORDER BY p.orden ASC, p.id ASC
    ''', (intento_id, intento['evaluacion_id'])).fetchall()
    
    # Organizar en segmentos
    segmentos = [
        ('opcion_multiple', 'Selección Múltiple', preguntas_om),
        ('verdadero_falso', 'Verdadero o Falso', preguntas_vf),
        ('desarrollo', 'Desarrollo', preguntas_des),
    ]
    
    # Obtener puntajes de desarrollo
    respuestas_desarrollo = db_execute(conn, '''
        SELECT rd.pregunta_id, rd.puntaje_asignado
        FROM respuestas_desarrollo rd
        WHERE rd.intento_id = ?
    ''', (intento_id,)).fetchall()
    
    puntaje_desarrollo_map = {}
    for rd in respuestas_desarrollo:
        puntaje_desarrollo_map[rd['pregunta_id']] = rd['puntaje_asignado']
    
    return render_template('ver_prueba_estudiante.html', 
                           intento=intento, 
                           segmentos=segmentos,
                           puntaje_desarrollo_map=puntaje_desarrollo_map)

# Health check endpoint for deployment
@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/profesor/importar_examen', methods=['POST'])
def importar_examen():
    titulo = request.form.get('titulo')
    seccion = request.form.get('seccion')
    tiempo = request.form.get('tiempo', type=int)
    archivo_csv = request.files.get('archivo_csv')

    if not archivo_csv or not archivo_csv.filename.endswith('.csv'):
        flash('Por favor selecciona un archivo CSV válido.', 'error')
        return redirect(url_for('profesor_panel'))

    # 1. Crear la evaluación en la tabla evaluaciones
    codigo = generar_codigo_acceso()
    conn = get_db()
    evaluacion_id = db_execute_insert(conn, '''
        INSERT INTO evaluaciones (titulo, seccion, duracion_minutos, codigo_acceso)
        VALUES (?, ?, ?, ?)
    ''', (titulo, seccion, tiempo, codigo))

    # 2. Leer el CSV e insertar cada pregunta en la tabla preguntas
    content = archivo_csv.read().decode("utf-8")
    stream = io.StringIO(content)
    lector_csv = csv.DictReader(stream)

    orden = 1
    for fila in lector_csv:
        db_execute(conn, '''
            INSERT INTO preguntas (evaluacion_id, tipo, enunciado, opcion_a, opcion_b, opcion_c, opcion_d, respuesta_correcta, puntaje, orden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            evaluacion_id,
            'opcion_multiple',
            (fila.get('pregunta', '') or '').strip(),
            (fila.get('opcion_a', '') or '').strip(),
            (fila.get('opcion_b', '') or '').strip(),
            (fila.get('opcion_c', '') or '').strip(),
            (fila.get('opcion_d', '') or '').strip(),
            (fila.get('respuesta_correcta', '') or '').strip(),
            1.0,
            orden
        ))
        orden += 1

    conn.commit()
    flash('¡Examen importado exitosamente!', 'success')
    return redirect(url_for('profesor_panel'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)