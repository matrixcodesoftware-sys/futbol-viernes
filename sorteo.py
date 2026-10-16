"""
Algoritmo que arma dos equipos (Negro y Blanco) lo más parejos posible
según un puntaje de nivel de cada jugador (por defecto, sus estrellas;
también se puede balancear por cualquier otro campo numérico, por
ejemplo un puntaje combinado que incluya tasa de victoria y asistencia
— ver `calcular_pesos_sorteo` en db.py).

No es al azar: para un tamaño de equipo fijo, prueba matemáticamente
(con programación dinámica) cuál es el subconjunto de jugadores que deja
la suma de puntaje más cerca posible de la mitad del total. Por eso
siempre encuentra el mejor reparto posible, no una aproximación.
"""
import random


def _mejor_subconjunto(jugadores, k, key="stars"):
    """Encuentra, entre todos los subconjuntos de exactamente `k`
    jugadores, el que tiene la suma de `key` más cercana a la mitad
    del total. Devuelve (set de índices elegidos, suma de ese equipo)."""
    n = len(jugadores)
    max_sum = sum(j[key] for j in jugadores)

    # history[i][j][s] = True si, usando los primeros i jugadores, se
    # puede elegir exactamente j de ellos sumando s puntos.
    history = []
    prev = [[False] * (max_sum + 1) for _ in range(k + 1)]
    prev[0][0] = True
    history.append(prev)

    for i in range(n):
        valor = jugadores[i][key]
        cur = [row[:] for row in prev]
        for j in range(k + 1):
            for s in range(max_sum + 1):
                if not prev[j][s]:
                    continue
                if j + 1 <= k and s + valor <= max_sum:
                    cur[j + 1][s + valor] = True
        history.append(cur)
        prev = cur

    target = max_sum / 2
    best_sum, best_diff = 0, float("inf")
    for s in range(max_sum + 1):
        if prev[k][s]:
            diff = abs(s - target)
            if diff < best_diff:
                best_diff = diff
                best_sum = s

    # Reconstruir el subconjunto recorriendo el historial hacia atrás.
    elegidos = set()
    j, s = k, best_sum
    for i in range(n, 0, -1):
        valor = jugadores[i - 1][key]
        sin_jugador = history[i - 1][j][s]
        con_jugador = j > 0 and s - valor >= 0 and history[i - 1][j - 1][s - valor]

        if con_jugador and (not sin_jugador or random.random() < 0.5):
            elegidos.add(i - 1)
            j -= 1
            s -= valor
        elif sin_jugador:
            pass
        elif con_jugador:
            elegidos.add(i - 1)
            j -= 1
            s -= valor

    return elegidos, best_sum


def generar_sorteo(jugadores_confirmados, key="stars"):
    """jugadores_confirmados: lista de dicts con al menos {id, name, stars}
    (y el campo `key`, si es distinto de "stars" — debe ser un entero).
    Devuelve (equipo_negro, equipo_blanco), cada uno lista de esos dicts."""
    jugadores = list(jugadores_confirmados)
    random.shuffle(jugadores)
    n = len(jugadores)

    if n == 0:
        return [], []
    if n == 1:
        return jugadores, []

    k_a = n // 2
    k_b = n - k_a
    opciones = {k_a, k_b} - {0}

    total = sum(j[key] for j in jugadores)
    mejor = None
    for k in opciones:
        elegidos, suma = _mejor_subconjunto(jugadores, k, key=key)
        diff = abs(suma - (total - suma))
        if mejor is None or diff < mejor["diff"]:
            mejor = {"elegidos": elegidos, "suma": suma, "diff": diff, "k": k}

    equipo_a = [j for i, j in enumerate(jugadores) if i in mejor["elegidos"]]
    equipo_b = [j for i, j in enumerate(jugadores) if i not in mejor["elegidos"]]

    # El equipo con más jugadores (si n es impar) se llama "negro" por
    # convención.
    if len(equipo_a) >= len(equipo_b):
        return equipo_a, equipo_b
    return equipo_b, equipo_a
