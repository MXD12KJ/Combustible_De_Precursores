import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.request
import uuid
from collections import defaultdict, deque
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Secret key: set SECRET_KEY as an environment variable in production so
# sessions survive server restarts. If it's not set, we generate a random
# one at startup — safer than a hardcoded default, but it does mean every
# restart logs baristas out.
# ---------------------------------------------------------------------------
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ---------------------------------------------------------------------------
# Session cookie hardening.
# SESSION_COOKIE_SECURE should be True once this is served over HTTPS
# (set the FLASK_HTTPS=1 environment variable when you deploy behind TLS).
# ---------------------------------------------------------------------------
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_HTTPS") == "1",
    # 32 KB request cap — plenty for this form, blocks oversized payloads
    MAX_CONTENT_LENGTH=32 * 1024,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_FILE = os.path.join(DATA_DIR, "orders.json")
REMOVED_ITEMS_FILE = os.path.join(DATA_DIR, "removed_items.json")
CUSTOM_ITEMS_FILE = os.path.join(DATA_DIR, "custom_items.json")
STORE_STATUS_FILE = os.path.join(DATA_DIR, "store_status.json")
ORDER_LOG_FILE = os.path.join(DATA_DIR, "order_log.json")

BARISTA_USERNAME = os.environ.get("BARISTA_USERNAME", "South Bend Spanish")
BARISTA_PASSWORD = os.environ.get("BARISTA_PASSWORD", "2tim4:5")

_file_lock = threading.Lock()

MAX_CUSTOM_ITEMS_PER_CATEGORY = 25

# Data-driven menu definition. Each category maps to the question shown,
# the input type, whether it's required, and its list of selectable choices.
# This is the fixed base menu — baristas can additionally add/remove their
# own custom items per category, stored separately in custom_items.json.
OPTIONS = {
    "temp": {
        "question": "Caliente o frio?",
        "type": "radio",
        "required": True,
        "choices": [
            {"value": "Caliente", "label": "Caliente (Hot)",
             "note": "Las bebidas calientes vienen con dos shots de espresso."},
            {"value": "Frio", "label": "Frio (Cold)",
             "note": "Las bebidas frias vienen con un shot de espresso."},
        ],
    },
    "drink": {
        "question": "Tipo de bebida",
        "type": "radio",
        "required": True,
        "choices": [
            {"value": "Latte", "label": "Latte"},
            {"value": "Americano", "label": "Americano"},
            {"value": "Flat White", "label": "Flat White"},
            {"value": "Cappucino", "label": "Cappucino"},
            {"value": "Shakin' Espresso", "label": "Shakin' Espresso",
             "note": "(Solo disponible con bebidas frias)", "cold_only": True},
        ],
    },
    "jarave": {
        "question": "Jarave",
        "type": "radio",
        "required": True,
        "choices": [
            {"value": "Avellana", "label": "Avellana (Hazelnut)"},
            {"value": "Arandano", "label": "Arandano (Blueberry)"},
            {"value": "Fresa", "label": "Fresa (Strawberry)"},
            {"value": "Caramelo", "label": "Caramelo"},
            {"value": "Chai", "label": "Chai"},
        ],
    },
    "milk": {
        "question": "Leche",
        "type": "radio",
        "required": True,
        "choices": [
            {"value": "Entera", "label": "Whole"},
            {"value": "2%", "label": "2%"},
            {"value": "Leche de Avena", "label": "Oat milk"},
            {"value": "Leche de Almendra", "label": "Almond Milk"},
        ],
    },
    "whip": {
        "question": "Whip Cream?",
        "type": "radio",
        "required": True,
        "choices": [
            {"value": "Si", "label": "Si (Yes)"},
            {"value": "No", "label": "No"},
        ],
    },
    "drizzle": {
        "question": "Drizzle",
        "type": "checkbox",
        "required": False,
        "choices": [
            {"value": "Ninguno", "label": "None"},
            {"value": "Chocolate", "label": "Chocolate"},
            {"value": "Caramelo", "label": "Caramelo"},
            {"value": "Fresa", "label": "Fresa"},
        ],
    },
}


def is_base_choice(category, value):
    """True if value is one of the fixed, built-in menu options."""
    return category in OPTIONS and any(c["value"] == value for c in OPTIONS[category]["choices"])


def is_valid_choice(category, value, custom_items):
    """True if value is either a base option or a barista-added custom one."""
    if is_base_choice(category, value):
        return True
    return category in OPTIONS and any(c["value"] == value for c in custom_items.get(category, []))


def display_value(category, value, custom_items):
    """What to store/show for a submitted value. Base items keep their
    existing internal value (unchanged historical behavior). Custom items
    get resolved to the human-readable label the barista typed, since their
    internal value is just an opaque id like 'custom_a1b2c3'."""
    if is_base_choice(category, value):
        return value
    for c in custom_items.get(category, []):
        if c["value"] == value:
            return c["label"]
    return value


def build_display_options(custom_items):
    """Merge the fixed OPTIONS with any barista-added custom items, tagging
    each choice so the template can tell base items and custom items apart."""
    display = {}
    for category, config in OPTIONS.items():
        choices = [dict(c, is_custom=False) for c in config["choices"]]
        for c in custom_items.get(category, []):
            choices.append(
                {"value": c["value"], "label": c["label"], "is_custom": True})
        merged_config = dict(config)
        merged_config["choices"] = choices
        display[category] = merged_config
    return display


# ---------------------------------------------------------------------------
# Storage: Upstash Redis when configured (durable across Render restarts/
# redeploys), falling back to local JSON files when it's not (so local
# development still works without needing an Upstash account).
#
# Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN as environment
# variables in Render to enable this. Get both from your Upstash database's
# dashboard, under the "REST API" section.
# ---------------------------------------------------------------------------
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
USE_REDIS = bool(UPSTASH_URL and UPSTASH_TOKEN)


def _redis_command(*args):
    """Send one command to Upstash Redis's REST API and return its result."""
    body = json.dumps(list(args)).encode("utf-8")
    req = urllib.request.Request(
        UPSTASH_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + UPSTASH_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result.get("result")


def _redis_get_json(key, default):
    try:
        raw = _redis_command("GET", key)
    except Exception as exc:
        print("Upstash GET failed for key %r: %s" % (key, exc))
        return default
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _redis_set_json(key, value):
    try:
        _redis_command("SET", key, json.dumps(value, ensure_ascii=False))
    except Exception as exc:
        print("Upstash SET failed for key %r: %s" % (key, exc))


def load_orders():
    if USE_REDIS:
        return _redis_get_json("orders", [])
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_orders(orders):
    if USE_REDIS:
        _redis_set_json("orders", orders)
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2, ensure_ascii=False)


def load_removed_items():
    if USE_REDIS:
        data = _redis_get_json("removed_items", {})
    elif not os.path.exists(REMOVED_ITEMS_FILE):
        data = {}
    else:
        with open(REMOVED_ITEMS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    for category in OPTIONS:
        data.setdefault(category, [])
    return data


def save_removed_items(removed):
    if USE_REDIS:
        _redis_set_json("removed_items", removed)
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REMOVED_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(removed, f, indent=2, ensure_ascii=False)


def load_custom_items():
    if USE_REDIS:
        data = _redis_get_json("custom_items", {})
    elif not os.path.exists(CUSTOM_ITEMS_FILE):
        data = {}
    else:
        with open(CUSTOM_ITEMS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    for category in OPTIONS:
        data.setdefault(category, [])
    return data


def save_custom_items(custom_items):
    if USE_REDIS:
        _redis_set_json("custom_items", custom_items)
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CUSTOM_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(custom_items, f, indent=2, ensure_ascii=False)


def load_store_status():
    if USE_REDIS:
        data = _redis_get_json("store_status", {})
    elif not os.path.exists(STORE_STATUS_FILE):
        data = {}
    else:
        with open(STORE_STATUS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    data.setdefault("orders_closed", False)
    return data


def save_store_status(status):
    if USE_REDIS:
        _redis_set_json("store_status", status)
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STORE_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


def append_order_log(order):
    if USE_REDIS:
        try:
            _redis_command("RPUSH", "order_log",
                           json.dumps(order, ensure_ascii=False))
        except Exception as exc:
            print("Upstash RPUSH failed for order_log: %s" % exc)
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    log = []
    if os.path.exists(ORDER_LOG_FILE):
        with open(ORDER_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []
    log.append(order)
    with open(ORDER_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def load_order_log():
    if USE_REDIS:
        try:
            raw_entries = _redis_command("LRANGE", "order_log", 0, -1) or []
        except Exception as exc:
            print("Upstash LRANGE failed for order_log: %s" % exc)
            return []
        entries = []
        for raw in raw_entries:
            try:
                entries.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return entries
    if not os.path.exists(ORDER_LOG_FILE):
        return []
    with open(ORDER_LOG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


# ---------------------------------------------------------------------------
# Rate limiting: a small in-memory sliding-window limiter keyed by
# (endpoint, client IP). Good enough for a single-process deployment
# serving ~100 people. If this is ever run with multiple worker processes,
# swap this for Redis-backed limiting (e.g. Flask-Limiter + Redis) since
# in-memory state isn't shared across processes.
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_rate_buckets = defaultdict(deque)


def rate_limit(max_requests, window_seconds):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            key = (f.__name__, request.remote_addr)
            now = time.time()
            with _rate_lock:
                bucket = _rate_buckets[key]
                while bucket and now - bucket[0] > window_seconds:
                    bucket.popleft()
                if len(bucket) >= max_requests:
                    retry_after = int(window_seconds - (now - bucket[0])) + 1
                    response = jsonify(
                        {"error": "Demasiadas solicitudes. Intente de nuevo en un momento."})
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response
                bucket.append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# CSRF protection: standard synchronizer-token pattern. A per-session token
# is embedded in every form/AJAX call and checked on every state-changing
# request, so a malicious third-party page can't submit requests using a
# logged-in barista's session cookie.
# ---------------------------------------------------------------------------

def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


def csrf_protect(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        expected = session.get("csrf_token")
        submitted = request.form.get(
            "csrf_token") or request.headers.get("X-CSRFToken")
        if not expected or not submitted or not hmac.compare_digest(expected, submitted):
            return jsonify({"error": "Solicitud invalida. Por favor recargue la pagina e intente de nuevo."}), 400
        return f(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PHONE_RE = re.compile(r"^[0-9+\-\s().]{7,20}$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def clean_text(value, max_length):
    """Strip control characters and cap length. Jinja auto-escapes on
    render, so this isn't the only XSS defense — it's defense in depth
    plus basic hygiene against junk/oversized input."""
    if not value:
        return ""
    value = _CONTROL_CHAR_RE.sub("", value).strip()
    return value[:max_length]


# ---------------------------------------------------------------------------
# Security headers on every response
# ---------------------------------------------------------------------------

@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return response


# ---------------------------------------------------------------------------
# Customer-facing routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    is_barista = bool(session.get("is_barista"))
    removed = load_removed_items()
    custom_items = load_custom_items()
    display_options = build_display_options(custom_items)
    store_status = load_store_status()
    return render_template("index.html", options=display_options, removed=removed,
                           is_barista=is_barista, orders_closed=store_status.get("orders_closed", False))


@app.route("/submit_order", methods=["POST"])
@rate_limit(10, 60)
@csrf_protect
def submit_order():
    form = request.form
    with _file_lock:
        store_status = load_store_status()
        if store_status.get("orders_closed"):
            return jsonify({"success": False,
                            "error": "Perdon, ahorita no estamos tomando ordenes. \u00a1Pronto Regresamos!"}), 403

        removed = load_removed_items()
        custom_items = load_custom_items()

        name = clean_text(form.get("name"), 80)
        phone = clean_text(form.get("phone"), 20)
        temp = form.get("temp")
        drink = form.get("drink")
        jarave = form.get("jarave")
        milk = form.get("milk")
        whip = form.get("whip")
        drizzle = request.form.getlist("drizzle")
        notes = clean_text(form.get("notes"), 500)

        if not name or not phone:
            return jsonify({"success": False, "error": "Faltan campos requeridos."}), 400

        if not _PHONE_RE.match(phone):
            return jsonify({"success": False, "error": "Numero de telefono invalido."}), 400

        # Americano has no milk, so milk is only required for other drinks
        requires_milk = drink != "Americano"

        # Validate every selection is a real, known menu option (base or custom)
        for category, value in (("temp", temp), ("drink", drink), ("jarave", jarave), ("whip", whip)):
            if not value or not is_valid_choice(category, value, custom_items):
                return jsonify({"success": False, "error": "Faltan campos requeridos."}), 400

        if requires_milk:
            if not milk or not is_valid_choice("milk", milk, custom_items):
                return jsonify({"success": False, "error": "Faltan campos requeridos."}), 400
        else:
            milk = None

        max_drizzle = len(OPTIONS["drizzle"]["choices"]) + \
            len(custom_items.get("drizzle", []))
        if len(drizzle) > max_drizzle:
            return jsonify({"success": False, "error": "Seleccion invalida."}), 400

        for value in drizzle:
            if not is_valid_choice("drizzle", value, custom_items):
                return jsonify({"success": False, "error": "Seleccion invalida."}), 400

        # Reject any selection that a barista has temporarily removed
        selections = {"temp": [temp], "drink": [drink], "jarave": [jarave],
                      "milk": [milk] if milk else [], "whip": [whip], "drizzle": drizzle}
        for category, values in selections.items():
            for value in values:
                if value and value in removed.get(category, []):
                    return jsonify({"success": False,
                                    "error": "Uno de los articulos seleccionados ya no esta disponible."}), 400

        if drink == "Shakin' Espresso" and temp != "Frio":
            return jsonify({"success": False,
                            "error": "Shakin' Espresso solo esta disponible con bebidas frias."}), 400

        if notes:
            word_count = len(notes.split())
            if word_count > 50:
                notes = " ".join(notes.split()[:50])

        if not drizzle:
            drizzle = ["Ninguno"]

        order = {
            "id": str(uuid.uuid4()),
            "name": name,
            "phone": phone,
            "temp": display_value("temp", temp, custom_items),
            "drink": display_value("drink", drink, custom_items),
            "jarave": display_value("jarave", jarave, custom_items),
            "milk": display_value("milk", milk, custom_items) if milk else "N/A",
            "whip": display_value("whip", whip, custom_items),
            "drizzle": [display_value("drizzle", v, custom_items) for v in drizzle],
            "notes": notes,
            "started": False,
            "finished": False,
            "contacted": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        orders = load_orders()
        orders.append(order)
        save_orders(orders)
        append_order_log(order)

    return jsonify({"success": True})

# ---------------------------------------------------------------------------
# Barista login
# ---------------------------------------------------------------------------


@app.route("/login", methods=["POST"])
@rate_limit(5, 60)
@csrf_protect
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    valid_username = hmac.compare_digest(username, BARISTA_USERNAME)
    valid_password = hmac.compare_digest(password, BARISTA_PASSWORD)

    if valid_username and valid_password:
        session["is_barista"] = True
        return redirect(url_for("index"))

    return redirect(url_for("index", login_error=1))


@app.route("/logout")
def logout():
    session.pop("is_barista", None)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Barista menu editing
# ---------------------------------------------------------------------------

@app.route("/toggle_item", methods=["POST"])
@rate_limit(30, 60)
@csrf_protect
def toggle_item():
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401

    category = request.form.get("category")
    value = request.form.get("value")

    # This endpoint only manages availability of the fixed base menu.
    # Custom items are added/removed outright via /add_item and
    # /delete_custom_item instead.
    if not is_base_choice(category, value):
        return jsonify({"error": "invalid selection"}), 400

    with _file_lock:
        removed = load_removed_items()
        if value in removed[category]:
            removed[category].remove(value)
            is_removed = False
        else:
            removed[category].append(value)
            is_removed = True
        save_removed_items(removed)

    return jsonify({"success": True, "removed": is_removed})


@app.route("/add_item", methods=["POST"])
@rate_limit(40, 60)
@csrf_protect
def add_item():
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401

    category = request.form.get("category")
    label = clean_text(request.form.get("label"), 40)

    if category not in OPTIONS:
        return jsonify({"success": False, "error": "Categoria invalida."}), 400
    if not label:
        return jsonify({"success": False, "error": "Escriba un nombre para el nuevo articulo."}), 400

    with _file_lock:
        custom_items = load_custom_items()

        existing_labels = {c["label"].strip().lower()
                           for c in OPTIONS[category]["choices"]}
        existing_labels |= {c["label"].strip().lower()
                            for c in custom_items.get(category, [])}
        if label.strip().lower() in existing_labels:
            return jsonify({"success": False, "error": "Ese articulo ya existe."}), 400

        if len(custom_items.get(category, [])) >= MAX_CUSTOM_ITEMS_PER_CATEGORY:
            return jsonify({"success": False,
                            "error": "Se alcanzo el limite de articulos personalizados para esta categoria."}), 400

        new_value = "custom_" + secrets.token_hex(6)
        custom_items.setdefault(category, []).append(
            {"value": new_value, "label": label})
        save_custom_items(custom_items)

    return jsonify({"success": True, "value": new_value, "label": label})


@app.route("/delete_custom_item", methods=["POST"])
@rate_limit(30, 60)
@csrf_protect
def delete_custom_item():
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401

    category = request.form.get("category")
    value = request.form.get("value")

    # Only ever allow deleting items that were actually barista-added
    if category not in OPTIONS or not value or not value.startswith("custom_"):
        return jsonify({"success": False, "error": "Solicitud invalida."}), 400

    with _file_lock:
        custom_items = load_custom_items()
        before = len(custom_items.get(category, []))
        custom_items[category] = [c for c in custom_items.get(
            category, []) if c["value"] != value]
        if len(custom_items[category]) == before:
            return jsonify({"success": False, "error": "Articulo no encontrado."}), 404
        save_custom_items(custom_items)

    return jsonify({"success": True})


@app.route("/toggle_store_status", methods=["POST"])
@rate_limit(20, 60)
@csrf_protect
def toggle_store_status():
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401

    with _file_lock:
        status = load_store_status()
        status["orders_closed"] = not status.get("orders_closed", False)
        save_store_status(status)

    return jsonify({"success": True, "orders_closed": status["orders_closed"]})


# ---------------------------------------------------------------------------
# Barista-facing order queue
# ---------------------------------------------------------------------------

@app.route("/orders")
def orders_page():
    if not session.get("is_barista"):
        return redirect(url_for("index"))
    orders = load_orders()
    orders.reverse()  # newest first
    return render_template("orders.html", orders=orders)


@app.route("/order_history")
@rate_limit(30, 60)
def order_history():
    if not session.get("is_barista"):
        return redirect(url_for("index"))
    log = load_order_log()
    log.reverse()  # newest first
    return render_template("history.html", orders=log)


@app.route("/orders/data")
@rate_limit(60, 60)
def orders_data():
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401
    orders = load_orders()
    orders.reverse()
    return jsonify(orders)


@app.route("/orders/<order_id>/toggle/<field>", methods=["POST"])
@rate_limit(60, 60)
@csrf_protect
def toggle_order_field(order_id, field):
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401
    if not _UUID_RE.match(order_id):
        return jsonify({"error": "invalid order id"}), 400
    if field not in ("started", "finished", "contacted"):
        return jsonify({"error": "invalid field"}), 400

    with _file_lock:
        orders = load_orders()
        for o in orders:
            if o["id"] == order_id:
                o[field] = not o.get(field, False)
                save_orders(orders)
                return jsonify({"success": True, "value": o[field]})

    return jsonify({"error": "order not found"}), 404


@app.route("/orders/<order_id>/delete", methods=["POST"])
@rate_limit(20, 60)
@csrf_protect
def delete_order(order_id):
    if not session.get("is_barista"):
        return jsonify({"error": "unauthorized"}), 401
    if not _UUID_RE.match(order_id):
        return jsonify({"error": "invalid order id"}), 400

    with _file_lock:
        orders = load_orders()
        orders = [o for o in orders if o["id"] != order_id]
        save_orders(orders)

    return jsonify({"success": True})


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG") == "1"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)
