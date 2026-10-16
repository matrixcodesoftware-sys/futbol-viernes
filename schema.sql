-- Esquema de la base de datos SQLite de Fútbol de los Viernes.
-- Se ejecuta solo (crea las tablas si no existen) la primera vez que
-- corre la app, así que no hace falta correr nada a mano.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'JUGADOR',     -- 'ADMIN' | 'JUGADOR'
    photo_url TEXT,                            -- ruta relativa dentro de static/
    stars INTEGER NOT NULL DEFAULT 3,          -- 1 a 5
    active INTEGER NOT NULL DEFAULT 1,         -- 1 = activo, 0 = dado de baja
    -- partidos ganados/empatados/perdidos de ANTES de usar la app (ej:
    -- lo que tenían anotado en un Excel) — se suman a lo que la app
    -- registra de acá en adelante para que el ranking arranque al día.
    wins_adj INTEGER NOT NULL DEFAULT 0,
    draws_adj INTEGER NOT NULL DEFAULT 0,
    losses_adj INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,                        -- 'YYYY-MM-DD', el viernes del partido
    status TEXT NOT NULL DEFAULT 'ABIERTO',     -- ABIERTO | SORTEADO | JUGADO | CANCELADO
    winner TEXT,                                -- NEGRO | BLANCO | EMPATE | NULL
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (match_id, user_id)
);

CREATE TABLE IF NOT EXISTS match_teams (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team TEXT NOT NULL,                         -- NEGRO | BLANCO
    goals INTEGER NOT NULL DEFAULT 0,           -- goles de ese jugador en ese partido
    UNIQUE (match_id, user_id)
);
