import os
import random
import string
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response

base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get('SECRET_KEY', 'neurociencias_udp_secret_key_2026_v5')

# Database path - use environment variable or default to project directory
DATABASE = os.environ.get('DATABASE_URL', os.path.join(base_dir, 'database.db'))

# If DATABASE_URL is a SQLite path (not a URL), use it directly
# If it's a postgres:// URL, we'd need to adapt, but for simplicity we keep SQLite
if DATABASE.startswith('sqlite:///'):
    DATABASE = DATABASE.replace('sqlite:///', '')
elif DATABASE.startswith('sqlite://'):
    DATABASE = DATABASE.replace('sqlite://', '')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def generar_codigo_acceso():
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(6))

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS evaluaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                seccion TEXT NOT NULL,
                duracion_minutos INTEGER DEFAULT 60,
                codigo_acceso TEXT NOT NULL
            )
        ''')
        cursor.execute('''
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
        cursor.execute('''
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
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (evaluacion_id) REFERENCES evaluaciones (id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
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
        cursor.execute('''
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
    evaluaciones = conn.execute('SELECT * FROM evaluaciones').fetchall()
    return render_template('estudiante_portal.html', evaluaciones=evaluaciones)

@app.route('/estudiante/ingreso/<int:eval_id>', methods=['GET', 'POST'])
def estudiante_ingreso(eval_id):
    conn = get_db()
    evaluacion = conn.execute('SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
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
    evaluacion = conn.execute('SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    preguntas = conn.execute('SELECT * FROM preguntas WHERE evaluacion_id = ?', (eval_id,)).fetchall()
    
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
    # SI NO TIENE ACCESO AUTORIZADO (O YA FINALIZÓ), REDIRIGIR AL PORTAL
    if not session.get(f'acceso_autorizado_{eval_id}'):
        return redirect(url_for('estudiante_portal'))

    conn = get_db()
    evaluacion = conn.execute('SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    
    session_key = f'orden_preguntas_{eval_id}'
    if session_key not in session:
        om = [dict(p) for p in conn.execute("SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'opcion_multiple' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
        vf = [dict(p) for p in conn.execute("SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'verdadero_falso' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
        des = [dict(p) for p in conn.execute("SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'desarrollo' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
        
        random.shuffle(om)
        random.shuffle(vf)
        random.shuffle(des)
        
        preguntas_ordenadas = om + vf + des
        session[session_key] = preguntas_ordenadas
        session[f'respuestas_{eval_id}'] = {}

    preguntas_ordenadas = session[session_key]
    total_p = len(preguntas_ordenadas)
    
    page = request.args.get('page', 1, type=int)
    if page < 1 or page > total_p:
        page = 1
        
    pregunta_actual = preguntas_ordenadas[page - 1] if total_p > 0 else None
    respuestas_guardadas = session.get(f'respuestas_{eval_id}', {})

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
    p_id = str(data.get('pregunta_id'))
    resp = data.get('respuesta')
    
    respuestas_key = f'respuestas_{eval_id}'
    respuestas = session.get(respuestas_key, {})
    respuestas[p_id] = resp
    session[respuestas_key] = respuestas
    session.modified = True
    return jsonify({'status': 'ok'})

@app.route('/estudiante/finalizar/<int:eval_id>', methods=['POST'])
def estudiante_finalizar(eval_id):
    conn = get_db()
    nombre = session.get('estudiante_nombre', 'Estudiante Desconocido')
    rut = session.get('estudiante_rut', 'Sin RUT')
    seccion = session.get('estudiante_seccion', 'Sin Sección')
    razon = request.form.get('razon_finalizacion', 'Completado Normal')
    
    respuestas = session.get(f'respuestas_{eval_id}', {})
    preguntas = conn.execute('SELECT * FROM preguntas WHERE evaluacion_id = ?', (eval_id,)).fetchall()

    puntaje_obtenido_auto = 0
    puntaje_total_prueba = 0

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO intentos (evaluacion_id, estudiante_nombre, estudiante_rut, seccion, estado)
        VALUES (?, ?, ?, ?, ?)
    ''', (eval_id, nombre, rut, seccion, razon))
    intento_id = cursor.lastrowid

    for p in preguntas:
        p_id = str(p['id'])
        resp_estudiante = respuestas.get(p_id, '')
        puntaje_total_prueba += p['puntaje']
        es_correcta = 0

        if p['tipo'] in ['opcion_multiple', 'verdadero_falso']:
            if resp_estudiante and resp_estudiante.strip().upper() == str(p['respuesta_correcta']).strip().upper():
                puntaje_obtenido_auto += p['puntaje']
                es_correcta = 1
        elif p['tipo'] == 'desarrollo':
            cursor.execute('''
                INSERT INTO respuestas_desarrollo (intento_id, pregunta_id, respuesta_texto)
                VALUES (?, ?, ?)
            ''', (intento_id, p['id'], resp_estudiante))

        # Guardar todas las respuestas en respuestas_estudiante
        cursor.execute('''
            INSERT INTO respuestas_estudiante (intento_id, pregunta_id, respuesta, es_correcta)
            VALUES (?, ?, ?, ?)
        ''', (intento_id, p['id'], resp_estudiante, es_correcta))

    cursor.execute('''
        UPDATE intentos 
        SET puntaje_autocorregido = ?, puntaje_total_auto = ?
        WHERE id = ?
    ''', (puntaje_obtenido_auto, puntaje_total_prueba, intento_id))
    conn.commit()

    # DESTRUIR LAS SESIONES PARA BLOQUEAR REINGRESO
    session.pop(f'orden_preguntas_{eval_id}', None)
    session.pop(f'respuestas_{eval_id}', None)
    session.pop(f'acceso_autorizado_{eval_id}', None)

    return redirect(url_for('resultado_estudiante', intento_id=intento_id))

@app.route('/estudiante/resultado/<int:intento_id>')
def resultado_estudiante(intento_id):
    conn = get_db()
    intento = conn.execute('SELECT * FROM intentos WHERE id = ?', (intento_id,)).fetchone()
    if not intento:
        return redirect(url_for('index'))
    return render_template('resultado_estudiante.html', intento=intento)

# --- RUTAS PROFESOR ---

@app.route('/profesor')
def profesor_panel():
    conn = get_db()
    evaluaciones = conn.execute('SELECT * FROM evaluaciones').fetchall()
    intentos = conn.execute('''
        SELECT i.*, e.titulo as evaluacion_titulo 
        FROM intentos i JOIN evaluaciones e ON i.evaluacion_id = e.id 
        ORDER BY i.fecha DESC
    ''').fetchall()
    return render_template('profesor_panel.html', evaluaciones=evaluaciones, intentos=intentos)

@app.route('/profesor/crear_evaluacion', methods=['POST'])
def crear_evaluacion():
    titulo = request.form.get('titulo')
    seccion = request.form.get('seccion')
    duracion = request.form.get('duracion_minutos', 60)
    codigo = generar_codigo_acceso()
    
    conn = get_db()
    conn.execute('''
        INSERT INTO evaluaciones (titulo, seccion, duracion_minutos, codigo_acceso) 
        VALUES (?, ?, ?, ?)
    ''', (titulo, seccion, duracion, codigo))
    conn.commit()
    return redirect(url_for('profesor_panel'))

@app.route('/profesor/eliminar_evaluacion/<int:eval_id>', methods=['POST'])
def eliminar_evaluacion(eval_id):
    conn = get_db()
    conn.execute('DELETE FROM evaluaciones WHERE id = ?', (eval_id,))
    conn.commit()
    return redirect(url_for('profesor_panel'))

@app.route('/profesor/evaluacion/<int:eval_id>')
def editar_evaluacion(eval_id):
    conn = get_db()
    evaluacion = conn.execute('SELECT * FROM evaluaciones WHERE id = ?', (eval_id,)).fetchone()
    
    preguntas_om = [dict(p) for p in conn.execute("SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'opcion_multiple' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
    preguntas_vf = [dict(p) for p in conn.execute("SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'verdadero_falso' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]
    preguntas_des = [dict(p) for p in conn.execute("SELECT * FROM preguntas WHERE evaluacion_id = ? AND tipo = 'desarrollo' ORDER BY orden ASC, id ASC", (eval_id,)).fetchall()]

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
        conn.execute('''
            UPDATE preguntas 
            SET tipo = ?, enunciado = ?, opcion_a = ?, opcion_b = ?, opcion_c = ?, opcion_d = ?, respuesta_correcta = ?, puntaje = ?
            WHERE id = ?
        ''', (tipo, enunciado, op_a, op_b, op_c, op_d, resp_correcta, puntaje, pregunta_id))
    else:
        max_orden = conn.execute('SELECT MAX(orden) as max_o FROM preguntas WHERE evaluacion_id = ? AND tipo = ?', (eval_id, tipo)).fetchone()['max_o']
        nuevo_orden = (max_orden + 1) if max_orden is not None else 1
        conn.execute('''
            INSERT INTO preguntas (evaluacion_id, tipo, enunciado, opcion_a, opcion_b, opcion_c, opcion_d, respuesta_correcta, puntaje, orden)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (eval_id, tipo, enunciado, op_a, op_b, op_c, op_d, resp_correcta, puntaje, nuevo_orden))
        
    conn.commit()
    return redirect(url_for('editar_evaluacion', eval_id=eval_id))

@app.route('/profesor/eliminar_pregunta/<int:pregunta_id>', methods=['POST'])
def eliminar_pregunta(pregunta_id):
    conn = get_db()
    pregunta = conn.execute('SELECT evaluacion_id FROM preguntas WHERE id = ?', (pregunta_id,)).fetchone()
    eval_id = pregunta['evaluacion_id'] if pregunta else None
    
    conn.execute('DELETE FROM preguntas WHERE id = ?', (pregunta_id,))
    conn.commit()
    if eval_id:
        return redirect(url_for('editar_evaluacion', eval_id=eval_id))
    return redirect(url_for('profesor_panel'))

@app.route('/profesor/mover_pregunta/<int:pregunta_id>/<direccion>', methods=['POST'])
def mover_pregunta(pregunta_id, direccion):
    conn = get_db()
    p_actual = conn.execute('SELECT * FROM preguntas WHERE id = ?', (pregunta_id,)).fetchone()
    if not p_actual:
        return redirect(url_for('profesor_panel'))

    eval_id = p_actual['evaluacion_id']
    tipo = p_actual['tipo']
    orden_actual = p_actual['orden']

    if direccion == 'subir':
        p_vecina = conn.execute('''
            SELECT * FROM preguntas 
            WHERE evaluacion_id = ? AND tipo = ? AND orden < ? 
            ORDER BY orden DESC LIMIT 1
        ''', (eval_id, tipo, orden_actual)).fetchone()
    else:
        p_vecina = conn.execute('''
            SELECT * FROM preguntas 
            WHERE evaluacion_id = ? AND tipo = ? AND orden > ? 
            ORDER BY orden ASC LIMIT 1
        ''', (eval_id, tipo, orden_actual)).fetchone()

    if p_vecina:
        conn.execute('UPDATE preguntas SET orden = ? WHERE id = ?', (p_vecina['orden'], p_actual['id']))
        conn.execute('UPDATE preguntas SET orden = ? WHERE id = ?', (orden_actual, p_vecina['id']))
        conn.commit()

    return redirect(url_for('editar_evaluacion', eval_id=eval_id))

@app.route('/profesor/revisar/<int:intento_id>', methods=['GET', 'POST'])
def revisar_desarrollo(intento_id):
    conn = get_db()
    if request.method == 'POST':
        puntaje_total_desarrollo = 0
        for key, value in request.form.items():
            if key.startswith('puntaje_'):
                resp_id = key.split('_')[1]
                pts = float(value) if value else 0
                conn.execute('UPDATE respuestas_desarrollo SET puntaje_asignado = ? WHERE id = ?', (pts, resp_id))
                puntaje_total_desarrollo += pts
        
        conn.execute('UPDATE intentos SET puntaje_desarrollo = ? WHERE id = ?', (puntaje_total_desarrollo, intento_id))
        conn.commit()
        return redirect(url_for('profesor_panel'))

    intento = conn.execute('''
        SELECT i.*, e.titulo FROM intentos i JOIN evaluaciones e ON i.evaluacion_id = e.id WHERE i.id = ?
    ''', (intento_id,)).fetchone()
    
    respuestas = conn.execute('''
        SELECT rd.*, p.enunciado, p.puntaje as puntaje_maximo 
        FROM respuestas_desarrollo rd JOIN preguntas p ON rd.pregunta_id = p.id 
        WHERE rd.intento_id = ?
    ''', (intento_id,)).fetchall()

    return render_template('revisar_desarrollo.html', intento=intento, respuestas=respuestas)

@app.route('/profesor/ver_prueba/<int:intento_id>')
def ver_prueba_estudiante(intento_id):
    conn = get_db()
    
    intento = conn.execute('''
        SELECT i.*, e.titulo as evaluacion_titulo, e.seccion as evaluacion_seccion
        FROM intentos i JOIN evaluaciones e ON i.evaluacion_id = e.id WHERE i.id = ?
    ''', (intento_id,)).fetchone()
    
    if not intento:
        return redirect(url_for('profesor_panel'))
    
    # Obtener preguntas de la evaluación con las respuestas del estudiante
    preguntas = conn.execute('''
        SELECT p.*, re.respuesta as respuesta_estudiante, re.es_correcta
        FROM preguntas p
        LEFT JOIN respuestas_estudiante re ON re.pregunta_id = p.id AND re.intento_id = ?
        WHERE p.evaluacion_id = ?
        ORDER BY p.orden ASC, p.id ASC
    ''', (intento_id, intento['evaluacion_id'])).fetchall()
    
    # Obtener puntajes de desarrollo
    respuestas_desarrollo = conn.execute('''
        SELECT rd.pregunta_id, rd.puntaje_asignado
        FROM respuestas_desarrollo rd
        WHERE rd.intento_id = ?
    ''', (intento_id,)).fetchall()
    
    puntaje_desarrollo_map = {}
    for rd in respuestas_desarrollo:
        puntaje_desarrollo_map[rd['pregunta_id']] = rd['puntaje_asignado']
    
    return render_template('ver_prueba_estudiante.html', 
                           intento=intento, 
                           preguntas=preguntas,
                           puntaje_desarrollo_map=puntaje_desarrollo_map)

# Health check endpoint for deployment
@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)