"""Auditoría de formularios y endpoints POST: entradas malas, límites, IDOR, CSRF y repeticiones.

Cada formulario y cada POST que lee ``request.form`` a mano se prueba con lo que
puede mandar un navegador torpe o una persona con malas intenciones: campos
vacíos, texto en los números, NaN, infinitos, coma decimal, fechas imposibles,
opciones que no existen, identificadores ajenos o enormes, sin token CSRF y dos
veces seguidas. Por cada caso se comprueba lo mismo:

* no hay excepción ni 500 (en pruebas las excepciones se propagan: una que
  salte cuenta como fallo);
* la respuesta explica el error (formulario con su mensaje, un aviso o un
  código 4xx en los endpoints que no tienen pantalla propia);
* si la entrada no era válida, no se ha escrito nada en la base de datos.

Lo que hoy falla está marcado ``xfail(strict=True)`` con su ``BUG-n``, descrito
en ``docs/AUDITORIA_FORMULARIOS.md``: cuando se arregle, el test pasará a XPASS
y habrá que quitar la marca.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select

from app.models import (
    ActivityLog,
    BodyMeasurement,
    FoodEntry,
    IntakeLog,
    Profile,
    QuestionnaireDraft,
    RoutineExercise,
    SetLog,
    Subscription,
    User,
    WeightLog,
    WorkoutSession,
)
from app.models.user import DISPLAY_NAME_MAX_LENGTH
from tests.conftest import AppFactory
from tests.integration.test_auth import PASSWORD, _register
from tests.integration.test_hevy_import import HEADER as HEVY_HEADER
from tests.integration.test_onboarding import _post_step
from tests.integration.test_workout_flow import _routine, _with_routine

HUGE_ID = "99999999999999999999"  # cabe en un int de Python, no en un INTEGER de SQL
XSS = '"><img src=x onerror=alert(1)><script>alert("xss")</script>'
LONG = "x" * 10_000
STRONG_PASSWORD = "otra contraseña muy larga"


# --- Utilidades -----------------------------------------------------------------


def _short(value: object) -> str:
    """Readable test ids for long payloads."""
    text = str(value)
    if text == LONG:
        return "10000-x"
    if text == XSS:
        return "html"
    return text[:24] or "vacio"


def _count(database: SQLAlchemy, model: type) -> int:
    database.session.expire_all()
    return database.session.scalar(select(func.count()).select_from(model)) or 0


def _user(database: SQLAlchemy, email: str = "ana@example.com") -> User:
    database.session.expire_all()
    user = database.session.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _explains(html: str) -> bool:
    """A field error or a non-success flash is on the page."""
    return 'class="field-error"' in html or bool(
        re.search(r'class="flash flash-(error|warning|info)"', html)
    )


def _today(database: SQLAlchemy) -> date:
    return _user(database).today()


def _signed_up(client: FlaskClient) -> FlaskClient:
    assert _register(client).status_code == 302
    return client


@pytest.fixture
def account(client: FlaskClient, seeded: SQLAlchemy) -> FlaskClient:
    """A plain account, without questionnaire."""
    return _signed_up(client)


@pytest.fixture
def planned(client: FlaskClient, seeded: SQLAlchemy) -> FlaskClient:
    """An account with questionnaire, plan and routine."""
    _with_routine(client)
    return client


@pytest.fixture
def live(planned: FlaskClient, seeded: SQLAlchemy) -> tuple[FlaskClient, int, RoutineExercise]:
    """A session in progress and the first exercise of its day."""
    assert planned.post("/entreno/empezar/1").status_code == 302
    session = seeded.session.scalar(select(WorkoutSession))
    assert session is not None
    return planned, session.id, _routine(seeded).days[0].exercises[0]


# --- Método y CSRF, para todos los endpoints a la vez ----------------------------


def _post_rules(app: Flask) -> list[str]:
    paths = []
    for rule in app.url_map.iter_rules():
        if "POST" not in (rule.methods or set()):
            continue
        path = re.sub(r"<int:[^>]+>", "1", str(rule))
        paths.append(re.sub(r"<[^>]+>", "x", path))
    return sorted(paths)


def test_every_post_only_endpoint_refuses_a_get(app: Flask, database: SQLAlchemy) -> None:
    client = app.test_client()
    rules = list(app.url_map.iter_rules())
    with_get = {str(rule) for rule in rules if "GET" in (rule.methods or set())}
    post_only = [
        re.sub(r"<[^>]+>", "1", str(rule))
        for rule in rules
        if "POST" in (rule.methods or set()) and str(rule) not in with_get
    ]
    assert len(post_only) >= 30
    for path in post_only:
        assert client.get(path).status_code == 405, path


def test_every_post_endpoint_refuses_a_missing_csrf_token(make_app: AppFactory) -> None:
    """Sin token: 400 antes de llegar a la vista, con o sin sesión (salvo el webhook firmado)."""
    app = make_app(WTF_CSRF_ENABLED=True)
    with app.app_context():
        from app.extensions import db
        from app.services import auth

        db.create_all()
        user = auth.register_user("csrf@example.com", PASSWORD, "Ana", health_consent=True)
        db.session.commit()
        user_id = user.id
        paths = [path for path in _post_rules(app) if path != "/suscripcion/webhook"]
        assert len(paths) >= 45

        anonymous = app.test_client()
        signed_in = app.test_client()
        with signed_in.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True
        for path in paths:
            assert anonymous.post(path, data={}).status_code == 400, path
            assert signed_in.post(path, data={"day": "2026-11-01"}).status_code == 400, path

        # Y con datos válidos tampoco se escribe nada.
        signed_in.post("/diario/peso", data={"day": "2026-11-01", "weight_kg": "64"})
        signed_in.post("/cuenta/perfil", data={"display_name": "Otra", "locale": "en"})
        db.session.expire_all()
        assert db.session.scalar(select(func.count()).select_from(WeightLog)) == 0
        assert db.session.get(User, user_id).display_name == "Ana"
        db.session.remove()
        db.drop_all()


# --- auth ------------------------------------------------------------------------

REGISTER_OK = {
    "email": "nueva@example.com",
    "display_name": "Bea",
    "password": PASSWORD,
    "password_confirm": PASSWORD,
    "consent": "y",
    "health_consent": "y",
}


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param(dict.fromkeys(REGISTER_OK, ""), id="todo-vacio"),
        pytest.param({"email": ""}, id="sin-email"),
        pytest.param({"display_name": ""}, id="sin-nombre"),
        pytest.param({"password": ""}, id="sin-password"),
        pytest.param({"password_confirm": ""}, id="sin-confirmacion"),
        pytest.param({"consent": ""}, id="sin-aviso"),
        pytest.param({"health_consent": ""}, id="sin-consentimiento-salud"),
        pytest.param({"email": "no-es-un-correo"}, id="email-malo"),
        pytest.param({"email": "a" * 250 + "@example.com"}, id="email-largo"),
        pytest.param({"email": "' OR 1=1;--@example.com"}, id="email-inyeccion"),
        pytest.param({"display_name": "B"}, id="nombre-1-caracter"),
        pytest.param({"display_name": "   "}, id="nombre-solo-espacios"),
        pytest.param({"display_name": LONG}, id="nombre-10000"),
        pytest.param({"password_confirm": PASSWORD + "x"}, id="confirmacion-distinta"),
        pytest.param({"password": "a" * 129, "password_confirm": "a" * 129}, id="password-129"),
        pytest.param({"password": "12345678", "password_confirm": "12345678"}, id="password-debil"),
    ],
)
def test_register_refuses_bad_input_and_creates_nothing(
    client: FlaskClient, database: SQLAlchemy, overrides: dict[str, str]
) -> None:
    response = client.post("/registro", data={**REGISTER_OK, **overrides})
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(database, User) == 0


def test_register_accepts_the_limits(client: FlaskClient, database: SQLAlchemy) -> None:
    longest = ("Una frase de paso bastante larga y rara " * 4)[:128]
    response = client.post(
        "/registro",
        data={
            **REGISTER_OK,
            "display_name": "Bo" + "e" * (DISPLAY_NAME_MAX_LENGTH - 2),
            "password": longest,
            "password_confirm": longest,
        },
    )
    assert response.status_code == 302
    assert len(_user(database, "nueva@example.com").display_name) == DISPLAY_NAME_MAX_LENGTH


def test_register_with_the_same_email_in_other_casing_is_refused(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    _signed_up(client)
    client.post("/salir")
    response = _register(client, email="ANA@Example.COM")
    assert "Ya existe una cuenta con ese correo" in response.get_data(as_text=True)
    assert _count(database, User) == 1


def test_register_twice_in_a_row_creates_one_account(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    assert client.post("/registro", data=REGISTER_OK).status_code == 302
    # Ya con sesión: el segundo envío no vuelve a dar de alta.
    assert client.post("/registro", data=REGISTER_OK).status_code == 302
    assert _count(database, User) == 1


@pytest.mark.xfail(strict=True, reason="BUG-5: el nombre se recorta después de validar su largo")
def test_register_does_not_store_a_name_shorter_than_two_letters(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    client.post("/registro", data={**REGISTER_OK, "display_name": "  B  "})
    stored = database.session.scalar(select(User.display_name))
    assert stored is None or len(stored) >= 2


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="vacio"),
        pytest.param({"email": "ana@example.com"}, id="sin-password"),
        pytest.param({"password": PASSWORD}, id="sin-email"),
        pytest.param({"email": LONG, "password": PASSWORD}, id="email-10000"),
        pytest.param({"email": "ana@example.com", "password": LONG}, id="password-10000"),
        pytest.param({"email": "ana@example.com", "password": "mala"}, id="password-erronea"),
    ],
)
def test_login_refuses_bad_input_without_a_session(
    client: FlaskClient, database: SQLAlchemy, data: dict[str, str]
) -> None:
    _signed_up(client)
    client.post("/salir")
    response = client.post("/entrar", data=data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert "/entrar" in client.get("/panel").headers["Location"]


@pytest.mark.parametrize("email", ["", "no-es-un-correo", LONG], ids=_short)
def test_forgot_password_refuses_a_malformed_email(
    client: FlaskClient, database: SQLAlchemy, email: str
) -> None:
    response = client.post("/recuperar", data={"email": email})
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))


@pytest.mark.parametrize(
    "token", ["x", "a.b.c", LONG[:2000], "%00", "../../etc/passwd"], ids=_short
)
def test_reset_with_a_forged_token_changes_nothing(
    client: FlaskClient, database: SQLAlchemy, token: str
) -> None:
    _signed_up(client)
    client.post("/salir")
    before = _user(database).password_hash
    response = client.post(
        f"/restablecer/{token}",
        data={"password": STRONG_PASSWORD, "password_confirm": STRONG_PASSWORD},
    )
    assert response.status_code in {302, 404}
    assert _user(database).password_hash == before


def test_a_reset_link_works_only_once(client: FlaskClient, database: SQLAlchemy) -> None:
    from app.services import auth

    _signed_up(client)
    client.post("/salir")
    token = auth.issue_reset_token(_user(database))
    payload = {"password": STRONG_PASSWORD, "password_confirm": STRONG_PASSWORD}
    assert client.post(f"/restablecer/{token}", data=payload).status_code == 302
    after_first = _user(database).password_hash
    replay = client.post(
        f"/restablecer/{token}",
        data={"password": "una tercera clave larga", "password_confirm": "una tercera clave larga"},
        follow_redirects=True,
    )
    assert "no es válido o ha caducado" in replay.get_data(as_text=True)
    assert _user(database).password_hash == after_first


def test_reset_with_mismatched_passwords_changes_nothing(
    client: FlaskClient, database: SQLAlchemy
) -> None:
    from app.services import auth

    _signed_up(client)
    client.post("/salir")
    before = _user(database).password_hash
    token = auth.issue_reset_token(_user(database))
    response = client.post(
        f"/restablecer/{token}",
        data={"password": STRONG_PASSWORD, "password_confirm": STRONG_PASSWORD + "x"},
    )
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _user(database).password_hash == before


# --- account ---------------------------------------------------------------------

PROFILE_OK = {"display_name": "Ana", "locale": "es", "timezone": "Europe/Madrid"}


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param(dict.fromkeys(PROFILE_OK, ""), id="todo-vacio"),
        pytest.param({"display_name": ""}, id="sin-nombre"),
        pytest.param({"display_name": "Z"}, id="nombre-1"),
        pytest.param({"display_name": LONG}, id="nombre-10000"),
        pytest.param({"locale": "fr"}, id="idioma-inexistente"),
        pytest.param({"locale": "ES"}, id="idioma-mayusculas"),
        pytest.param({"locale": ""}, id="sin-idioma"),
        pytest.param({"timezone": "Mars/Olympus"}, id="zona-inexistente"),
        pytest.param({"timezone": LONG}, id="zona-10000"),
        pytest.param({"timezone": "' OR 1=1;--"}, id="zona-inyeccion"),
        pytest.param({"timezone": ""}, id="sin-zona"),
    ],
)
def test_profile_refuses_bad_input_and_keeps_the_old_values(
    account: FlaskClient, seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:
    response = account.post(
        "/cuenta/perfil", data={**PROFILE_OK, "display_name": "Otra", **overrides}
    )
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    user = _user(seeded)
    assert (user.display_name, user.locale, user.timezone) == ("Ana", "es", "Europe/Madrid")


def test_profile_accepts_the_limits(account: FlaskClient, seeded: SQLAlchemy) -> None:
    name = "Zo" + "é" * (DISPLAY_NAME_MAX_LENGTH - 2)
    response = account.post(
        "/cuenta/perfil", data={"display_name": name, "locale": "en", "timezone": "Atlantic/Canary"}
    )
    assert response.status_code == 302
    assert _user(seeded).display_name == name


@pytest.mark.xfail(strict=True, reason="BUG-5: el nombre se recorta después de validar su largo")
def test_profile_does_not_store_a_name_shorter_than_two_letters(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    account.post("/cuenta/perfil", data={**PROFILE_OK, "display_name": "  Z  "})
    assert len(_user(seeded).display_name) >= 2


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="vacio"),
        pytest.param({"email": "nuevo@example.com"}, id="sin-password"),
        pytest.param({"email": "", "current_password": PASSWORD}, id="sin-email"),
        pytest.param({"email": "malo", "current_password": PASSWORD}, id="email-malo"),
        pytest.param({"email": LONG + "@x.es", "current_password": PASSWORD}, id="email-largo"),
        pytest.param(
            {"email": "nuevo@example.com", "current_password": "mala"}, id="password-mala"
        ),
        pytest.param({"email": "nuevo@example.com", "current_password": LONG}, id="password-10000"),
    ],
)
def test_change_email_refuses_bad_input(
    account: FlaskClient, seeded: SQLAlchemy, data: dict[str, str]
) -> None:
    response = account.post("/cuenta/correo", data=data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _user(seeded).email == "ana@example.com"


def test_change_email_to_your_own_in_other_casing_is_not_an_error(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    response = account.post(
        "/cuenta/correo", data={"email": "ANA@EXAMPLE.COM", "current_password": PASSWORD}
    )
    assert response.status_code in {200, 302}
    assert _user(seeded).email == "ana@example.com"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="vacio"),
        pytest.param(
            {
                "current_password": "mala",
                "password": STRONG_PASSWORD,
                "password_confirm": STRONG_PASSWORD,
            },
            id="actual-mala",
        ),
        pytest.param(
            {"current_password": PASSWORD, "password": STRONG_PASSWORD, "password_confirm": "otra"},
            id="no-coinciden",
        ),
        pytest.param(
            {"current_password": PASSWORD, "password": "a" * 129, "password_confirm": "a" * 129},
            id="nueva-129",
        ),
        pytest.param(
            {"current_password": PASSWORD, "password": "123", "password_confirm": "123"},
            id="nueva-debil",
        ),
    ],
)
def test_change_password_refuses_bad_input(
    account: FlaskClient, seeded: SQLAlchemy, data: dict[str, str]
) -> None:
    before = _user(seeded).password_hash
    response = account.post("/cuenta/contrasena", data=data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _user(seeded).password_hash == before


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="vacio"),
        pytest.param({"current_password": PASSWORD, "confirmation": "borrar"}, id="minusculas"),
        pytest.param({"current_password": PASSWORD, "confirmation": "BORRA"}, id="errata"),
        pytest.param({"current_password": "mala", "confirmation": "BORRAR"}, id="password-mala"),
        pytest.param({"confirmation": "BORRAR"}, id="sin-password"),
    ],
)
def test_delete_account_refuses_bad_input_and_keeps_everything(
    account: FlaskClient, seeded: SQLAlchemy, data: dict[str, str]
) -> None:
    response = account.post("/cuenta/borrar", data=data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, User) == 1
    assert _user(seeded).deleted_at is None


# --- onboarding ------------------------------------------------------------------


def _draft(database: SQLAlchemy) -> tuple[int, dict[str, Any]]:
    database.session.expire_all()
    draft = database.session.scalar(select(QuestionnaireDraft))
    return (draft.step, dict(draft.data)) if draft else (0, {})


def _ready_for(client: FlaskClient, number: int) -> None:
    for previous in range(1, number):
        assert _post_step(client, previous).status_code == 302


STEP_BAD_INPUT = [
    # Paso 1: cuerpo.
    (1, {"sex": ""}, "sexo-vacio"),
    (1, {"sex": "FEMALE"}, "sexo-mayusculas"),
    (1, {"sex": "other"}, "sexo-fuera-de-opciones"),
    (1, {"birth_date": ""}, "nacimiento-vacio"),
    (1, {"birth_date": "2000-02-30"}, "nacimiento-imposible"),
    (1, {"birth_date": "20/05/1992"}, "nacimiento-formato-es"),
    (1, {"birth_date": "1900-01-01"}, "nacimiento-muy-antiguo"),
    (1, {"birth_date": "2030-01-01"}, "nacimiento-futuro"),
    (1, {"height_cm": ""}, "altura-vacia"),
    (1, {"height_cm": "abc"}, "altura-texto"),
    (1, {"height_cm": "99.9"}, "altura-bajo-minimo"),
    (1, {"height_cm": "250,1"}, "altura-sobre-maximo"),
    (1, {"height_cm": "-168"}, "altura-negativa"),
    (1, {"height_cm": "0"}, "altura-cero"),
    (1, {"height_cm": "nan"}, "altura-nan"),
    (1, {"height_cm": "inf"}, "altura-inf"),
    (1, {"height_cm": "1e300"}, "altura-enorme"),
    (1, {"weight_kg": "24,9"}, "peso-bajo-minimo"),
    (1, {"weight_kg": "350.1"}, "peso-sobre-maximo"),
    (1, {"weight_kg": "64kg"}, "peso-con-unidad"),
    (1, {"neck_cm": "19.9"}, "cuello-bajo-minimo"),
    (1, {"waist_cm": "250.1"}, "cintura-sobre-maximo"),
    (1, {"hip_cm": ""}, "mujer-sin-cadera"),
    (1, {"body_fat_pct": "20", "body_fat_method": "none"}, "grasa-sin-metodo"),
    (1, {"body_fat_pct": "1.9", "body_fat_method": "dexa"}, "grasa-bajo-minimo"),
    (1, {"body_fat_pct": "70.1", "body_fat_method": "dexa"}, "grasa-sobre-maximo"),
    (1, {"body_fat_method": "rayos-x"}, "metodo-fuera-de-opciones"),
    # Paso 2: actividad.
    (2, {"job_activity": "astronauta"}, "trabajo-fuera-de-opciones"),
    (2, {"daily_steps": "-1"}, "pasos-negativos"),
    (2, {"daily_steps": "60001"}, "pasos-sobre-maximo"),
    (2, {"daily_steps": "6000.5"}, "pasos-decimales"),
    (2, {"sleep_hours": "2,9"}, "sueno-bajo-minimo"),
    (2, {"sleep_hours": "16.1"}, "sueno-sobre-maximo"),
    (2, {"stress_level": "6"}, "estres-fuera-de-opciones"),
    (2, {"stress_level": "abc"}, "estres-texto"),
    (2, {"other_activity_type": "x" * 81}, "otra-actividad-81"),
    (2, {"other_activity_sessions_per_week": "15"}, "sesiones-sobre-maximo"),
    (2, {"other_activity_sessions_per_week": "2"}, "sesiones-sin-minutos-ni-intensidad"),
    (
        2,
        {"other_activity_sessions_per_week": "2", "other_activity_minutes": "301"},
        "minutos-sobre-maximo",
    ),
    (
        2,
        {
            "other_activity_sessions_per_week": "2",
            "other_activity_minutes": "40",
            "other_activity_intensity": "extrema",
        },
        "intensidad-fuera-de-opciones",
    ),
    # Paso 3: entrenamiento.
    (3, {"training_experience": "experto"}, "experiencia-fuera-de-opciones"),
    (3, {"training_days_per_week": "0"}, "dias-cero"),
    (3, {"training_days_per_week": "7"}, "dias-siete"),
    (3, {"training_days_per_week": "abc"}, "dias-texto"),
    (3, {"session_minutes": "50"}, "minutos-fuera-de-opciones"),
    (3, {"training_location": "luna"}, "lugar-fuera-de-opciones"),
    (3, {"training_time": "medianoche"}, "hora-fuera-de-opciones"),
    # Paso 4: material.
    (4, {"equipment": []}, "sin-material"),
    (4, {"equipment": ["cohete"]}, "material-inexistente"),
    (4, {"priority_muscles": ["glutes", "shoulders", "chest"]}, "tres-prioridades"),
    (4, {"priority_muscles": ["alas"]}, "prioridad-inexistente"),
    (4, {"injury_knee": "extrema"}, "lesion-fuera-de-opciones"),
    # Paso 5: objetivo.
    (5, {"goal": "volar"}, "objetivo-fuera-de-opciones"),
    (5, {"goal": ""}, "objetivo-vacio"),
    (5, {"aggressiveness": "brutal"}, "ritmo-fuera-de-opciones"),
    (5, {"target_weight_kg": "24"}, "peso-objetivo-bajo"),
    (5, {"target_weight_kg": "nan"}, "peso-objetivo-nan"),
    (5, {"target_date": "2026-02-30"}, "fecha-imposible"),
    (5, {"target_date": "2020-01-01"}, "fecha-pasada"),
    # Paso 6: nutrición.
    (6, {"meals_per_day": "1"}, "comidas-una"),
    (6, {"meals_per_day": "7"}, "comidas-siete"),
    (6, {"diet_pattern": "carnivora"}, "dieta-fuera-de-opciones"),
    (6, {"alcohol_drinks_per_week": "-1"}, "alcohol-negativo"),
    (6, {"alcohol_drinks_per_week": "51"}, "alcohol-sobre-maximo"),
    (6, {"alcohol_drinks_per_week": ""}, "alcohol-vacio"),
]


STEP_KNOWN_BUGS = {
    "lesion-fuera-de-opciones": pytest.mark.xfail(
        strict=True, reason="BUG-12: una gravedad de lesión no válida se rechaza sin decir por qué"
    ),
}


@pytest.mark.parametrize(
    ("number", "overrides"),
    [
        pytest.param(n, o, id=f"paso{n}-{name}", marks=STEP_KNOWN_BUGS.get(name, ()))
        for n, o, name in STEP_BAD_INPUT
    ],
)
def test_questionnaire_steps_refuse_bad_input_and_keep_the_draft(
    account: FlaskClient, seeded: SQLAlchemy, number: int, overrides: dict[str, Any]
) -> None:
    _ready_for(account, number)
    before = _draft(seeded)
    response = _post_step(account, number, **overrides)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _draft(seeded) == before


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"height_cm": "100", "weight_kg": "25"}, id="minimos"),
        pytest.param({"height_cm": "250", "weight_kg": "350"}, id="maximos"),
        pytest.param({"height_cm": "168,5", "weight_kg": "72,5"}, id="coma-decimal"),
        pytest.param({"height_cm": " 168 ", "weight_kg": " 64.0 "}, id="espacios"),
        pytest.param({"neck_cm": "20", "waist_cm": "250", "hip_cm": "50"}, id="medidas-limite"),
    ],
)
def test_questionnaire_body_step_accepts_the_limits(
    account: FlaskClient, seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:
    assert _post_step(account, 1, **overrides).status_code == 302
    assert _draft(seeded)[0] == 1


def test_questionnaire_birth_date_at_exactly_eighteen(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    today = _today(seeded)
    if (today.month, today.day) == (2, 29):
        pytest.skip("el 29 de febrero no tiene «hace 18 años» exacto")
    adult = today.replace(year=today.year - 18)
    one_day_short = adult + timedelta(days=1)
    refused = _post_step(account, 1, birth_date=one_day_short.isoformat())
    assert "solo para mayores de 18" in refused.get_data(as_text=True)
    assert _post_step(account, 1, birth_date=adult.isoformat()).status_code == 302


def test_questionnaire_rejects_unknown_or_skipped_steps(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    for number in ("0", "8", HUGE_ID):
        assert account.post(f"/cuestionario/paso/{number}", data={}).status_code == 404
    skipped = _post_step(account, 3)
    assert skipped.status_code == 302
    assert skipped.headers["Location"].endswith("/cuestionario/paso/1")
    assert _draft(seeded) == (0, {})


def test_a_target_date_of_tomorrow_is_the_first_valid_one(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    _ready_for(account, 5)
    today = _today(seeded)
    assert _post_step(account, 5, target_date=today.isoformat()).status_code == 200
    assert (
        _post_step(account, 5, target_date=(today + timedelta(days=1)).isoformat()).status_code
        == 302
    )


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"sex": "", "goal": ""}, id="vacios"),
        pytest.param({"birth_date": "2015-01-01"}, id="menor"),
        pytest.param({"height_cm": "nan"}, id="altura-nan"),
        pytest.param({"training_days_per_week": "9"}, id="dias-fuera"),
        pytest.param({"training_location": "luna"}, id="lugar-fuera"),
    ],
)
def test_quick_questionnaire_refuses_bad_input_and_writes_no_plan(
    account: FlaskClient, seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:
    data = {
        "sex": "female",
        "birth_date": "1992-05-20",
        "height_cm": "168",
        "weight_kg": "64",
        "goal": "fat_loss",
        "training_experience": "6_to_24_months",
        "training_days_per_week": "3",
        "session_minutes": "60",
        "training_location": "basic_gym",
        **overrides,
    }
    response = account.post("/cuestionario/rapido", data=data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, Profile) == 0


@pytest.mark.xfail(
    strict=True,
    reason="BUG-10: pulsar dos veces «Generar plan» crea otra versión de perfil y de plan",
)
def test_generating_the_plan_twice_makes_one_profile(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    _ready_for(account, 8)
    assert account.post("/cuestionario/revisar").status_code == 302
    second = account.post("/cuestionario/revisar")
    assert second.status_code == 302
    assert _count(seeded, Profile) == 1


# --- tracking: diario ------------------------------------------------------------


def _yesterday(database: SQLAlchemy) -> str:
    return (_today(database) - timedelta(days=1)).isoformat()


DIARY_BAD_INPUT = [
    ("/diario/peso", {"weight_kg": "64", "day": ""}, "peso-sin-dia"),
    ("/diario/peso", {"weight_kg": ""}, "peso-vacio"),
    ("/diario/peso", {"weight_kg": "abc"}, "peso-texto"),
    ("/diario/peso", {"weight_kg": "24.9"}, "peso-bajo-minimo"),
    ("/diario/peso", {"weight_kg": "350,1"}, "peso-sobre-maximo"),
    ("/diario/peso", {"weight_kg": "-64"}, "peso-negativo"),
    ("/diario/peso", {"weight_kg": "0"}, "peso-cero"),
    ("/diario/peso", {"weight_kg": "nan"}, "peso-nan"),
    ("/diario/peso", {"weight_kg": "inf"}, "peso-inf"),
    ("/diario/peso", {"weight_kg": "1.234,5"}, "peso-miles"),
    ("/diario/peso", {"weight_kg": "64", "notes": "x" * 201}, "peso-nota-201"),
    ("/diario/peso", {"weight_kg": "64", "day": "2026-02-30"}, "peso-dia-imposible"),
    ("/diario/peso", {"weight_kg": "64", "day": "01/11/2026"}, "peso-dia-formato-es"),
    ("/diario/peso", {"weight_kg": "64", "day": "mañana"}, "peso-dia-texto"),
    ("/diario/ingesta", {"calories": ""}, "kcal-vacias"),
    ("/diario/ingesta", {"calories": "abc"}, "kcal-texto"),
    ("/diario/ingesta", {"calories": "1850.5"}, "kcal-decimales"),
    ("/diario/ingesta", {"calories": "-1"}, "kcal-negativas"),
    ("/diario/ingesta", {"calories": "20001"}, "kcal-sobre-maximo"),
    ("/diario/ingesta", {"calories": HUGE_ID}, "kcal-enormes"),
    ("/diario/ingesta", {"calories": "1800", "protein_g": "1000.1"}, "proteina-sobre-maximo"),
    ("/diario/ingesta", {"calories": "1800", "carbs_g": "-1"}, "hidratos-negativos"),
    ("/diario/ingesta", {"calories": "1800", "fat_g": "nan"}, "grasa-nan"),
    ("/diario/ingesta", {"calories": "1800", "adherence_pct": "101"}, "adherencia-101"),
    ("/diario/actividad", {"steps": "-1"}, "pasos-negativos"),
    ("/diario/actividad", {"steps": "100001"}, "pasos-sobre-maximo"),
    ("/diario/actividad", {"steps": "8.000"}, "pasos-con-punto"),
    ("/diario/actividad", {"cardio_kind": "LISS", "cardio_minutes": "30"}, "cardio-mayusculas"),
    ("/diario/actividad", {"cardio_kind": "natacion", "cardio_minutes": "30"}, "cardio-fuera"),
    ("/diario/actividad", {"cardio_minutes": "30"}, "minutos-sin-tipo"),
    ("/diario/actividad", {"cardio_kind": "liss"}, "tipo-sin-minutos"),
    ("/diario/actividad", {"cardio_kind": "liss", "cardio_minutes": "601"}, "minutos-sobre-max"),
]


@pytest.mark.parametrize(
    ("path", "overrides"),
    [pytest.param(p, o, id=name) for p, o, name in DIARY_BAD_INPUT],
)
def test_diary_forms_refuse_bad_input_and_write_nothing(
    account: FlaskClient, seeded: SQLAlchemy, path: str, overrides: dict[str, str]
) -> None:
    data = {"day": _yesterday(seeded), **overrides}
    response = account.post(path, data=data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, WeightLog) == 0
    assert _count(seeded, IntakeLog) == 0
    assert _count(seeded, ActivityLog) == 0


@pytest.mark.parametrize("path", ["/diario/peso", "/diario/ingesta", "/diario/actividad"])
def test_diary_forms_refuse_a_day_that_has_not_come(
    account: FlaskClient, seeded: SQLAlchemy, path: str
) -> None:
    tomorrow = (_today(seeded) + timedelta(days=1)).isoformat()
    data = {"day": tomorrow, "weight_kg": "64", "calories": "1800", "steps": "5000"}
    response = account.post(path, data=data)
    assert "Ese día todavía no ha llegado" in response.get_data(as_text=True)
    assert _count(seeded, WeightLog) == 0
    assert _count(seeded, IntakeLog) == 0
    assert _count(seeded, ActivityLog) == 0


@pytest.mark.parametrize(
    "value", ["25", "350", "72,5", " 64 ", "64.25"], ids=lambda v: f"peso-{v.strip()}"
)
def test_the_weigh_in_accepts_the_limits_and_the_decimal_comma(
    account: FlaskClient, seeded: SQLAlchemy, value: str
) -> None:
    response = account.post("/diario/peso", data={"day": _yesterday(seeded), "weight_kg": value})
    assert response.status_code == 302
    assert seeded.session.scalar(select(WeightLog.weight_kg)) == pytest.approx(
        float(value.strip().replace(",", "."))
    )


def test_intake_and_activity_accept_their_limits(account: FlaskClient, seeded: SQLAlchemy) -> None:
    day = _yesterday(seeded)
    assert (
        account.post(
            "/diario/ingesta",
            data={
                "day": day,
                "calories": "20000",
                "protein_g": "1000",
                "carbs_g": "0",
                "fat_g": "0,5",
                "adherence_pct": "100",
            },
        ).status_code
        == 302
    )
    assert (
        account.post(
            "/diario/actividad",
            data={"day": day, "steps": "100000", "cardio_kind": "hiit", "cardio_minutes": "600"},
        ).status_code
        == 302
    )
    assert seeded.session.scalar(select(IntakeLog.calories)) == 20000


def test_saving_the_same_day_twice_keeps_one_row(account: FlaskClient, seeded: SQLAlchemy) -> None:
    day = _yesterday(seeded)
    for kg in ("64", "64,5"):
        assert account.post("/diario/peso", data={"day": day, "weight_kg": kg}).status_code == 302
    for kcal in ("1800", "1900"):
        assert (
            account.post("/diario/ingesta", data={"day": day, "calories": kcal}).status_code == 302
        )
    assert _count(seeded, WeightLog) == 1
    assert _count(seeded, IntakeLog) == 1
    assert seeded.session.scalar(select(WeightLog.weight_kg)) == 64.5


def test_diary_notes_never_come_back_as_html(account: FlaskClient, seeded: SQLAlchemy) -> None:
    day = _yesterday(seeded)
    account.post("/diario/ingesta", data={"day": day, "calories": "1800", "notes": XSS[:200]})
    account.post("/diario/actividad", data={"day": day, "steps": "100", "notes": XSS[:200]})
    account.post("/diario/perimetros", data={"day": day, "waist_cm": "80", "notes": XSS[:200]})
    for path in (f"/diario?fecha={day}", "/diario/perimetros"):
        page = account.get(path).get_data(as_text=True)
        assert "<img src=x onerror" not in page, path
        assert "<script>alert" not in page, path


@pytest.mark.xfail(
    strict=True, reason="BUG-6: el diario acepta días de hace más de un siglo (sin límite inferior)"
)
@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("/diario/peso", {"weight_kg": "64"}),
        ("/diario/ingesta", {"calories": "1800"}),
        ("/diario/actividad", {"steps": "5000"}),
        ("/diario/perimetros", {"waist_cm": "80"}),
    ],
)
def test_diary_refuses_a_day_before_anyone_was_born(
    account: FlaskClient, seeded: SQLAlchemy, path: str, data: dict[str, str]
) -> None:
    response = account.post(path, data={"day": "1900-01-01", **data})
    assert response.status_code == 200
    assert _count(seeded, WeightLog) == 0
    assert _count(seeded, IntakeLog) == 0
    assert _count(seeded, ActivityLog) == 0

    assert _count(seeded, BodyMeasurement) == 0


@pytest.mark.xfail(
    strict=True, reason="BUG-7: los números aceptan la sintaxis de Python ('6_4' se lee como 64)"
)
@pytest.mark.parametrize("value", ["6_4", "1_00"])
def test_numbers_with_underscores_are_not_numbers(
    account: FlaskClient, seeded: SQLAlchemy, value: str
) -> None:
    account.post("/diario/peso", data={"day": _yesterday(seeded), "weight_kg": value})
    assert _count(seeded, WeightLog) == 0


MEASUREMENT_BAD_INPUT = [
    ({}, "sin-ninguna-medida"),
    ({"day": "", "waist_cm": "80"}, "sin-dia"),
    ({"day": "2026-02-30", "waist_cm": "80"}, "dia-imposible"),
    ({"waist_cm": "abc"}, "cintura-texto"),
    ({"neck_cm": "19.9"}, "cuello-bajo-minimo"),
    ({"hip_cm": "250,1"}, "cadera-sobre-maximo"),
    ({"chest_cm": "-90"}, "pecho-negativo"),
    ({"arm_cm": "nan"}, "brazo-nan"),
    ({"thigh_cm": "inf"}, "muslo-inf"),
    ({"calf_cm": "14.9"}, "gemelo-bajo-minimo"),
    ({"body_fat_pct": "20"}, "grasa-sin-metodo"),
    ({"body_fat_pct": "70.1", "body_fat_method": "dexa"}, "grasa-sobre-maximo"),
    ({"waist_cm": "80", "body_fat_method": "rayos-x"}, "metodo-fuera-de-opciones"),
    ({"waist_cm": "80", "notes": "x" * 201}, "nota-201"),
]


@pytest.mark.parametrize(
    "overrides", [pytest.param(o, id=name) for o, name in MEASUREMENT_BAD_INPUT]
)
def test_measurements_refuse_bad_input_and_write_nothing(
    account: FlaskClient, seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:

    response = account.post("/diario/perimetros", data={"day": _yesterday(seeded), **overrides})
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, BodyMeasurement) == 0


def test_measurements_twice_on_the_same_day_keep_one_row(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:

    day = _yesterday(seeded)
    for waist in ("80", "79,5"):
        response = account.post("/diario/perimetros", data={"day": day, "waist_cm": waist})
        assert response.status_code == 302
    assert _count(seeded, BodyMeasurement) == 1


# --- tracking: alimentos (Pro) ----------------------------------------------------

FOOD_OK = {"source": "basic", "code": "arroz-blanco-cocido", "grams": "200"}


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"grams": ""}, id="gramos-vacios"),
        pytest.param({"grams": "abc"}, id="gramos-texto"),
        pytest.param({"grams": "0"}, id="gramos-cero"),
        pytest.param({"grams": "-50"}, id="gramos-negativos"),
        pytest.param({"grams": "5000,1"}, id="gramos-sobre-maximo"),
        pytest.param({"grams": "nan"}, id="gramos-nan"),
        pytest.param({"grams": "inf"}, id="gramos-inf"),
        pytest.param({"grams": "1e400"}, id="gramos-desbordados"),
        pytest.param({"source": "manual"}, id="origen-inventado"),
        pytest.param({"source": ""}, id="origen-vacio"),
        pytest.param({"code": "no-existe"}, id="alimento-inexistente"),
        pytest.param({"code": XSS}, id="codigo-html"),
        pytest.param({"source": "off", "code": "' OR 1=1;--"}, id="codigo-inyeccion"),
    ],
)
def test_adding_a_food_refuses_bad_input_and_writes_nothing(
    account: FlaskClient, seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:
    response = account.post(
        "/diario/alimentos", data={**FOOD_OK, **overrides}, follow_redirects=True
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert _explains(html)
    assert "<img src=x onerror" not in html
    assert _count(seeded, FoodEntry) == 0
    assert _count(seeded, IntakeLog) == 0
    assert _count(seeded, ActivityLog) == 0


@pytest.mark.parametrize("grams", ["0,1", "5000", " 150 "])
def test_adding_a_food_accepts_the_limits(
    account: FlaskClient, seeded: SQLAlchemy, grams: str
) -> None:
    response = account.post("/diario/alimentos", data={**FOOD_OK, "grams": grams})
    assert response.status_code == 302
    assert _count(seeded, FoodEntry) == 1


@pytest.mark.parametrize("fecha", ["2099-01-01", "no-es-fecha", "2026-02-30"])
def test_a_food_for_a_bad_or_future_day_lands_on_today(
    account: FlaskClient, seeded: SQLAlchemy, fecha: str
) -> None:
    """Decisión de diseño: la fecha mala no se rechaza, se lleva a hoy (nunca al futuro)."""
    assert account.post("/diario/alimentos", data={**FOOD_OK, "fecha": fecha}).status_code == 302
    assert seeded.session.scalar(select(FoodEntry.logged_on)) == _today(seeded)


@pytest.mark.parametrize("entry_id", ["0", "12345"])
def test_deleting_a_food_that_does_not_exist_is_harmless(
    account: FlaskClient, seeded: SQLAlchemy, entry_id: str
) -> None:
    account.post("/diario/alimentos", data=FOOD_OK)
    assert account.post(f"/diario/alimentos/{entry_id}/borrar").status_code == 302
    assert _count(seeded, FoodEntry) == 1


@pytest.mark.xfail(
    strict=True, reason="BUG-1: un id enorme en la URL desborda el INTEGER de SQL y da 500"
)
def test_deleting_a_food_with_a_huge_id_is_harmless(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    assert account.post(f"/diario/alimentos/{HUGE_ID}/borrar").status_code in {302, 404}


@pytest.mark.xfail(strict=True, reason="BUG-3: «Copiar ayer» enviado dos veces duplica la comida")
def test_copying_yesterday_twice_does_not_duplicate(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    account.post("/diario/alimentos", data={**FOOD_OK, "fecha": _yesterday(seeded)})
    today = _today(seeded).isoformat()
    for _ in range(2):
        assert account.post("/diario/alimentos/copiar", data={"fecha": today}).status_code == 302
    assert _count(seeded, FoodEntry) == 2  # ayer + una copia hoy, no dos


def test_copying_an_empty_yesterday_writes_nothing(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    response = account.post("/diario/alimentos/copiar", data={"fecha": "basura"})
    assert response.status_code == 302
    assert _count(seeded, FoodEntry) == 0
    assert _count(seeded, IntakeLog) == 0
    assert _count(seeded, ActivityLog) == 0


# --- nutrition -------------------------------------------------------------------


@pytest.mark.parametrize("meal", ["", "abc", "0", "99", "-1", HUGE_ID, "1.5"])
def test_logging_a_meal_that_is_not_on_the_menu_is_refused(
    planned: FlaskClient, seeded: SQLAlchemy, meal: str
) -> None:
    assert planned.post("/nutricion/menu/apuntar", data={"comida": meal}).status_code == 400
    assert _count(seeded, FoodEntry) == 0


@pytest.mark.xfail(
    strict=True, reason="BUG-4: apuntar dos veces la misma comida del menú la duplica"
)
def test_logging_the_same_planned_meal_twice_does_not_duplicate(
    planned: FlaskClient, seeded: SQLAlchemy
) -> None:
    assert planned.post("/nutricion/menu/apuntar", data={"comida": "1"}).status_code == 302
    once = _count(seeded, FoodEntry)
    assert once > 0
    planned.post("/nutricion/menu/apuntar", data={"comida": "1"})
    assert _count(seeded, FoodEntry) == once


# --- workouts --------------------------------------------------------------------


def _set_payload(item: RoutineExercise, **overrides: Any) -> dict[str, Any]:
    return {
        "routine_exercise_id": item.id,
        "set_index": "1",
        "weight_kg": "60",
        "reps": "8",
        "rir": "2",
        "set_type": "working",
        **overrides,
    }


SET_BAD_INPUT = [
    ({"routine_exercise_id": ""}, "sin-ejercicio"),
    ({"routine_exercise_id": "abc"}, "ejercicio-texto"),
    ({"set_index": ""}, "sin-serie"),
    ({"set_index": "0"}, "serie-cero"),
    ({"set_index": "21"}, "serie-21"),
    ({"set_index": "-1"}, "serie-negativa"),
    ({"set_index": "abc"}, "serie-texto"),
    ({"weight_kg": ""}, "sin-peso"),
    ({"weight_kg": "abc"}, "peso-texto"),
    ({"weight_kg": "-1"}, "peso-negativo"),
    ({"weight_kg": "1000,1"}, "peso-sobre-maximo"),
    ({"weight_kg": "nan"}, "peso-nan"),
    ({"weight_kg": "inf"}, "peso-inf"),
    ({"weight_kg": "-inf"}, "peso-menos-inf"),
    ({"reps": ""}, "sin-reps"),
    ({"reps": "-1"}, "reps-negativas"),
    ({"reps": "201"}, "reps-sobre-maximo"),
    ({"reps": "8.5"}, "reps-decimales"),
    ({"reps": HUGE_ID}, "reps-enormes"),
    ({"rir": "11"}, "rir-sobre-maximo"),
    ({"rir": "-1"}, "rir-negativo"),
    ({"rir": "dos"}, "rir-texto"),
    ({"set_type": "WORKING"}, "tipo-mayusculas"),
    ({"set_type": "dropset"}, "tipo-fuera-de-opciones"),
]


@pytest.mark.parametrize("overrides", [pytest.param(o, id=name) for o, name in SET_BAD_INPUT])
def test_logging_a_set_refuses_bad_input_and_writes_nothing(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:
    client, session_id, item = live
    response = client.post(
        f"/entreno/{session_id}/serie", data=_set_payload(item, **overrides), follow_redirects=True
    )
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, SetLog) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"weight_kg": "0", "reps": "0", "rir": "0"}, id="ceros"),
        pytest.param({"weight_kg": "1000", "reps": "200", "rir": "10"}, id="maximos"),
        pytest.param({"weight_kg": "62,5"}, id="coma-decimal"),
        pytest.param({"rir": ""}, id="sin-rir"),
        pytest.param({"set_type": "warmup"}, id="calentamiento"),
    ],
)
def test_logging_a_set_accepts_the_limits(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy, overrides: dict[str, str]
) -> None:
    client, session_id, item = live
    assert (
        client.post(
            f"/entreno/{session_id}/serie", data=_set_payload(item, **overrides)
        ).status_code
        == 302
    )
    assert _count(seeded, SetLog) == 1


def test_a_set_beyond_the_prescription_is_refused(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy
) -> None:
    client, session_id, item = live
    too_far = item.sets + 3  # dentro del 1-20 del formulario, fuera de lo prescrito + 2
    response = client.post(
        f"/entreno/{session_id}/serie",
        data=_set_payload(item, set_index=str(too_far)),
        follow_redirects=True,
    )
    assert "Número de serie fuera de rango" in response.get_data(as_text=True)
    assert _count(seeded, SetLog) == 0


def test_the_same_set_sent_twice_is_stored_once(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy
) -> None:
    client, session_id, item = live
    for _ in range(2):
        client.post(f"/entreno/{session_id}/serie", data=_set_payload(item))
    assert _count(seeded, SetLog) == 1


def test_a_set_for_an_exercise_of_another_day_is_refused(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy
) -> None:
    client, session_id, item = live
    other_day = _routine(seeded).days[1].exercises[0]
    for target in (other_day.id, 0, -1, 999_999):
        response = client.post(
            f"/entreno/{session_id}/serie", data=_set_payload(item, routine_exercise_id=target)
        )
        assert response.status_code == 404, target
    assert _count(seeded, SetLog) == 0


@pytest.mark.xfail(
    strict=True, reason="BUG-2: un id enorme en un campo oculto desborda el INTEGER de SQL"
)
@pytest.mark.parametrize(
    ("endpoint", "overrides"),
    [
        ("serie", {"routine_exercise_id": HUGE_ID}),
        ("sustituir", {"routine_exercise_id": HUGE_ID}),
        ("sustituir", {"exercise_id": HUGE_ID}),
    ],
    ids=["serie", "sustituir-prescripcion", "sustituir-ejercicio"],
)
def test_a_huge_hidden_id_is_refused_without_crashing(
    live: tuple[FlaskClient, int, RoutineExercise],
    seeded: SQLAlchemy,
    endpoint: str,
    overrides: dict[str, str],
) -> None:
    client, session_id, item = live
    response = client.post(
        f"/entreno/{session_id}/{endpoint}", data=_set_payload(item, **overrides)
    )
    assert response.status_code in {302, 400, 404}
    assert _count(seeded, SetLog) == 0


@pytest.mark.xfail(
    strict=True, reason="BUG-1: un id enorme en la URL desborda el INTEGER de SQL y da 500"
)
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("get", "/resumen"),
        ("post", "/serie"),
        ("post", "/estado"),
        ("post", "/sustituir"),
        ("post", "/terminar"),
        ("post", "/abandonar"),
    ],
)
def test_a_huge_session_id_in_the_url_is_a_404(
    live: tuple[FlaskClient, int, RoutineExercise], method: str, suffix: str
) -> None:
    client, _session_id, _item = live
    assert getattr(client, method)(f"/entreno/{HUGE_ID}{suffix}").status_code == 404


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"exercise_id": "abc"}, id="ejercicio-texto"),
        pytest.param({"routine_exercise_id": ""}, id="sin-prescripcion"),
        pytest.param({"exercise_id": "1.5"}, id="ejercicio-decimal"),
    ],
)
def test_a_malformed_substitution_changes_nothing(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy, data: dict[str, str]
) -> None:
    client, session_id, item = live
    response = client.post(
        f"/entreno/{session_id}/sustituir",
        data={"routine_exercise_id": item.id, **data},
        follow_redirects=True,
    )
    assert "Petición no válida" in response.get_data(as_text=True)
    assert seeded.session.get(WorkoutSession, session_id).substitutions == {}


def test_a_substitution_that_is_not_an_alternative_is_refused(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy
) -> None:
    from app.models import Exercise

    client, session_id, item = live
    seeded.session.expire_all()
    unrelated = seeded.session.scalar(
        select(Exercise).where(Exercise.primary_muscle != item.exercise.primary_muscle)
    )
    assert unrelated is not None
    response = client.post(
        f"/entreno/{session_id}/sustituir",
        data={"routine_exercise_id": item.id, "exercise_id": unrelated.id},
        follow_redirects=True,
    )
    assert "no es una alternativa válida" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.get(WorkoutSession, session_id).substitutions == {}


@pytest.mark.xfail(
    strict=True,
    reason="BUG-11: un exercise_id inexistente se toma como «restaurar el original» y borra "
    "la sustitución que hubiera",
)
def test_a_substitution_with_an_unknown_exercise_is_refused(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy
) -> None:
    from app.services import onboarding, workouts

    client, session_id, item = live
    seeded.session.expire_all()
    session = seeded.session.get(WorkoutSession, session_id)
    user = _user(seeded)
    profile = onboarding.current_profile(user)
    equipment = frozenset(row.code for row in user.equipment)
    from app.services import dashboard

    alternatives = dashboard.usable_alternatives(item, profile, equipment)
    assert alternatives, "el primer ejercicio necesita alguna alternativa para esta prueba"
    workouts.substitute(session, item, alternatives[0], profile, equipment)
    seeded.session.commit()

    response = client.post(
        f"/entreno/{session_id}/sustituir",
        data={"routine_exercise_id": item.id, "exercise_id": 999_999},
        follow_redirects=True,
    )
    assert _explains(response.get_data(as_text=True))
    seeded.session.expire_all()
    assert seeded.session.get(WorkoutSession, session_id).substitutions == {
        str(item.id): alternatives[0].id
    }


@pytest.mark.parametrize("answer", ["", "GOOD", "fatal", XSS], ids=_short)
def test_how_you_arrive_only_takes_the_known_answers(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy, answer: str
) -> None:
    client, session_id, _item = live
    assert client.post(f"/entreno/{session_id}/estado", data={"sueno": answer}).status_code == 400
    seeded.session.expire_all()
    assert seeded.session.get(WorkoutSession, session_id).sleep_quality is None


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"perceived_fatigue": "0"}, id="fatiga-cero"),
        pytest.param({"perceived_fatigue": "6"}, id="fatiga-seis"),
        pytest.param({"perceived_fatigue": "abc"}, id="fatiga-texto"),
        pytest.param({"perceived_fatigue": "3.5"}, id="fatiga-decimal"),
        pytest.param({"perceived_fatigue": "3", "notes": "x" * 501}, id="notas-501"),
    ],
)
def test_finishing_with_bad_input_keeps_the_session_open(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy, data: dict[str, str]
) -> None:
    client, session_id, _item = live
    response = client.post(f"/entreno/{session_id}/terminar", data=data, follow_redirects=True)
    assert "Revisa el formulario de cierre" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert seeded.session.get(WorkoutSession, session_id).finished_at is None


def test_finishing_accepts_the_limits_and_escapes_the_notes(
    live: tuple[FlaskClient, int, RoutineExercise], seeded: SQLAlchemy
) -> None:
    client, session_id, item = live
    client.post(f"/entreno/{session_id}/serie", data=_set_payload(item))
    notes = (XSS * 10)[:500]
    response = client.post(
        f"/entreno/{session_id}/terminar",
        data={"perceived_fatigue": "5", "notes": notes},
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<img src=x onerror" not in html
    seeded.session.expire_all()
    assert seeded.session.get(WorkoutSession, session_id).perceived_fatigue == 5


@pytest.mark.parametrize("day_index", ["0", "99"])
def test_starting_a_day_that_does_not_exist_is_a_404(
    planned: FlaskClient, seeded: SQLAlchemy, day_index: str
) -> None:
    assert planned.post(f"/entreno/empezar/{day_index}").status_code == 404
    assert _count(seeded, WorkoutSession) == 0


# --- training ---------------------------------------------------------------------


def test_swapping_an_exercise_with_a_bad_id_changes_nothing(
    planned: FlaskClient, seeded: SQLAlchemy
) -> None:
    day = _routine(seeded).days[0]
    other_day = _routine(seeded).days[1].exercises[0]
    before = [row.exercise_id for row in day.exercises]
    for value in ("", "abc", "0", str(other_day.id), HUGE_ID, "1.5"):
        response = planned.post("/entrenamiento/dia/1/cambiar", data={"routine_exercise_id": value})
        assert response.status_code == 404, value
    assert planned.post("/entrenamiento/dia/99/cambiar", data={}).status_code == 404
    seeded.session.expire_all()
    assert [row.exercise_id for row in _routine(seeded).days[0].exercises] == before


@pytest.mark.parametrize("slug", ["", "no-existe", XSS, "' OR 1=1;--", LONG], ids=_short)
def test_allowing_an_unknown_exercise_again_is_harmless(
    planned: FlaskClient, seeded: SQLAlchemy, slug: str
) -> None:
    response = planned.post("/entrenamiento/permitir", data={"slug": slug})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/entrenamiento")


# --- main: tema e idioma ------------------------------------------------------------


@pytest.mark.parametrize("lang", ["", "xx", "ES", "en-GB", XSS, LONG], ids=_short)
def test_an_unknown_language_changes_nothing(
    account: FlaskClient, seeded: SQLAlchemy, lang: str
) -> None:
    response = account.post("/idioma", data={"lang": lang})
    assert response.status_code == 302
    assert _user(seeded).locale == "es"


@pytest.mark.parametrize(
    "target", ["https://evil.example/", "//evil.example", "javascript:alert(1)", "evil.example"]
)
def test_theme_and_language_never_redirect_off_site(client: FlaskClient, target: str) -> None:
    for path, data in (("/tema", {}), ("/idioma", {"lang": "en"})):
        location = client.post(path, data={**data, "next": target}).headers["Location"]
        assert "evil.example" not in location, (path, location)
        assert not location.startswith("javascript"), (path, location)


# Los navegadores leen «\» como «/» y se saltan tabuladores y saltos de línea:
# «/\evil.example» o «/<TAB>/evil.example» acabarían siendo «//evil.example», otra web.
# Hoy no pasa (Werkzeug codifica la barra como %5C y urlsplit quita el tabulador): esto
# lo vigila.
BROWSER_NORMALISED = ["/\\evil.example", "/\t/evil.example", "/\n/evil.example"]


def _leaves_the_site(location: str) -> bool:
    cleaned = location.replace("\\", "/").replace("\t", "").replace("\n", "").replace("\r", "")
    return cleaned.startswith("//") or "evil.example" in cleaned.split("/")[2:3]


@pytest.mark.parametrize("target", BROWSER_NORMALISED, ids=["barra-invertida", "tab", "salto"])
def test_theme_and_language_refuse_targets_browsers_turn_into_another_site(
    client: FlaskClient, target: str
) -> None:
    for path, data in (("/tema", {}), ("/idioma", {"lang": "en"})):
        location = client.post(path, data={**data, "next": target}).headers["Location"]
        assert not _leaves_the_site(location), (path, location)


@pytest.mark.parametrize("target", BROWSER_NORMALISED, ids=["barra-invertida", "tab", "salto"])
def test_login_refuses_next_targets_browsers_turn_into_another_site(
    client: FlaskClient, database: SQLAlchemy, target: str
) -> None:
    _signed_up(client)
    client.post("/salir")
    response = client.post(
        "/entrar",
        query_string={"next": target},
        data={"email": "ana@example.com", "password": PASSWORD},
    )
    assert response.status_code == 302
    assert not _leaves_the_site(response.headers["Location"])


# --- privacy: consentimiento ---------------------------------------------------------


@pytest.mark.parametrize("password", ["", "mala", LONG], ids=_short)
def test_withdrawing_consent_needs_the_right_password(
    planned: FlaskClient, seeded: SQLAlchemy, password: str
) -> None:
    response = planned.post("/cuenta/consentimiento/retirar", data={"current_password": password})
    assert response.status_code == 200
    assert "La contraseña no es correcta" in response.get_data(as_text=True)
    assert _user(seeded).has_health_consent
    assert _count(seeded, Profile) == 1


@pytest.mark.parametrize("value", ["", "n", "Y", "on", "yes"])
def test_giving_consent_needs_the_box_ticked(
    account: FlaskClient, seeded: SQLAlchemy, value: str
) -> None:
    account.post("/cuenta/consentimiento/retirar", data={"current_password": PASSWORD})
    assert not _user(seeded).has_health_consent
    response = account.post("/consentimiento", data={"health_consent": value})
    assert response.status_code == 200
    assert "Marca la casilla" in response.get_data(as_text=True)
    assert not _user(seeded).has_health_consent
    assert account.post("/consentimiento", data={"health_consent": "y"}).status_code == 302
    assert _user(seeded).has_health_consent


# --- imports: Hevy --------------------------------------------------------------------


def _hevy(row: str = "", *, end: str = "10 Nov 2026, 19:35") -> bytes:
    start = f'"Push A","10 Nov 2026, 18:30","{end}","",'
    body = row or '"Bench Press (Barbell)","","",1,"normal",80,8,,,8'
    return ("﻿" + HEVY_HEADER + "\n" + start + body + "\n").encode("utf-8")


def _upload(client: FlaskClient, data: bytes) -> Any:
    return client.post(
        "/cuenta/importar/hevy",
        data={"archivo": (io.BytesIO(data), "workouts.csv")},
        content_type="multipart/form-data",
    )


def _confirm(client: FlaskClient, page: str) -> Any:
    token = re.search(r'name="token" value="([^"]+)"', page)
    assert token is not None
    pairs = dict(re.findall(r'name="(par-\d+)" list="ejercicios-alza"\s*value="([^"]*)"', page))
    return client.post("/cuenta/importar/hevy/confirmar", data={"token": token.group(1), **pairs})


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="vacio"),
        pytest.param(b"\x00\x01\xff" * 50, id="binario"),
        pytest.param(b"a,b\n1,2\n", id="otro-csv"),
        pytest.param((HEVY_HEADER + "\n").encode(), id="solo-cabecera"),
    ],
)
def test_a_file_that_is_not_an_export_is_explained(
    planned: FlaskClient, seeded: SQLAlchemy, data: bytes
) -> None:
    response = _upload(planned, data)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, WorkoutSession) == 0


def test_upload_without_a_file_is_explained(planned: FlaskClient, seeded: SQLAlchemy) -> None:
    response = planned.post("/cuenta/importar/hevy", data={}, content_type="multipart/form-data")
    assert response.status_code == 200
    assert "Elige el fichero CSV" in response.get_data(as_text=True)


@pytest.mark.parametrize("token", ["", "../../etc/passwd", "x" * 41, "abc", LONG], ids=_short)
def test_confirming_with_a_forged_token_imports_nothing(
    planned: FlaskClient, seeded: SQLAlchemy, token: str
) -> None:
    response = planned.post(
        "/cuenta/importar/hevy/confirmar", data={"token": token}, follow_redirects=True
    )
    assert "La vista previa ha caducado" in response.get_data(as_text=True)
    assert _count(seeded, WorkoutSession) == 0


def test_hevy_names_never_come_back_as_html(planned: FlaskClient, seeded: SQLAlchemy) -> None:
    row = '"<script>alert(1)</script>","","",1,"normal",80,8,,,8'
    page = _upload(planned, _hevy(row)).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_confirming_twice_imports_once(planned: FlaskClient, seeded: SQLAlchemy) -> None:
    page = _upload(planned, _hevy()).get_data(as_text=True)
    assert _confirm(planned, page).status_code == 302
    replay = _confirm(planned, page)
    assert replay.status_code == 302
    assert _count(seeded, WorkoutSession) == 1


HEVY_ODD_ROWS_HANDLED = [
    ('"Bench Press (Barbell)","","",1,"normal",-80,8,,,8', "peso-negativo"),
    ('"Bench Press (Barbell)","","",1,"normal",80,500,,,8', "reps-500"),
    ('"Bench Press (Barbell)","","",1,"normal",abc,8,,,8', "peso-texto"),
    ('"Bench Press (Barbell)","","",1,"normal",80,8,,,15', "rpe-15"),
]


@pytest.mark.parametrize("row", [pytest.param(r, id=name) for r, name in HEVY_ODD_ROWS_HANDLED])
def test_odd_hevy_values_are_clamped_not_fatal(
    planned: FlaskClient, seeded: SQLAlchemy, row: str
) -> None:
    page = _upload(planned, _hevy(row))
    assert page.status_code == 200
    assert _confirm(planned, page.get_data(as_text=True)).status_code == 302


@pytest.mark.xfail(strict=True, reason="BUG-8: NaN o infinito en reps/RPE del CSV de Hevy da 500")
@pytest.mark.parametrize(
    "row",
    [
        pytest.param('"Bench Press (Barbell)","","",1,"normal",80,nan,,,8', id="reps-nan"),
        pytest.param('"Bench Press (Barbell)","","",1,"normal",80,inf,,,8', id="reps-inf"),
        pytest.param('"Bench Press (Barbell)","","",1,"normal",80,8,,,nan', id="rpe-nan"),
        pytest.param('"Bench Press (Barbell)","","",1,"normal",80,8,,,inf', id="rpe-inf"),
    ],
)
def test_hevy_upload_survives_nan_and_infinity(
    planned: FlaskClient, seeded: SQLAlchemy, row: str
) -> None:
    response = _upload(planned, _hevy(row))
    assert response.status_code == 200


@pytest.mark.xfail(
    strict=True, reason="BUG-9: valores del CSV fuera de las CHECK de la base dan 500 al importar"
)
@pytest.mark.parametrize(
    ("row", "end"),
    [
        pytest.param(
            '"Bench Press (Barbell)","","",1,"normal",5000,8,,,8',
            "10 Nov 2026, 19:35",
            id="peso-5000",
        ),
        pytest.param(
            '"Bench Press (Barbell)","","",1,"normal",nan,8,,,8',
            "10 Nov 2026, 19:35",
            id="peso-nan",
        ),
        pytest.param(
            '"Bench Press (Barbell)","","",-5,"normal",80,8,,,8',
            "10 Nov 2026, 19:35",
            id="serie-negativa",
        ),
        pytest.param(
            '"Bench Press (Barbell)","","",1,"normal",80,8,,,8',
            "10 Nov 2026, 17:00",
            id="fin-antes-que-inicio",
        ),
    ],
)
def test_hevy_confirm_survives_values_outside_the_database_limits(
    planned: FlaskClient, seeded: SQLAlchemy, row: str, end: str
) -> None:
    page = _upload(planned, _hevy(row, end=end))
    assert page.status_code == 200
    assert _confirm(planned, page.get_data(as_text=True)).status_code == 302


# --- billing ---------------------------------------------------------------------------


@pytest.mark.parametrize("plan", ["", "gold", "MONTHLY", XSS, LONG], ids=_short)
def test_starting_an_unknown_plan_is_explained_and_charges_nothing(
    account: FlaskClient, seeded: SQLAlchemy, plan: str
) -> None:

    response = account.post("/suscripcion/empezar", data={"plan": plan}, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert _explains(html)
    assert "<img src=x onerror" not in html
    assert _count(seeded, Subscription) == 0


@pytest.mark.parametrize(
    "path",
    [
        "/suscripcion/cancelar",
        "/suscripcion/reanudar",
        "/suscripcion/desistir",
        "/suscripcion/gestionar",
    ],
)
def test_subscription_actions_without_a_subscription_are_explained(
    account: FlaskClient, seeded: SQLAlchemy, path: str
) -> None:
    response = account.post(path, follow_redirects=True)
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))


@pytest.mark.parametrize("body", [b"", b"junk", b'{"type": "checkout.session.completed"}'])
def test_the_webhook_refuses_unsigned_bodies(
    client: FlaskClient, database: SQLAlchemy, body: bytes
) -> None:

    response = client.post(
        "/suscripcion/webhook", data=body, headers={"Stripe-Signature": "t=1,v1=bad"}
    )
    assert response.status_code == 400
    assert _count(database, Subscription) == 0


@pytest.mark.parametrize("token", ["x", "no.es.un.token", LONG[:500]], ids=_short)
def test_a_forged_simulated_checkout_charges_nothing(
    account: FlaskClient, seeded: SQLAlchemy, token: str
) -> None:

    response = account.post(
        f"/suscripcion/simulada/pago/{token}", data={"outcome": "pay"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert _explains(response.get_data(as_text=True))
    assert _count(seeded, Subscription) == 0


# --- review -----------------------------------------------------------------------------


def test_applying_a_review_without_a_plan_is_explained(
    account: FlaskClient, seeded: SQLAlchemy
) -> None:
    response = account.post("/revision/aplicar", data={"anything": XSS}, follow_redirects=True)
    assert response.status_code == 200
    assert "<img src=x onerror" not in response.get_data(as_text=True)
    assert _count(seeded, Profile) == 0
