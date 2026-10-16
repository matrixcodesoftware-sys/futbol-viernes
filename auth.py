"""Helpers de sesión / autenticación (usa las cookies de sesión firmadas
que trae Flask, no hace falta ninguna librería aparte)."""
import os
from functools import wraps

from flask import g, redirect, session, url_for

from db import get_db


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    if "user" not in g:
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        g.user = row if (row and row["active"]) else None

    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("login"))
        if user["role"] != "ADMIN":
            return redirect(url_for("partido"))
        return view(*args, **kwargs)

    return wrapped


def es_admin_por_email(email):
    admins = [
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "").split(",")
        if e.strip()
    ]
    return email.strip().lower() in admins
