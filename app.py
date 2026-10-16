"""
Fútbol de los Viernes — app Flask (Python) + HTML/CSS/JS.

Para correrla:
    pip install -r requirements.txt
    flask --app app run --debug

Mirá el README.md para el paso a paso completo.
"""
import calendar
import os
import re
import unicodedata
import urllib.parse
import uuid
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import db as dbmod
from auth import admin_required, current_user, es_admin_por_email, login_required
from sorteo import generar_sorteo

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-cambiar")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB por archivo subido

UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
FOTO_EXTENSIONES = {"png", "jpg", "jpeg", "gif", "webp"}

dbmod.init_app(app)

# Crea las tablas si todavía no existen, para no tener que correr un
# comando aparte la primera vez.
with app.app_context():
    dbmod.init_db()


# ---------------------------------------------------------------------
# Helpers de plantillas
# ---------------------------------------------------------------------

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def formato_fecha_es(iso_date_str):
    d = date.fromisoformat(iso_date_str)
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]}"


app.jinja_env.filters["fecha_es"] = formato_fecha_es


@app.context_processor
def inject_user():
    return {"usuario_actual": current_user()}


# ---------------------------------------------------------------------
# Home / raíz
# ---------------------------------------------------------------------

@app.route("/")
def index():
    if current_user():
        return redirect(url_for("partido"))
    return redirect(url_for("login"))


# ---------------------------------------------------------------------
# Registro / login / logout
# ---------------------------------------------------------------------

def _sugerir_usuario(db, name):
    """A partir del nombre arma un usuario simple para loguearse (sin
    tildes ni espacios, ej: 'Juan Pérez' -> 'juan.perez'), agregando un
    número al final si ya hay alguien con ese mismo usuario. Se usa para
    que el admin pueda crear jugadores sin tener que inventarle un usuario
    a cada uno."""
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-zA-Z0-9]+", ".", base).strip(".").lower()
    if not base:
        base = "jugador"
    usuario = base
    i = 1
    while db.execute("SELECT id FROM users WHERE email = ?", (usuario,)).fetchone():
        i += 1
        usuario = f"{base}{i}"
    return usuario


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("partido"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirmPassword", "")
        invite_code = request.form.get("inviteCode", "").strip()

        error = None
        if not name or not email or not password:
            error = "Completá todos los campos."
        elif len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif password != confirm_password:
            error = "Las contraseñas no coinciden."
        else:
            codigo_valido = dbmod.get_invite_code()
            if not invite_code or invite_code.upper() != codigo_valido.upper():
                error = (
                    "El código de invitación es incorrecto. "
                    "Pedíselo al organizador del partido."
                )

        db = dbmod.get_db()
        if error is None:
            existente = db.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existente:
                error = "Ya existe una cuenta con ese email."

        if error:
            return render_template("register.html", error=error, form=request.form)

        user_id = dbmod.new_id()
        role = "ADMIN" if es_admin_por_email(email) else "JUGADOR"
        db.execute(
            """
            INSERT INTO users (id, name, email, password_hash, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name, email, generate_password_hash(password), role),
        )
        db.commit()

        session.clear()
        session["user_id"] = user_id
        return redirect(url_for("partido"))

    return render_template("register.html", error=None, form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("partido"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        db = dbmod.get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not user:
            error = "Email o contraseña incorrectos."
        elif not user["active"]:
            error = "Tu cuenta fue dada de baja. Consultá con el organizador."
        elif not check_password_hash(user["password_hash"], password):
            error = "Email o contraseña incorrectos."

        if error:
            return render_template("login.html", error=error)

        session.clear()
        session["user_id"] = user["id"]
        return redirect(url_for("partido"))

    return render_template("login.html", error=None)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------
# Jugador: partido y perfil
# ---------------------------------------------------------------------

@app.route("/partido")
@login_required
def partido():
    uid = current_user()["id"]
    cupo = dbmod.get_cupo()
    partidos = []
    for match in dbmod.get_upcoming_matches():
        confirmados = dbmod.get_confirmed_players(match["id"])
        titulares = confirmados[:cupo]
        espera = confirmados[cupo:]
        ya_confirmado = any(c["id"] == uid for c in confirmados)
        en_espera = any(c["id"] == uid for c in espera)
        partidos.append(
            {
                "match": match,
                "titulares": titulares,
                "espera": espera,
                "cupo": cupo,
                "ya_confirmado": ya_confirmado,
                "en_espera": en_espera,
            }
        )
    return render_template("partido.html", partidos=partidos)


@app.route("/partido/confirmar", methods=["POST"])
@login_required
def partido_confirmar():
    match_id = request.form.get("matchId")
    user = current_user()
    db = dbmod.get_db()
    db.execute(
        "INSERT OR IGNORE INTO attendance (id, match_id, user_id) VALUES (?, ?, ?)",
        (dbmod.new_id(), match_id, user["id"]),
    )
    db.commit()
    return redirect(url_for("partido"))


@app.route("/partido/cancelar", methods=["POST"])
@login_required
def partido_cancelar():
    match_id = request.form.get("matchId")
    user = current_user()
    db = dbmod.get_db()
    db.execute(
        "DELETE FROM attendance WHERE match_id = ? AND user_id = ?",
        (match_id, user["id"]),
    )
    db.commit()
    return redirect(url_for("partido"))


@app.route("/perfil")
@login_required
def perfil():
    user = current_user()
    ranking = dbmod.get_ranking()
    stats = next((r for r in ranking if r["id"] == user["id"]), None)
    puesto = ranking.index(stats) + 1 if stats else None
    return render_template(
        "perfil.html", stats=stats, puesto=puesto, total_jugadores=len(ranking)
    )


@app.route("/perfil/editar", methods=["POST"])
@login_required
def perfil_editar():
    user = current_user()
    name = request.form.get("name", "").strip()
    current_password = request.form.get("currentPassword", "")
    new_password = request.form.get("newPassword", "")
    confirm_new_password = request.form.get("confirmNewPassword", "")

    if not name:
        flash("El nombre no puede quedar vacío.", "error")
        return redirect(url_for("perfil"))

    db = dbmod.get_db()
    quiere_cambiar_password = bool(current_password or new_password or confirm_new_password)

    if quiere_cambiar_password:
        if not check_password_hash(user["password_hash"], current_password):
            flash("La contraseña actual no es correcta.", "error")
            return redirect(url_for("perfil"))
        if len(new_password) < 6:
            flash("La contraseña nueva debe tener al menos 6 caracteres.", "error")
            return redirect(url_for("perfil"))
        if new_password != confirm_new_password:
            flash("Las contraseñas nuevas no coinciden.", "error")
            return redirect(url_for("perfil"))
        db.execute(
            "UPDATE users SET name = ?, password_hash = ? WHERE id = ?",
            (name, generate_password_hash(new_password), user["id"]),
        )
        flash("¡Datos y contraseña actualizados!", "success")
    else:
        db.execute("UPDATE users SET name = ? WHERE id = ?", (name, user["id"]))
        flash("¡Datos actualizados!", "success")

    db.commit()
    return redirect(url_for("perfil"))


@app.route("/perfil/foto", methods=["POST"])
@login_required
def perfil_foto():
    user = current_user()
    file = request.files.get("foto")

    if not file or file.filename == "":
        flash("Elegí una foto para subir.", "error")
        return redirect(url_for("perfil"))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in FOTO_EXTENSIONES:
        flash("El archivo tiene que ser una imagen (jpg, png, gif o webp).", "error")
        return redirect(url_for("perfil"))

    filename = secure_filename(f"{user['id']}_{uuid.uuid4().hex}.{ext}")
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    db = dbmod.get_db()
    db.execute(
        "UPDATE users SET photo_url = ? WHERE id = ?",
        (f"uploads/{filename}", user["id"]),
    )
    db.commit()
    flash("¡Foto actualizada!", "success")
    return redirect(url_for("perfil"))


# ---------------------------------------------------------------------
# Admin: resumen
# ---------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_home():
    cupo = dbmod.get_cupo()
    partidos = []
    for match in dbmod.get_upcoming_matches():
        confirmados = dbmod.get_confirmed_players(match["id"])
        titulares = confirmados[:cupo]
        espera = confirmados[cupo:]
        texto_whatsapp = (
            f"⚽ Partido el {formato_fecha_es(match['date'])}. "
            f"Entrá a confirmar si vas: {request.host_url}"
        )
        whatsapp_url = "https://wa.me/?text=" + urllib.parse.quote(texto_whatsapp)
        partidos.append(
            {
                "match": match,
                "titulares": titulares,
                "espera": espera,
                "cupo": cupo,
                "whatsapp_url": whatsapp_url,
            }
        )
    return render_template(
        "admin_home.html", partidos=partidos, fecha_sugerida=dbmod.proximo_viernes()
    )


@app.route("/admin/partidos/crear", methods=["POST"])
@admin_required
def admin_partidos_crear():
    fecha = request.form.get("fecha", "").strip()
    try:
        date.fromisoformat(fecha)
    except ValueError:
        flash("La fecha no es válida.", "error")
        return redirect(url_for("admin_home"))

    dbmod.create_match(fecha)
    flash("¡Partido creado! Ya lo pueden confirmar los jugadores.", "success")
    return redirect(url_for("admin_home"))


@app.route("/admin/partidos/<match_id>/cancelar", methods=["POST"])
@admin_required
def admin_partidos_cancelar(match_id):
    dbmod.cancel_match(match_id)
    flash("Partido cancelado.", "success")
    return redirect(url_for("admin_home"))


# ---------------------------------------------------------------------
# Admin: jugadores (estrellas, código de invitación, roles, altas/bajas)
# ---------------------------------------------------------------------

@app.route("/admin/jugadores")
@admin_required
def admin_jugadores():
    db = dbmod.get_db()
    jugadores = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    invite_code = dbmod.get_invite_code()
    cupo = dbmod.get_cupo()
    return render_template(
        "admin_jugadores.html", jugadores=jugadores, invite_code=invite_code, cupo=cupo
    )


@app.route("/admin/jugadores/crear", methods=["POST"])
@admin_required
def admin_jugadores_crear():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()

    if not name:
        flash("Ponele un nombre al jugador.", "error")
        return redirect(url_for("admin_jugadores"))

    db = dbmod.get_db()

    if email:
        existente = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existente:
            flash(f"Ya existe un jugador con el usuario \"{email}\".", "error")
            return redirect(url_for("admin_jugadores"))
    else:
        email = _sugerir_usuario(db, name)

    if not password:
        password = "123456"
    elif len(password) < 6:
        flash("Si le ponés contraseña, tiene que tener al menos 6 caracteres.", "error")
        return redirect(url_for("admin_jugadores"))

    user_id = dbmod.new_id()
    role = "ADMIN" if es_admin_por_email(email) else "JUGADOR"
    db.execute(
        """
        INSERT INTO users (id, name, email, password_hash, role)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, name, email, generate_password_hash(password), role),
    )
    db.commit()

    flash(
        f"¡Jugador \"{name}\" creado! Usuario: {email} · Contraseña: {password} "
        "— avisale así puede entrar (y cambiar la contraseña desde su perfil cuando quiera).",
        "success",
    )
    return redirect(url_for("admin_jugadores"))


@app.route("/admin/jugadores/<user_id>/editar", methods=["GET", "POST"])
@admin_required
def admin_jugador_editar(user_id):
    db = dbmod.get_db()
    jugador = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not jugador:
        abort(404)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not name or not email:
            flash("El nombre y el usuario no pueden quedar vacíos.", "error")
            return redirect(url_for("admin_jugador_editar", user_id=user_id))

        existente = db.execute(
            "SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)
        ).fetchone()
        if existente:
            flash(f"Ya existe otro jugador con el usuario \"{email}\".", "error")
            return redirect(url_for("admin_jugador_editar", user_id=user_id))

        if password and len(password) < 6:
            flash("Si le ponés una contraseña nueva, tiene que tener al menos 6 caracteres.", "error")
            return redirect(url_for("admin_jugador_editar", user_id=user_id))

        if password:
            db.execute(
                "UPDATE users SET name = ?, email = ?, password_hash = ? WHERE id = ?",
                (name, email, generate_password_hash(password), user_id),
            )
        else:
            db.execute(
                "UPDATE users SET name = ?, email = ? WHERE id = ?",
                (name, email, user_id),
            )
        db.commit()
        flash(f"¡Datos de \"{name}\" actualizados!", "success")
        return redirect(url_for("admin_jugadores"))

    return render_template("admin_jugador_editar.html", jugador=jugador)


@app.route("/admin/jugadores/<user_id>/eliminar", methods=["POST"])
@admin_required
def admin_jugador_eliminar(user_id):
    admin = current_user()
    if user_id == admin["id"]:
        flash("No te podés eliminar a vos mismo.", "error")
        return redirect(url_for("admin_jugadores"))

    db = dbmod.get_db()
    jugador = db.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
    if jugador:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        flash(f"Jugador \"{jugador['name']}\" eliminado.", "success")
    return redirect(url_for("admin_jugadores"))


@app.route("/admin/jugadores/estrellas", methods=["POST"])
@admin_required
def admin_jugadores_estrellas():
    user_id = request.form.get("userId")
    try:
        stars = int(request.form.get("stars", ""))
    except ValueError:
        stars = None

    if user_id and stars and 1 <= stars <= 5:
        db = dbmod.get_db()
        db.execute("UPDATE users SET stars = ? WHERE id = ?", (stars, user_id))
        db.commit()

    return redirect(url_for("admin_jugadores"))


@app.route("/admin/jugadores/rol", methods=["POST"])
@admin_required
def admin_jugadores_rol():
    user_id = request.form.get("userId")
    admin = current_user()
    if user_id and user_id != admin["id"]:
        db = dbmod.get_db()
        target = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if target:
            nuevo_rol = "JUGADOR" if target["role"] == "ADMIN" else "ADMIN"
            db.execute("UPDATE users SET role = ? WHERE id = ?", (nuevo_rol, user_id))
            db.commit()

    return redirect(url_for("admin_jugadores"))


@app.route("/admin/jugadores/activo", methods=["POST"])
@admin_required
def admin_jugadores_activo():
    user_id = request.form.get("userId")
    admin = current_user()
    if user_id and user_id != admin["id"]:
        db = dbmod.get_db()
        target = db.execute("SELECT active FROM users WHERE id = ?", (user_id,)).fetchone()
        if target:
            db.execute(
                "UPDATE users SET active = ? WHERE id = ?",
                (0 if target["active"] else 1, user_id),
            )
            db.commit()

    return redirect(url_for("admin_jugadores"))


@app.route("/admin/jugadores/codigo", methods=["POST"])
@admin_required
def admin_jugadores_codigo():
    code = request.form.get("inviteCode", "").strip()
    if code:
        dbmod.set_invite_code(code)
    return redirect(url_for("admin_jugadores"))


@app.route("/admin/jugadores/cupo", methods=["POST"])
@admin_required
def admin_jugadores_cupo():
    try:
        cupo = int(request.form.get("cupo", ""))
    except ValueError:
        cupo = None

    if cupo and cupo > 0:
        dbmod.set_cupo(cupo)
        flash("Cupo de titulares actualizado.", "success")
    else:
        flash("El cupo tiene que ser un número mayor a 0.", "error")

    return redirect(url_for("admin_jugadores"))


# ---------------------------------------------------------------------
# Admin: historial anterior (partidos jugados antes de usar la app)
# ---------------------------------------------------------------------

@app.route("/admin/historial-previo")
@admin_required
def admin_historial_previo():
    db = dbmod.get_db()
    jugadores = db.execute(
        "SELECT id, name, wins_adj, draws_adj, losses_adj "
        "FROM users WHERE active = 1 ORDER BY name"
    ).fetchall()
    return render_template("admin_historial_previo.html", jugadores=jugadores)


@app.route("/admin/historial-previo/guardar", methods=["POST"])
@admin_required
def admin_historial_previo_guardar():
    db = dbmod.get_db()
    jugadores = db.execute("SELECT id FROM users WHERE active = 1").fetchall()

    def numero(campo, user_id):
        try:
            return max(0, int(request.form.get(f"{campo}_{user_id}", "0") or "0"))
        except ValueError:
            return 0

    for j in jugadores:
        db.execute(
            "UPDATE users SET wins_adj = ?, draws_adj = ?, losses_adj = ? WHERE id = ?",
            (
                numero("wins", j["id"]),
                numero("draws", j["id"]),
                numero("losses", j["id"]),
                j["id"],
            ),
        )
    db.commit()
    flash("¡Historial anterior guardado! Ya se suma al ranking.", "success")
    return redirect(url_for("admin_historial_previo"))


# ---------------------------------------------------------------------
# Admin: sorteo
# ---------------------------------------------------------------------

@app.route("/admin/sorteo")
@admin_required
def admin_sorteo():
    partidos = dbmod.get_upcoming_matches()
    if len(partidos) == 1:
        return redirect(url_for("admin_sorteo_ver", match_id=partidos[0]["id"]))
    return render_template(
        "admin_elegir_partido.html",
        titulo="Sorteo — elegí el partido",
        vacio_mensaje="No hay partidos programados todavía. Creá uno primero.",
        partidos=partidos,
        destino="admin_sorteo_ver",
    )


@app.route("/admin/sorteo/<match_id>")
@admin_required
def admin_sorteo_ver(match_id):
    match = dbmod.get_match(match_id)
    if not match:
        abort(404)
    cupo = dbmod.get_cupo()
    confirmados_todos = dbmod.get_confirmed_players(match["id"])
    confirmados = confirmados_todos[:cupo]
    espera = confirmados_todos[cupo:]
    disponibles = dbmod.get_available_players(match["id"])
    negro, blanco = dbmod.get_teams(match["id"])
    suma_negro = sum(j["stars"] for j in negro)
    suma_blanco = sum(j["stars"] for j in blanco)
    equipo_por_id = {j["id"]: "NEGRO" for j in negro}
    equipo_por_id.update({j["id"]: "BLANCO" for j in blanco})
    return render_template(
        "admin_sorteo.html",
        match=match,
        confirmados=confirmados,
        espera=espera,
        disponibles=disponibles,
        negro=negro,
        blanco=blanco,
        suma_negro=suma_negro,
        suma_blanco=suma_blanco,
        equipo_por_id=equipo_por_id,
        hay_equipos=(len(negro) + len(blanco)) > 0,
    )


@app.route("/admin/asistencia/agregar", methods=["POST"])
@admin_required
def admin_asistencia_agregar():
    match_id = request.form.get("matchId")
    user_id = request.form.get("userId")
    if match_id and user_id:
        db = dbmod.get_db()
        db.execute(
            "INSERT OR IGNORE INTO attendance (id, match_id, user_id) VALUES (?, ?, ?)",
            (dbmod.new_id(), match_id, user_id),
        )
        db.commit()
    return redirect(url_for("admin_sorteo_ver", match_id=match_id))


@app.route("/admin/asistencia/quitar", methods=["POST"])
@admin_required
def admin_asistencia_quitar():
    match_id = request.form.get("matchId")
    user_id = request.form.get("userId")
    if match_id and user_id:
        db = dbmod.get_db()
        db.execute(
            "DELETE FROM attendance WHERE match_id = ? AND user_id = ?",
            (match_id, user_id),
        )
        db.commit()
    return redirect(url_for("admin_sorteo_ver", match_id=match_id))


@app.route("/admin/sorteo/generar", methods=["POST"])
@admin_required
def admin_sorteo_generar():
    match_id = request.form.get("matchId")
    cupo = dbmod.get_cupo()
    confirmados = dbmod.get_confirmed_players(match_id)[:cupo]
    if len(confirmados) >= 2:
        jugadores = dbmod.calcular_pesos_sorteo([dict(row) for row in confirmados])
        negro, blanco = generar_sorteo(jugadores, key="peso")

        db = dbmod.get_db()
        db.execute("DELETE FROM match_teams WHERE match_id = ?", (match_id,))
        for j in negro:
            db.execute(
                "INSERT INTO match_teams (id, match_id, user_id, team) VALUES (?, ?, ?, 'NEGRO')",
                (dbmod.new_id(), match_id, j["id"]),
            )
        for j in blanco:
            db.execute(
                "INSERT INTO match_teams (id, match_id, user_id, team) VALUES (?, ?, ?, 'BLANCO')",
                (dbmod.new_id(), match_id, j["id"]),
            )
        db.execute("UPDATE matches SET status = 'SORTEADO' WHERE id = ?", (match_id,))
        db.commit()

    return redirect(url_for("admin_sorteo_ver", match_id=match_id))


@app.route("/admin/sorteo/asignar", methods=["POST"])
@admin_required
def admin_sorteo_asignar():
    """Asigna a mano un jugador confirmado a Equipo Negro o Blanco, sin
    esperar al sorteo automático — para cuando el admin prefiere armar los
    equipos jugador por jugador. Si el jugador ya estaba en un equipo, lo
    cambia de equipo en vez de duplicarlo."""
    match_id = request.form.get("matchId")
    user_id = request.form.get("userId")
    equipo = request.form.get("equipo")

    if match_id and user_id and equipo in ("NEGRO", "BLANCO"):
        db = dbmod.get_db()
        db.execute(
            """
            INSERT INTO match_teams (id, match_id, user_id, team)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(match_id, user_id) DO UPDATE SET team = excluded.team
            """,
            (dbmod.new_id(), match_id, user_id, equipo),
        )
        # Al asignar el primer jugador a mano, el partido ya queda
        # "sorteado" — así se puede cargar el resultado más adelante.
        db.execute(
            "UPDATE matches SET status = 'SORTEADO' WHERE id = ? AND status = 'ABIERTO'",
            (match_id,),
        )
        db.commit()

    return redirect(url_for("admin_sorteo_ver", match_id=match_id))


@app.route("/admin/sorteo/mover", methods=["POST"])
@admin_required
def admin_sorteo_mover():
    match_id = request.form.get("matchId")
    user_id = request.form.get("userId")
    equipo = request.form.get("equipo")

    if match_id and user_id and equipo in ("NEGRO", "BLANCO"):
        db = dbmod.get_db()
        db.execute(
            "UPDATE match_teams SET team = ? WHERE match_id = ? AND user_id = ?",
            (equipo, match_id, user_id),
        )
        db.commit()

    return redirect(url_for("admin_sorteo_ver", match_id=match_id))


@app.route("/admin/sorteo/deshacer", methods=["POST"])
@admin_required
def admin_sorteo_deshacer():
    match_id = request.form.get("matchId")
    if match_id:
        db = dbmod.get_db()
        db.execute("DELETE FROM match_teams WHERE match_id = ?", (match_id,))
        db.execute("UPDATE matches SET status = 'ABIERTO' WHERE id = ?", (match_id,))
        db.commit()

    return redirect(url_for("admin_sorteo_ver", match_id=match_id))


# ---------------------------------------------------------------------
# Admin: resultado
# ---------------------------------------------------------------------

@app.route("/admin/resultado")
@admin_required
def admin_resultado():
    partidos = dbmod.get_sorteado_matches()
    if len(partidos) == 1:
        return redirect(url_for("admin_resultado_ver", match_id=partidos[0]["id"]))
    return render_template(
        "admin_elegir_partido.html",
        titulo="Resultado — elegí el partido",
        vacio_mensaje="No hay partidos sorteados todavía. Primero sorteá los equipos en la pestaña \"Sorteo\".",
        partidos=partidos,
        destino="admin_resultado_ver",
    )


@app.route("/admin/resultado/<match_id>")
@admin_required
def admin_resultado_ver(match_id):
    match = dbmod.get_match(match_id)
    if not match:
        abort(404)
    negro, blanco = dbmod.get_teams(match["id"])
    return render_template("admin_resultado.html", match=match, negro=negro, blanco=blanco)


@app.route("/admin/resultado/cargar", methods=["POST"])
@admin_required
def admin_resultado_cargar():
    match_id = request.form.get("matchId")
    ganador = request.form.get("ganador")

    if match_id and ganador in ("NEGRO", "BLANCO", "EMPATE"):
        db = dbmod.get_db()
        db.execute(
            "UPDATE matches SET winner = ?, status = 'JUGADO' WHERE id = ?",
            (ganador, match_id),
        )
        db.commit()
        flash("¡Resultado cargado! Ya quedó registrado en el ranking.", "success")

    return redirect(url_for("admin_home"))


# ---------------------------------------------------------------------
# Admin: ranking e historial
# ---------------------------------------------------------------------

@app.route("/admin/ranking")
@admin_required
def admin_ranking():
    ranking = dbmod.get_ranking()
    return render_template("admin_ranking.html", ranking=ranking)


@app.route("/admin/historial")
@admin_required
def admin_historial():
    semana = request.args.get("semana", "").strip()
    mes = request.args.get("mes", "").strip()
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    ganador = request.args.get("ganador", "").strip()
    ver_todos = request.args.get("todos") == "1"

    # "Semana" y "mes" son atajos: se convierten a un rango desde/hasta
    # para la consulta. Si el admin eligió una semana, esa gana sobre
    # cualquier "desde"/"hasta" que haya tipeado a mano.
    desde_filtro = desde or None
    hasta_filtro = hasta or None

    if semana:
        try:
            lunes = datetime.strptime(f"{semana}-1", "%G-W%V-%u").date()
            desde_filtro = lunes.isoformat()
            hasta_filtro = (lunes + timedelta(days=6)).isoformat()
        except ValueError:
            flash("La semana elegida no es válida.", "error")
    elif mes:
        try:
            anio_str, mes_str = mes.split("-")
            anio, mes_num = int(anio_str), int(mes_str)
            ultimo_dia = calendar.monthrange(anio, mes_num)[1]
            desde_filtro = date(anio, mes_num, 1).isoformat()
            hasta_filtro = date(anio, mes_num, ultimo_dia).isoformat()
        except (ValueError, IndexError):
            flash("El mes elegido no es válido.", "error")

    hay_filtro = bool(semana or mes or desde or hasta or ganador)
    total_jugados = dbmod.contar_partidos_jugados()

    if hay_filtro or ver_todos:
        historial = dbmod.get_historial(
            desde=desde_filtro, hasta=hasta_filtro, ganador=ganador or None
        )
    else:
        # Por defecto no volcamos todo el historial de una: mostramos
        # solo los últimos partidos, y el admin busca el resto con los
        # filtros (o toca "Ver todos").
        historial = dbmod.get_historial(limite=10)

    return render_template(
        "admin_historial.html",
        historial=historial,
        total_jugados=total_jugados,
        hay_filtro=hay_filtro,
        ver_todos=ver_todos,
        f_semana=semana,
        f_mes=mes,
        f_desde=desde,
        f_hasta=hasta,
        f_ganador=ganador,
    )


@app.route("/admin/historial/<match_id>/borrar", methods=["POST"])
@admin_required
def admin_historial_borrar(match_id):
    dbmod.delete_match(match_id)
    flash("Partido borrado del historial. El ranking se actualizó.", "success")
    return redirect(url_for("admin_historial"))


# ---------------------------------------------------------------------
# Admin: corregir un partido ya jugado (jugadores mal anotados, etc.)
# ---------------------------------------------------------------------

@app.route("/admin/historial/<match_id>/editar")
@admin_required
def admin_historial_editar_form(match_id):
    match = dbmod.get_match(match_id)
    if not match:
        abort(404)
    negro, blanco = dbmod.get_teams(match_id)
    disponibles = dbmod.get_jugadores_fuera_del_partido(match_id)
    return render_template(
        "admin_historial_editar.html",
        match=match,
        negro=negro,
        blanco=blanco,
        disponibles=disponibles,
    )


@app.route("/admin/historial/<match_id>/fecha", methods=["POST"])
@admin_required
def admin_historial_fecha_cambiar(match_id):
    fecha = request.form.get("fecha", "").strip()
    try:
        date.fromisoformat(fecha)
    except ValueError:
        flash("La fecha no es válida.", "error")
        return redirect(url_for("admin_historial_editar_form", match_id=match_id))

    db = dbmod.get_db()
    db.execute("UPDATE matches SET date = ? WHERE id = ?", (fecha, match_id))
    db.commit()
    flash("Fecha actualizada.", "success")
    return redirect(url_for("admin_historial_editar_form", match_id=match_id))


@app.route("/admin/historial/<match_id>/ganador", methods=["POST"])
@admin_required
def admin_historial_ganador_cambiar(match_id):
    ganador = request.form.get("ganador")
    if ganador in ("NEGRO", "BLANCO", "EMPATE"):
        db = dbmod.get_db()
        db.execute(
            "UPDATE matches SET winner = ?, status = 'JUGADO' WHERE id = ?",
            (ganador, match_id),
        )
        db.commit()
        flash("Resultado corregido. El ranking se actualizó.", "success")

    return redirect(url_for("admin_historial_editar_form", match_id=match_id))


@app.route("/admin/historial/<match_id>/jugador/agregar", methods=["POST"])
@admin_required
def admin_historial_jugador_agregar(match_id):
    user_id = request.form.get("userId")
    equipo = request.form.get("equipo")
    if user_id and equipo in ("NEGRO", "BLANCO"):
        db = dbmod.get_db()
        db.execute(
            """
            INSERT INTO match_teams (id, match_id, user_id, team)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(match_id, user_id) DO UPDATE SET team = excluded.team
            """,
            (dbmod.new_id(), match_id, user_id, equipo),
        )
        db.commit()

    return redirect(url_for("admin_historial_editar_form", match_id=match_id))


@app.route("/admin/historial/<match_id>/jugador/mover", methods=["POST"])
@admin_required
def admin_historial_jugador_mover(match_id):
    user_id = request.form.get("userId")
    equipo = request.form.get("equipo")
    if user_id and equipo in ("NEGRO", "BLANCO"):
        db = dbmod.get_db()
        db.execute(
            "UPDATE match_teams SET team = ? WHERE match_id = ? AND user_id = ?",
            (equipo, match_id, user_id),
        )
        db.commit()

    return redirect(url_for("admin_historial_editar_form", match_id=match_id))


@app.route("/admin/historial/<match_id>/goles", methods=["POST"])
@admin_required
def admin_historial_goles_guardar(match_id):
    db = dbmod.get_db()
    negro, blanco = dbmod.get_teams(match_id)

    for j in list(negro) + list(blanco):
        campo = f"goles_{j['id']}"
        if campo not in request.form:
            continue
        try:
            goles = max(0, int(request.form.get(campo, "0") or "0"))
        except ValueError:
            goles = 0
        db.execute(
            "UPDATE match_teams SET goals = ? WHERE match_id = ? AND user_id = ?",
            (goles, match_id, j["id"]),
        )
    db.commit()
    flash("¡Goles guardados! Ya se suman al ranking de goleadores.", "success")
    return redirect(url_for("admin_historial_editar_form", match_id=match_id))


@app.route("/admin/historial/<match_id>/jugador/quitar", methods=["POST"])
@admin_required
def admin_historial_jugador_quitar(match_id):
    user_id = request.form.get("userId")
    if user_id:
        db = dbmod.get_db()
        db.execute(
            "DELETE FROM match_teams WHERE match_id = ? AND user_id = ?",
            (match_id, user_id),
        )
        db.commit()

    return redirect(url_for("admin_historial_editar_form", match_id=match_id))


if __name__ == "__main__":
    # host="0.0.0.0" hace que la app escuche en toda la red local, no
    # solo en esta PC, para poder abrirla también desde el celular
    # (mismo WiFi) yendo a la IP de esta compu, ej: http://192.168.0.15:5000
    app.run(host="0.0.0.0", debug=True)
