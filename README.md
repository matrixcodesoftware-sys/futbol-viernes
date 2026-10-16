# ⚽ Fútbol de los Viernes (Python + HTML + CSS + JS)

Aplicación web para organizar los partidos 7 vs 7 de los viernes: los
jugadores se anotan, el organizador valora a cada uno con estrellas, el
sistema sortea equipos parejos (Negro vs Blanco), se carga quién ganó y
queda un ranking histórico de partidos ganados.

Hecha con **Python (Flask)** en el servidor, **HTML** con plantillas
Jinja, **CSS** plano (sin frameworks) y algo de **JavaScript** del propio
navegador (formularios nativos). La base de datos es **SQLite**: un solo
archivo (`futbolviernes.db`) que se crea solo, sin instalar ningún motor
aparte. No usa Node/npm ni build para nada — es Python puro.

## Dashboards

- **Dashboard jugador** (`/partido`): cada jugador ve el próximo viernes
  y toca un botón para anotarse ("voy" / "no voy"). También tiene
  `/perfil` para subir su foto.
- **Dashboard admin** (`/admin`): el organizador valora a cada jugador
  con estrellas, genera el sorteo balanceado el día del partido, puede
  mover manualmente a alguien de equipo, carga el equipo ganador al
  terminar, y ve el ranking y el historial. Los jugadores comunes no ven
  nada de esto — solo quien tiene rol admin.
- **Sorteo parejo**: prueba matemáticamente (no al azar) todas las
  combinaciones posibles y elige la que deja la suma de estrellas más
  pareja entre los dos equipos, respetando 7 vs 7 (o el número que haya
  confirmado ese viernes).
- **Código de invitación**: nadie puede crear una cuenta sin el código
  que vos definís y podés cambiar cuando quieras desde el dashboard
  admin.

## Probarla en tu computadora (VS Code)

Necesitás [Python](https://www.python.org/downloads/) 3.10 o más nuevo
(al instalarlo en Windows, tildá la opción "Add Python to PATH").

1. Descomprimí el proyecto y abrí la carpeta en VS Code.
2. Abrí una terminal (Terminal → New Terminal) y creá un entorno virtual
   (esto mantiene las librerías de este proyecto separadas del resto de
   tu compu):

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

   **Mac / Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   Vas a ver `(.venv)` al principio de la línea de la terminal cuando
   esté activado. Tenés que activarlo cada vez que abras una terminal
   nueva para trabajar en el proyecto.

3. Instalá las dependencias (son solo dos: Flask y python-dotenv):

   ```bash
   pip install -r requirements.txt
   ```

4. Copiá el archivo de variables de entorno:

   **Windows:** `copy .env.example .env`
   **Mac/Linux:** `cp .env.example .env`

   Con los valores por defecto ya alcanza para probarla. Si querés, abrí
   `.env` y poné tu email en `ADMIN_EMAILS` para que esa cuenta quede
   como administradora apenas te registres.

5. Corré la app:

   ```bash
   flask --app app run --debug
   ```

   El flag `--debug` hace que la app se recargue sola en el navegador
   cada vez que guardás un cambio en el código — ideal para ir probando
   mientras seguimos agregando cosas.

6. Entrá a http://127.0.0.1:5000, registrate con el email que pusiste en
   `ADMIN_EMAILS` y el código `INVITE_CODE_DEFAULT` (por defecto
   `VIERNES2026`) — vas a quedar como administrador.

La primera vez que corre, la app crea sola el archivo `futbolviernes.db`
con todas las tablas. Si en algún momento querés arrancar de cero,
cerrá el servidor y borrá ese archivo — se vuelve a crear vacío la
próxima vez que corras `flask run`.

## Usarla desde el celular (mientras la tenés corriendo en tu PC)

Esto sirve para probarla desde tu teléfono ahora mismo, sin subirla a
internet — el celular y la PC tienen que estar conectados al **mismo
WiFi**.

1. Levantá la app indicando que escuche en toda la red, no solo en tu
   PC (fijate que cambia el comando: se agrega `--host=0.0.0.0`):

   ```bash
   flask --app app run --host=0.0.0.0 --debug
   ```

2. La primera vez, Windows va a preguntarte si permitís que Python
   acceda a redes privadas — tocá **"Permitir acceso"** (si no te
   dejás, el celular no va a poder conectarse).

3. Buscá la IP local de tu PC. En una terminal de Windows (puede ser
   la misma de VS Code) corré:

   ```powershell
   ipconfig
   ```

   Buscá el bloque "Adaptador de LAN inalámbrica Wi-Fi" y anotá el
   número que dice **Dirección IPv4** (algo como `192.168.0.15`).

4. En el celular (conectado al mismo WiFi), abrí el navegador y entrá
   a `http://` + esa IP + `:5000`, por ejemplo:

   ```
   http://192.168.0.15:5000
   ```

Mientras la terminal de VS Code siga corriendo el servidor, la app va a
estar disponible para cualquier dispositivo de esa misma red WiFi. Si
cerrás la terminal, se corta. Esto es solo para probarla en casa — para
que tus amigos la usen desde sus casas hace falta publicarla online
(siguiente sección).

## Subirla online

Como todo queda en un archivo (`futbolviernes.db` y las fotos en
`static/uploads/`), necesitás un hosting con **disco persistente** —
o sea, que no sea "serverless" puro (los free tier de Vercel/Netlify,
por ejemplo, no sirven para esto porque no guardan archivos entre
requests). Sirven bien: un VPS propio, Render, Railway, PythonAnywhere,
Fly.io, o tu propia PC con un servicio de túnel/DNS dinámico.

Pasos generales (van a variar un poco según el hosting que elijas):

1. Subí el proyecto (por ejemplo a un repositorio de GitHub).
2. En el servidor: `pip install -r requirements.txt` y, además, un
   servidor de producción (Flask lo pide): `pip install gunicorn`.
3. Variables de entorno en el hosting: las mismas de `.env.example`,
   pero con un `SESSION_SECRET` distinto y secreto (por ejemplo
   generado con `python -c "import secrets; print(secrets.token_hex(32))"`).
4. Comando para levantarla en producción (en vez de `flask run`, que es
   solo para desarrollo):
   ```bash
   gunicorn -w 2 -b 0.0.0.0:8000 app:app
   ```
5. Configurá el hosting para que el disco donde queden
   `futbolviernes.db` y `static/uploads/` sea persistente (no se borre
   en cada deploy), y hacé backups de `futbolviernes.db` de vez en
   cuando.
6. Conectá tu dominio gratuito desde el panel del hosting que elijas.

Si me contás qué hosting vas a usar te ayudo a dejarla lista paso a
paso para ese en particular.

## Estructura del proyecto

- `app.py` — todas las rutas de la app (páginas y acciones de los
  formularios).
- `db.py` — conexión a SQLite y todas las consultas (jugadores,
  partidos, ranking, etc.).
- `auth.py` — sesión de usuario, `login_required` / `admin_required`.
- `sorteo.py` — algoritmo que arma los equipos parejos.
- `schema.sql` — estructura de las tablas de la base de datos.
- `templates/` — las páginas HTML (Jinja2).
- `static/style.css` — todos los estilos.
- `static/uploads/` — ahí se guardan las fotos de perfil.

## Notas de seguridad

- Solo puede crear una cuenta quien tenga el código de invitación
  vigente. Si el código se filtra, cambialo desde el dashboard admin
  (a los que ya se registraron no les afecta).
- Un admin puede "dar de baja" a alguien puntual desde **Admin →
  Jugadores**: no borra su historial, pero ya no puede iniciar sesión.
- En producción, usá un `SESSION_SECRET` distinto y secreto al de
  desarrollo — es lo que firma las cookies de sesión. Nunca lo subas a
  un repositorio público.
