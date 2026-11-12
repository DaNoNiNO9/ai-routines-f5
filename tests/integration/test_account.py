"""Account settings, downloads and deletion through HTTP."""

from __future__ import annotations

import io
import zipfile

from flask.testing import FlaskClient
from flask_sqlalchemy import SQLAlchemy
from pypdf import PdfReader
from sqlalchemy import func, select

from app.models import Plan, Profile, SetLog, User, WeightLog, WorkoutSession
from app.services import auth as auth_service
from tests.integration.test_onboarding import _fill_all, _register, _signup

PASSWORD = "una contraseña larga"


def _user(database: SQLAlchemy, email: str = "ana@example.com") -> User:
    user = auth_service.find_by_email(email)
    assert user is not None
    return user


def test_the_account_page_needs_a_session(client: FlaskClient, database: SQLAlchemy) -> None:
    for path in ("/cuenta", "/cuenta/plan.pdf", "/cuenta/datos.zip"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/entrar" in response.headers["Location"], path


def test_the_page_shows_every_section(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    page = client.get("/cuenta").get_data(as_text=True)
    for text in (
        "Datos de la cuenta",
        "Correo y contraseña",
        "Llévate tus datos",
        "Borrar la cuenta",
        "ana@example.com",
        "Europe/Madrid",
        "BORRAR",
    ):
        assert text in page, text
    assert "Todavía no hay plan" in page  # sin cuestionario todavía


def test_profile_changes_are_saved_and_validated(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    saved = client.post(
        "/cuenta/perfil",
        data={"display_name": "Ana María", "locale": "en", "timezone": "America/Bogota"},
        follow_redirects=True,
    )
    # Se acaba de elegir inglés: la confirmación ya llega en inglés.
    assert "Saved." in saved.get_data(as_text=True)
    seeded.session.expire_all()
    user = _user(seeded)
    assert user.display_name == "Ana María"
    assert user.locale == "en"
    assert user.timezone == "America/Bogota"

    bad = client.post(
        "/cuenta/perfil",
        data={"display_name": "Ana", "locale": "es", "timezone": "Marte/Olimpo"},
    )
    # El formulario se rechaza entero, así que la cuenta sigue en inglés.
    assert "That time zone does not exist" in bad.get_data(as_text=True)
    seeded.session.expire_all()
    assert _user(seeded).timezone == "America/Bogota"


def test_changing_the_email_needs_the_password(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    wrong = client.post(
        "/cuenta/correo", data={"email": "nueva@example.com", "current_password": "otra cosa"}
    )
    assert "La contraseña no es correcta" in wrong.get_data(as_text=True)
    assert auth_service.find_by_email("nueva@example.com") is None

    ok = client.post(
        "/cuenta/correo",
        data={"email": "Nueva@Example.com", "current_password": PASSWORD},
        follow_redirects=True,
    )
    assert "Correo actualizado" in ok.get_data(as_text=True)
    seeded.session.expire_all()
    assert auth_service.find_by_email("nueva@example.com") is not None
    assert auth_service.find_by_email("ana@example.com") is None

    # The new address is the one that signs in.
    client.post("/salir")
    assert (
        client.post(
            "/entrar", data={"email": "nueva@example.com", "password": PASSWORD}
        ).status_code
        == 302
    )


def test_an_email_already_taken_is_refused(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    client.post("/salir", follow_redirects=True)
    assert _register(client, email="otra@example.com").status_code == 302
    response = client.post(
        "/cuenta/correo", data={"email": "ana@example.com", "current_password": PASSWORD}
    )
    assert "Ya existe una cuenta con ese correo" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert _user(seeded, "otra@example.com").email == "otra@example.com"


def test_changing_the_password(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    nueva = "otra contraseña bien larga"

    wrong = client.post(
        "/cuenta/contrasena",
        data={"current_password": "no es", "password": nueva, "password_confirm": nueva},
    )
    assert "La contraseña no es correcta" in wrong.get_data(as_text=True)

    weak = client.post(
        "/cuenta/contrasena",
        data={"current_password": PASSWORD, "password": "corta", "password_confirm": "corta"},
    )
    assert "al menos 10 caracteres" in weak.get_data(as_text=True)

    mismatch = client.post(
        "/cuenta/contrasena",
        data={"current_password": PASSWORD, "password": nueva, "password_confirm": "otra distinta"},
    )
    assert "no coinciden" in mismatch.get_data(as_text=True)

    ok = client.post(
        "/cuenta/contrasena",
        data={"current_password": PASSWORD, "password": nueva, "password_confirm": nueva},
        follow_redirects=True,
    )
    assert "Contraseña actualizada" in ok.get_data(as_text=True)
    client.post("/salir")
    assert (
        client.post("/entrar", data={"email": "ana@example.com", "password": PASSWORD}).status_code
        == 200
    )
    assert (
        client.post("/entrar", data={"email": "ana@example.com", "password": nueva}).status_code
        == 302
    )


def test_the_pdf_download(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    assert client.get("/cuenta/plan.pdf").headers["Location"].endswith("/cuestionario")

    _fill_all(client)
    client.post("/cuestionario/revisar")
    response = client.get("/cuenta/plan.pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert 'filename="alza-plan-ana-' in response.headers["Content-Disposition"]
    assert response.data.startswith(b"%PDF-")

    reader = PdfReader(io.BytesIO(response.data))
    texto = "\n".join(page.extract_text() for page in reader.pages)
    plan = seeded.session.scalar(select(Plan))
    assert str(plan.calorie_target) in texto
    assert "herramienta orientativa" in texto


def test_the_data_archive_download(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    client.post("/diario/peso", data={"day": _user(seeded).today().isoformat(), "weight_kg": "70"})
    response = client.get("/cuenta/datos.zip")
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert 'filename="alza-datos-ana-' in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "no-store"

    with zipfile.ZipFile(io.BytesIO(response.data)) as zipped:
        assert zipped.testzip() is None
        assert "pesajes.csv" in zipped.namelist()
        assert "70.0" in zipped.read("pesajes.csv").decode("utf-8-sig")


def test_deleting_the_account_asks_twice(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    _fill_all(client)
    client.post("/cuestionario/revisar")

    wrong_word = client.post(
        "/cuenta/borrar", data={"current_password": PASSWORD, "confirmation": "borrar"}
    )
    assert "Escribe BORRAR exactamente" in wrong_word.get_data(as_text=True)

    wrong_password = client.post(
        "/cuenta/borrar", data={"current_password": "no es", "confirmation": "BORRAR"}
    )
    assert "La contraseña no es correcta" in wrong_password.get_data(as_text=True)
    seeded.session.expire_all()
    assert auth_service.find_by_email("ana@example.com") is not None


def test_deleting_the_account_erases_everything(client: FlaskClient, seeded: SQLAlchemy) -> None:
    _signup(client)
    _fill_all(client)
    client.post("/cuestionario/revisar")
    client.post("/entreno/empezar/1")
    session = seeded.session.scalar(select(WorkoutSession))
    routine_item = session.routine_day.exercises[0]
    client.post(
        f"/entreno/{session.id}/serie",
        data={
            "routine_exercise_id": routine_item.id,
            "set_index": 1,
            "weight_kg": "60",
            "reps": "8",
            "rir": "2",
            "set_type": "working",
        },
    )
    client.post("/diario/peso", data={"day": _user(seeded).today().isoformat(), "weight_kg": "70"})
    seeded.session.expire_all()
    assert seeded.session.scalar(select(func.count()).select_from(SetLog)) == 1

    done = client.post(
        "/cuenta/borrar",
        data={"current_password": PASSWORD, "confirmation": "BORRAR"},
        follow_redirects=True,
    )
    assert "se han borrado" in done.get_data(as_text=True)
    assert done.history[0].headers["Clear-Site-Data"] == '"cache", "storage"'
    seeded.session.expire_all()

    for model in (User, Profile, Plan, WeightLog, WorkoutSession, SetLog):
        assert seeded.session.scalar(select(func.count()).select_from(model)) == 0, model.__name__
    # The session is gone too: the account page sends you to sign in.
    assert "/entrar" in client.get("/cuenta").headers["Location"]


def test_deleting_one_account_leaves_the_others_alone(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    _fill_all(client)
    client.post("/cuestionario/revisar")
    client.post("/salir", follow_redirects=True)

    assert _register(client, email="otra@example.com").status_code == 302
    _fill_all(client)
    client.post("/cuestionario/revisar")
    client.post(
        "/cuenta/borrar",
        data={"current_password": PASSWORD, "confirmation": "BORRAR"},
        follow_redirects=True,
    )
    seeded.session.expire_all()

    assert auth_service.find_by_email("otra@example.com") is None
    superviviente = auth_service.find_by_email("ana@example.com")
    assert superviviente is not None
    assert seeded.session.scalar(select(func.count()).select_from(Plan)) == 1
    assert seeded.session.scalar(select(Plan)).user_id == superviviente.id


def test_a_malformed_email_is_refused_before_the_password_check(
    client: FlaskClient, seeded: SQLAlchemy
) -> None:
    _signup(client)
    response = client.post(
        "/cuenta/correo", data={"email": "no-es-un-correo", "current_password": PASSWORD}
    )
    assert response.status_code == 200
    assert "Correo y contraseña" in response.get_data(as_text=True)
    seeded.session.expire_all()
    assert _user(seeded).email == "ana@example.com"


def test_the_pdf_of_a_blocked_plan_explains_why(client: FlaskClient, seeded: SQLAlchemy) -> None:
    from tests.integration.test_onboarding import _post_step

    _signup(client)
    for number in range(1, 7):
        _post_step(client, number)
    _post_step(client, 7, is_pregnant_or_breastfeeding="y")
    client.post("/cuestionario/revisar")

    response = client.get("/cuenta/plan.pdf")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF-")
    texto = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.data)).pages)
    assert "No hay plan de nutrición" in texto
    assert "embarazo" in texto.lower()
