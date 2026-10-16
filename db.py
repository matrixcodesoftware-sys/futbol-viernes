"""
Todo lo relacionado a la base de datos SQLite.

Usa el módulo sqlite3 de la biblioteca estándar de Python (no hace falta
instalar ningún motor de base de datos aparte). Los datos quedan en un
único archivo (por defecto "futbolviernes.db" en esta misma carpeta).
"""
import os
import sqlite3
import uuid
from datetime import date, timedelta

import click
from flask import current_app, g

# Si DATABASE_PATH (en .env) es relativo, lo resolvemos SIEMPRE respecto
# a esta carpeta (donde está este archivo db.py) — no respecto a la
# carpeta desde la que se haya arrancado el servidor. Sin esto, si algún
# día corrés `flask run` parado un nivel más arriba (o VS Code abre otra
# carpeta como raíz), Python crea sin avisar una base nueva y vacía ahí,
# y de golpe "nadie puede ingresar" porque no encuentra a los usuarios
# reales — quedan a salvo en el archivo de siempre, solo que la app está
# mirando el archivo equivocado.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolver_database_path():
    ruta = os.environ.get("DATABASE_PATH", "futbolviernes.db")
    if not os.path.isabs(ruta):
        ruta = os.path.join(_BASE_DIR, ruta)
    return ruta


DATABASE_PATH = _resolver_database_path()


def get_db():
    """Devuelve la conexión a la base para el request actual (se abre una
    sola vez por request y se reutiliza)."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_columns(db, table, columnas):
    """Agrega columnas nuevas a una tabla que ya existe, sin tocar los
    datos. Sirve para que una base vieja (creada con una versión
    anterior de la app) se ponga al día sola la próxima vez que corra,
    sin que el usuario tenga que borrar nada ni correr comandos."""
    existentes = {fila["name"] for fila in db.execute(f"PRAGMA table_info({table})")}
    for nombre, definicion in columnas.items():
        if nombre not in existentes:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {nombre} {definicion}")


def init_db():
    """Crea las tablas si todavía no existen, y agrega columnas nuevas a
    una base vieja si hace falta."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    _ensure_columns(
        db,
        "users",
        {
            "wins_adj": "INTEGER NOT NULL DEFAULT 0",
            "draws_adj": "INTEGER NOT NULL DEFAULT 0",
            "losses_adj": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    _ensure_columns(
        db,
        "match_teams",
        {"goals": "INTEGER NOT NULL DEFAULT 0"},
    )
    db.commit()


def new_id():
    return uuid.uuid4().hex


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


@click.command("init-db")
def init_db_command():
    """Comando `flask --app app init-db`: crea las tablas."""
    init_db()
    click.echo("Base de datos lista.")


# ---------------------------------------------------------------------
# Configuración (código de invitación)
# ---------------------------------------------------------------------

def get_invite_code():
    db = get_db()
    row = db.execute(
        "SELECT value FROM settings WHERE key = 'invite_code'"
    ).fetchone()
    if row:
        return row["value"]
    default = os.environ.get("INVITE_CODE_DEFAULT", "FUTBOLVIERNES")
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('invite_code', ?)",
        (default,),
    )
    db.commit()
    return default


def set_invite_code(code):
    db = get_db()
    db.execute(
        """
        INSERT INTO settings (key, value) VALUES ('invite_code', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (code,),
    )
    db.commit()


# ---------------------------------------------------------------------
# Configuración (cupo de titulares — para la lista de espera)
# ---------------------------------------------------------------------

def get_cupo():
    db = get_db()
    row = db.execute(
        "SELECT value FROM settings WHERE key = 'cupo_titulares'"
    ).fetchone()
    if row:
        return int(row["value"])
    default = int(os.environ.get("CUPO_TITULARES_DEFAULT", "14"))
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('cupo_titulares', ?)",
        (str(default),),
    )
    db.commit()
    return default


def set_cupo(n):
    db = get_db()
    db.execute(
        """
        INSERT INTO settings (key, value) VALUES ('cupo_titulares', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(n),),
    )
    db.commit()


# ---------------------------------------------------------------------
# Partidos
# ---------------------------------------------------------------------

def proximo_viernes():
    """Solo se usa para sugerir una fecha al abrir el formulario de
    'crear partido' — el admin puede cambiarla por cualquier otro día."""
    d = date.today()
    while d.weekday() != 4:  # lunes=0 ... viernes=4
        d += timedelta(days=1)
    return d.isoformat()


def create_match(date_str):
    """Crea un partido nuevo para la fecha indicada (YYYY-MM-DD). El admin
    puede crear más de uno por semana (ej: martes y viernes)."""
    db = get_db()
    match_id = new_id()
    db.execute(
        "INSERT INTO matches (id, date, status) VALUES (?, ?, 'ABIERTO')",
        (match_id, date_str),
    )
    db.commit()
    return db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()


def get_match(match_id):
    db = get_db()
    return db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()


def get_upcoming_matches():
    """Partidos todavía no jugados (abiertos para confirmar asistencia o
    ya sorteados), ordenados por fecha. Puede haber varios a la vez."""
    db = get_db()
    return db.execute(
        "SELECT * FROM matches WHERE status IN ('ABIERTO', 'SORTEADO') ORDER BY date ASC"
    ).fetchall()


def get_sorteado_matches():
    db = get_db()
    return db.execute(
        "SELECT * FROM matches WHERE status = 'SORTEADO' ORDER BY date ASC"
    ).fetchall()


def cancel_match(match_id):
    db = get_db()
    db.execute("UPDATE matches SET status = 'CANCELADO' WHERE id = ?", (match_id,))
    db.commit()


def delete_match(match_id):
    """Borra un partido por completo (asistencia y equipos incluidos, por
    el ON DELETE CASCADE del esquema). Se usa para limpiar partidos de
    prueba o cargados por error del historial — el ranking se recalcula
    solo, restando lo que ese partido sumaba."""
    db = get_db()
    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()


def get_confirmed_players(match_id):
    """Jugadores confirmados para un partido, en el orden en que confirmaron
    (el primero en confirmar es el primero de la lista) — así se puede
    separar titulares de lista de espera según el cupo."""
    db = get_db()
    return db.execute(
        """
        SELECT u.id, u.name, u.stars, u.photo_url
        FROM attendance a
        JOIN users u ON u.id = a.user_id
        WHERE a.match_id = ?
        ORDER BY a.created_at ASC
        """,
        (match_id,),
    ).fetchall()


def get_available_players(match_id):
    """Jugadores activos que todavía no están anotados en este partido —
    para que el admin los pueda anotar a mano (ej: avisaron por WhatsApp
    y no entran a la app)."""
    db = get_db()
    return db.execute(
        """
        SELECT u.id, u.name
        FROM users u
        WHERE u.active = 1
          AND u.id NOT IN (SELECT user_id FROM attendance WHERE match_id = ?)
        ORDER BY u.name
        """,
        (match_id,),
    ).fetchall()


def get_jugadores_fuera_del_partido(match_id):
    """Jugadores activos que todavía no están en ninguno de los dos
    equipos de este partido — para agregarlos al corregir un partido ya
    jugado (a diferencia de get_available_players, esto mira los equipos
    ya armados, no la lista de confirmados)."""
    db = get_db()
    return db.execute(
        """
        SELECT u.id, u.name
        FROM users u
        WHERE u.active = 1
          AND u.id NOT IN (SELECT user_id FROM match_teams WHERE match_id = ?)
        ORDER BY u.name
        """,
        (match_id,),
    ).fetchall()


def get_teams(match_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT u.id, u.name, u.stars, u.photo_url, mt.team, mt.goals
        FROM match_teams mt
        JOIN users u ON u.id = mt.user_id
        WHERE mt.match_id = ?
        ORDER BY u.name
        """,
        (match_id,),
    ).fetchall()
    negro = [r for r in rows if r["team"] == "NEGRO"]
    blanco = [r for r in rows if r["team"] == "BLANCO"]
    return negro, blanco


def get_ranking():
    """Ranking = lo que la app registró jugando partidos acá adentro, más
    el historial anterior que haya cargado el admin a mano (wins_adj /
    draws_adj / losses_adj, ej: lo que tenían anotado en un Excel)."""
    db = get_db()
    jugadores = db.execute(
        "SELECT id, name, photo_url, stars, wins_adj, draws_adj, losses_adj "
        "FROM users WHERE active = 1"
    ).fetchall()

    partidos = db.execute(
        """
        SELECT mt.user_id, mt.team, mt.goals, m.winner
        FROM match_teams mt
        JOIN matches m ON m.id = mt.match_id
        WHERE m.status = 'JUGADO'
        """
    ).fetchall()

    ranking = []
    for j in jugadores:
        propios = [p for p in partidos if p["user_id"] == j["id"]]
        ganados_app = len([p for p in propios if p["winner"] == p["team"]])
        empatados_app = len([p for p in propios if p["winner"] == "EMPATE"])
        perdidos_app = len(propios) - ganados_app - empatados_app
        goles = sum(p["goals"] for p in propios)

        ganados = ganados_app + j["wins_adj"]
        empatados = empatados_app + j["draws_adj"]
        perdidos = perdidos_app + j["losses_adj"]
        jugados = ganados + empatados + perdidos
        porcentaje = round((ganados / jugados) * 100) if jugados > 0 else 0
        ranking.append(
            {
                "id": j["id"],
                "name": j["name"],
                "photo_url": j["photo_url"],
                "jugados": jugados,
                "ganados": ganados,
                "empatados": empatados,
                "perdidos": perdidos,
                "porcentaje": porcentaje,
                "goles": goles,
            }
        )

    ranking.sort(key=lambda r: (-r["ganados"], -r["porcentaje"]))
    return ranking


def calcular_pesos_sorteo(jugadores_confirmados):
    """Combina, con el mismo peso cada uno, las estrellas, la tasa de
    victoria y la cantidad de partidos jugados (asistencia) de cada
    jugador confirmado, para usar como criterio de balanceo del sorteo
    (en vez de balancear solo por estrellas).

    Devuelve una copia de `jugadores_confirmados` con un campo extra
    'peso' (entero) agregado a cada jugador — no toca el campo 'stars'
    original, que se sigue usando para mostrar las estrellitas en
    pantalla.

    A los jugadores sin partidos jugados todavía no se los perjudica:
    en vez de darles el peor puntaje posible en tasa de victoria y
    asistencia (por falta de datos), se les asigna un valor neutro
    (mitad de tabla).
    """
    ranking_por_id = {r["id"]: r for r in get_ranking()}

    max_jugados = max(
        (ranking_por_id.get(j["id"], {}).get("jugados", 0) for j in jugadores_confirmados),
        default=0,
    )

    resultado = []
    for jugador in jugadores_confirmados:
        j = dict(jugador)
        datos = ranking_por_id.get(j["id"])
        jugados = datos["jugados"] if datos else 0

        estrellas_norm = (j["stars"] - 1) / 4 * 10  # 1..5 estrellas -> 0..10

        if jugados == 0:
            tasa_norm = 5.0  # todavía no jugó ningún partido: valor neutro
        else:
            tasa_norm = (datos["porcentaje"] / 100) * 10

        asistencia_norm = (jugados / max_jugados * 10) if max_jugados > 0 else 5.0

        peso = round((estrellas_norm + tasa_norm + asistencia_norm) / 3)
        j["peso"] = max(0, peso)
        resultado.append(j)

    return resultado


def contar_partidos_jugados():
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM matches WHERE status = 'JUGADO'"
    ).fetchone()
    return row["n"]


def get_historial(desde=None, hasta=None, ganador=None, limite=None):
    """Partidos jugados, más nuevos primero. `desde`/`hasta` son fechas
    'YYYY-MM-DD' (funciona comparándolas como texto porque las fechas se
    guardan en ese mismo formato). `ganador` filtra por NEGRO/BLANCO/
    EMPATE. `limite` corta la cantidad de resultados (para no volcar todo
    el historial de una si no se pidió ningún filtro)."""
    db = get_db()
    query = "SELECT * FROM matches WHERE status = 'JUGADO'"
    params = []
    if desde:
        query += " AND date >= ?"
        params.append(desde)
    if hasta:
        query += " AND date <= ?"
        params.append(hasta)
    if ganador in ("NEGRO", "BLANCO", "EMPATE"):
        query += " AND winner = ?"
        params.append(ganador)
    query += " ORDER BY date DESC"
    if limite:
        query += " LIMIT ?"
        params.append(limite)

    partidos = db.execute(query, params).fetchall()

    resultado = []
    for m in partidos:
        negro, blanco = get_teams(m["id"])
        resultado.append({"match": m, "negro": negro, "blanco": blanco})
    return resultado
