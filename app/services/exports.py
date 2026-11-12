"""Exports: the plan as a PDF and every personal record as a ZIP of CSV files.

The PDF is laid out with ReportLab (pure Python, no system libraries). The
archive is what a person is entitled to take with them: one CSV per kind of
record plus a readme explaining the columns.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from flask_babel import gettext as _
from flask_babel import ngettext
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select

from app import formatting
from app.engine import messages
from app.engine.types import Note
from app.extensions import db
from app.labels import BMR_METHOD, BODY_FAT_METHOD, GOAL, MEAL_TIMING, label
from app.models import (
    ActivityLog,
    BodyMeasurement,
    IntakeLog,
    Plan,
    PlanAdjustment,
    Profile,
    Routine,
    SetLog,
    User,
    WeightLog,
    WorkoutSession,
)
from app.services import plans as plans_service

ACCENT = colors.HexColor("#b34b00")
INK = colors.HexColor("#15171c")
MUTED = colors.HexColor("#5a6170")
RULE = colors.HexColor("#d7dae2")


def _disclaimer() -> str:
    """El mismo aviso que el pie de la web, en el idioma de quien lee."""
    return _(
        "Alza es una herramienta orientativa. No sustituye el consejo de un médico, "
        "dietista-nutricionista ni de ningún otro profesional sanitario."
    )


@dataclass(frozen=True)
class Sheet:
    """One CSV inside the archive."""

    name: str
    header: Sequence[str]
    rows: Sequence[Sequence[Any]]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "alza-title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=29,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "eyebrow": ParagraphStyle(
            "alza-eyebrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=ACCENT,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "alza-h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=INK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "alza-h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "alza-body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=INK,
            spaceAfter=4,
        ),
        "muted": ParagraphStyle(
            "alza-muted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
            spaceAfter=3,
        ),
    }


def _table(data: list[list[Any]], widths: list[float], *, numeric_from: int = 1) -> Table:
    """A table with the project's look: header rule, thin row rules, numbers right."""
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, RULE),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _brand_mark(canvas: Any, x: float, y: float, size: float) -> None:
    """The Alza mark (an upward A) with its bottom-left corner at ``x, y``.

    Same 32-unit geometry as ``components/brand.html`` and ``scripts/build_brand.py``.
    """
    unit = size / 32

    def point(px: float, py: float) -> tuple[float, float]:
        return x + px * unit, y + (32 - py) * unit  # SVG y grows downwards

    canvas.setFillColor(ACCENT)
    canvas.roundRect(x, y, size, size, 8 * unit, stroke=0, fill=1)
    canvas.setStrokeColor(colors.white)
    canvas.setLineWidth(3.4 * unit)
    canvas.setLineCap(1)
    canvas.setLineJoin(1)
    chevron = canvas.beginPath()
    chevron.moveTo(*point(9.5, 23.5))
    chevron.lineTo(*point(16, 9.5))
    chevron.lineTo(*point(22.5, 23.5))
    chevron.moveTo(*point(12.6, 18.5))
    chevron.lineTo(*point(19.4, 18.5))
    canvas.drawPath(chevron, stroke=1, fill=0)


def _page_furniture(canvas: Any, doc: Any) -> None:
    """Brand on top, disclaimer and page number at the bottom, on every page."""
    canvas.saveState()
    width, _height = A4
    top = doc.pagesize[1] - 12 * mm
    _brand_mark(canvas, 18 * mm, top - 1 * mm, 4.4 * mm)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(INK)
    canvas.drawString(18 * mm + 6 * mm, top, "ALZA")
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - 18 * mm, top, str(doc.alza_subtitle))
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, top - 3 * mm, width - 18 * mm, top - 3 * mm)

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    text = canvas.beginText(18 * mm, 14 * mm)
    for line in _wrap(_disclaimer(), 110):
        text.textLine(line)
    canvas.drawText(text)
    canvas.drawRightString(width - 18 * mm, 14 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def _wrap(text: str, width: int) -> list[str]:
    """Very small word wrapper for the fixed-width footer."""
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _round(value: Any, digits: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return formatting.num(number, digits)


def plan_pdf(
    user: User,
    plan: Plan | None,
    routine: Routine | None,
    profile: Profile,
    today: date,
    *,
    blocked_reasons: Sequence[str] = (),
) -> bytes:
    """The plan as a PDF: nutrition, how it was calculated, and the routine.

    Works with no plan too: then it prints the reasons safety stopped it, which
    is exactly what a person needs to take to a professional.
    """
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
        title=_("Alza · plan de %(name)s", name=user.display_name),
        author="Alza",
        subject=_("Plan de nutrición y entrenamiento"),
    )
    document.alza_subtitle = f"{user.display_name} · {today.strftime('%d/%m/%Y')}"
    flow: list[Any] = []

    flow.append(Paragraph(_("Plan de nutrición y entrenamiento").upper(), styles["eyebrow"]))
    flow.append(Paragraph(user.display_name, styles["title"]))
    flow.append(
        Paragraph(
            _(
                "Generado el %(date)s · cuestionario v%(version)s · objetivo: %(goal)s",
                date=today.strftime("%d/%m/%Y"),
                version=profile.version,
                goal=label(GOAL, profile.goal).lower(),
            ),
            styles["muted"],
        )
    )
    flow.append(Spacer(1, 8))

    if plan is None:
        flow.append(Paragraph(_("No hay plan de nutrición"), styles["h2"]))
        flow.append(
            Paragraph(
                _("Con tus respuestas no se puede calcular un plan con seguridad:"),
                styles["body"],
            )
        )
        for reason in blocked_reasons:
            flow.append(Paragraph(f"• {reason}", styles["body"]))
    else:
        flow.extend(_nutrition_pages(plan, profile, styles))

    if routine is not None:
        flow.append(PageBreak())
        flow.extend(_routine_pages(routine, styles))

    document.build(flow, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return buffer.getvalue()


def _meal_name(meal: Any) -> str:
    """El nombre de la comida, marcando las que rodean al entrenamiento."""
    if meal.timing.value in ("pre_workout", "post_workout"):
        return f"{meal.name} ({label(MEAL_TIMING, meal.timing).lower()})"
    return str(meal.name)


def _nutrition_pages(plan: Plan, profile: Profile, styles: dict[str, ParagraphStyle]) -> list[Any]:
    details = plan.details or {}
    target = details.get("target") or {}
    body = details.get("body") or {}
    bmr = details.get("bmr") or {}
    spent = details.get("expenditure") or {}
    hydration = details.get("hydration") or {}
    flow: list[Any] = []

    flow.append(Paragraph(_("Objetivo diario"), styles["h2"]))
    flow.append(
        _table(
            [
                [
                    _("Calorías"),
                    _("Proteína"),
                    _("Carbohidratos"),
                    _("Grasa"),
                    _("Fibra"),
                    _("Agua"),
                ],
                [
                    f"{plan.calorie_target} kcal",
                    f"{_round(plan.protein_g)} g",
                    f"{_round(plan.carbs_g)} g",
                    f"{_round(plan.fat_g)} g",
                    f"{_round(plan.fiber_g)} g",
                    f"{formatting.num(plan.water_ml / 1000)} l",
                ],
            ],
            [30 * mm] * 6,
            numeric_from=0,
        )
    )
    flow.append(Spacer(1, 6))
    # La primera frase es la del motor: misma redacción que en la pantalla.
    modo = target.get("mode")
    cabeza = messages.render(
        Note(
            f"target.{modo if modo in ('deficit', 'surplus') else 'maintenance'}",
            params={"pct": round(float(target.get("fraction", 0)) * 100, 1)},
        )
    )
    detalle = _(
        "Para mantenerte gastas unas %(tdee)s kcal al día; con este plan el cambio previsto es "
        "de %(change)s kg a la semana. Los días de entreno, %(water)s l de agua.",
        tdee=_round(target.get("maintenance_kcal")),
        change=formatting.signed(target.get("expected_weekly_change_kg"), 2),
        water=formatting.num(hydration.get("training_day_ml", 0) / 1000),
    )
    flow.append(Paragraph(f"{cabeza} {detalle}", styles["body"]))

    if plan.meals:
        flow.append(Paragraph(_("Reparto por comidas"), styles["h2"]))
        filas = [[_("Comida"), "kcal", _("Proteína"), _("Carbohidratos"), _("Grasa")]]
        filas += [
            [
                _meal_name(meal),
                str(meal.calories),
                f"{_round(meal.protein_g)} g",
                f"{_round(meal.carbs_g)} g",
                f"{_round(meal.fat_g)} g",
            ]
            for meal in plan.meals
        ]
        flow.append(_table(filas, [60 * mm, 25 * mm, 30 * mm, 30 * mm, 25 * mm]))

    cycle = details.get("carb_cycle")
    if isinstance(cycle, dict):
        alto, bajo = cycle.get("high_day", {}), cycle.get("low_day", {})
        flow.append(Paragraph(_("Más hidratos los días de entreno"), styles["h3"]))
        flow.append(
            Paragraph(
                _(
                    "%(td)s días de entreno con %(hc)s g de carbohidratos (%(hk)s kcal) y "
                    "%(rd)s de descanso con %(lc)s g (%(lk)s kcal). La media de la semana es "
                    "la del plan.",
                    td=cycle.get("training_days"),
                    hc=alto.get("carbs_g"),
                    hk=alto.get("calories"),
                    rd=cycle.get("rest_days"),
                    lc=bajo.get("carbs_g"),
                    lk=bajo.get("calories"),
                ),
                styles["body"],
            )
        )

    flow.append(Paragraph(_("Cómo se ha calculado"), styles["h2"]))
    composicion = [
        [_("Dato"), _("Valor")],
        [_("Peso"), f"{_round(body.get('weight_kg'), 1)} kg"],
        [_("Altura"), f"{_round(body.get('height_cm'), 0)} cm"],
        [_("IMC"), _round(body.get("bmi"), 1)],
        [
            _("Grasa corporal"),
            f"{_round(body.get('body_fat_pct'), 1)} %"
            if body.get("body_fat_pct") is not None
            else _("sin estimación"),
        ],
        [
            _("Método"),
            label(BODY_FAT_METHOD, body.get("body_fat_source"))
            if body.get("body_fat_pct") is not None
            else "—",
        ],
        [
            _("Masa magra"),
            f"{_round(body.get('lean_mass_kg'), 1)} kg" if body.get("lean_mass_kg") else "—",
        ],
        [_("Metabolismo basal"), f"{_round(bmr.get('selected_kcal'))} kcal"],
        [_("Fórmula del basal"), label(BMR_METHOD, bmr.get("method"))],
        [_("Gasto por actividad diaria"), f"{_round(spent.get('neat_kcal'))} kcal"],
        [_("Gasto por ejercicio"), f"{_round(spent.get('eat_kcal'))} kcal"],
        [_("Mantenimiento"), f"{_round(spent.get('maintenance_kcal'))} kcal"],
    ]
    flow.append(_table(composicion, [70 * mm, 60 * mm]))
    flow.append(
        Paragraph(
            _(
                "Grasa por perímetros con la fórmula de la Marina de EE. UU.; metabolismo basal "
                "por Katch-McArdle o Mifflin-St Jeor; gasto sumando el basal, lo que caminas, el "
                "ejercicio y la digestión. El plan nunca baja del mínimo seguro de calorías ni "
                "hace perder más del 1 %% del peso a la semana."
            ),
            styles["muted"],
        )
    )

    avisos = plans_service.messages_of(details)
    if avisos:
        flow.append(Paragraph(_("A tener en cuenta"), styles["h3"]))
        for item in avisos:
            flow.append(Paragraph(f"• {item['text']}", styles["muted"]))
    del profile
    return flow


def _routine_pages(routine: Routine, styles: dict[str, ParagraphStyle]) -> list[Any]:
    details = routine.details or {}
    flow: list[Any] = [
        Paragraph(_("Rutina"), styles["h2"]),
        Paragraph(routine.name, styles["h3"]),
    ]
    rir = details.get("weekly_rir") or []
    resumen = ngettext(
        "%(num)s día a la semana · bloques de %(weeks)s semanas con una semana suave cada "
        "%(deload)s",
        "%(num)s días a la semana · bloques de %(weeks)s semanas con una semana suave cada "
        "%(deload)s",
        routine.days_per_week,
        weeks=routine.mesocycle_weeks,
        deload=routine.deload_every_weeks,
    )
    if rir:
        valores = ", ".join(str(value) for value in rir)
        resumen += " · " + _("reserva por semana: %(rir)s", rir=valores)
    flow.append(Paragraph(resumen, styles["muted"]))

    for day in routine.days:
        filas = [[_("Ejercicio"), _("Series"), _("Repeticiones"), _("Reserva"), _("Descanso")]]
        filas += [
            [
                item.exercise.display_name,
                str(item.sets),
                f"{item.rep_min}-{item.rep_max}",
                _("de %(a)s a %(b)s", a=item.rir_start, b=item.rir_end),
                formatting.duration(item.rest_seconds),
            ]
            for item in day.exercises
        ]
        bloque = [
            Paragraph(f"{_('Día %(n)s', n=day.day_index)} · {day.name}", styles["h3"]),
            Paragraph(
                ngettext(
                    "%(num)s ejercicio · unos %(m)s minutos",
                    "%(num)s ejercicios · unos %(m)s minutos",
                    len(day.exercises),
                    m=day.estimated_minutes,
                ),
                styles["muted"],
            ),
            _table(filas, [70 * mm, 20 * mm, 25 * mm, 25 * mm, 25 * mm]),
        ]
        if day.notes:
            bloque.append(Paragraph(day.notes, styles["muted"]))
        flow.append(KeepTogether(bloque))

    cardio = details.get("cardio")
    if isinstance(cardio, dict):
        flow.append(Paragraph(_("Cardio y pasos"), styles["h3"]))
        partes = [_("%(n)s pasos al día", n=_round(cardio.get("daily_steps_target")))]
        if cardio.get("liss_sessions"):
            partes.append(
                _(
                    "%(n)s × %(m)s min de cardio suave a la semana",  # noqa: RUF001
                    n=cardio["liss_sessions"],
                    m=cardio["liss_minutes"],
                )
            )
        if cardio.get("hiit_sessions"):
            partes.append(
                _(
                    "%(n)s × %(m)s min de intervalos a la semana",  # noqa: RUF001
                    n=cardio["hiit_sessions"],
                    m=cardio["hiit_minutes"],
                )
            )
        flow.append(Paragraph(" · ".join(partes) + ".", styles["body"]))

    avisos = plans_service.messages_of(details)
    if avisos:
        flow.append(Paragraph(_("Cómo está montada"), styles["h3"]))
        for item in avisos:
            flow.append(Paragraph(f"• {item['text']}", styles["muted"]))
    return flow


def _sheet(name: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Sheet:
    return Sheet(name=name, header=header, rows=list(rows))


def personal_sheets(user: User) -> list[Sheet]:
    """Every record of ``user``, one sheet per kind, oldest first."""
    session = db.session
    profiles = session.scalars(
        select(Profile).where(Profile.user_id == user.id).order_by(Profile.version)
    ).all()
    weights = session.scalars(
        select(WeightLog).where(WeightLog.user_id == user.id).order_by(WeightLog.logged_on)
    ).all()
    intakes = session.scalars(
        select(IntakeLog).where(IntakeLog.user_id == user.id).order_by(IntakeLog.logged_on)
    ).all()
    activity = session.scalars(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.logged_on)
    ).all()
    measures = session.scalars(
        select(BodyMeasurement)
        .where(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.measured_on)
    ).all()
    plans_ = session.scalars(
        select(Plan).where(Plan.user_id == user.id).order_by(Plan.version)
    ).all()
    routines = session.scalars(
        select(Routine).where(Routine.user_id == user.id).order_by(Routine.version)
    ).all()
    adjustments = session.scalars(
        select(PlanAdjustment).where(PlanAdjustment.user_id == user.id).order_by(PlanAdjustment.id)
    ).all()
    sessions = session.scalars(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user.id)
        .order_by(WorkoutSession.started_at)
    ).all()
    sets = session.scalars(
        select(SetLog)
        .join(WorkoutSession, SetLog.workout_session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user.id)
        .order_by(SetLog.completed_at)
    ).all()

    return [
        _sheet(
            "cuenta.csv",
            [
                "correo",
                "nombre",
                "idioma",
                "zona_horaria",
                "alta",
                "ultimo_acceso",
                "consentimiento",
            ],
            [
                [
                    user.email,
                    user.display_name,
                    user.locale,
                    user.timezone,
                    user.created_at.isoformat(),
                    user.last_login_at.isoformat() if user.last_login_at else "",
                    user.consent_accepted_at.isoformat() if user.consent_accepted_at else "",
                ]
            ],
        ),
        _sheet(
            "cuestionarios.csv",
            [
                "version",
                "creado",
                "sustituido",
                "sexo",
                "nacimiento",
                "altura_cm",
                "peso_kg",
                "grasa_pct",
                "metodo_grasa",
                "trabajo",
                "pasos",
                "sueno_h",
                "estres",
                "experiencia",
                "dias",
                "minutos",
                "lugar",
                "objetivo",
                "ritmo",
                "comidas",
                "patron_dieta",
                "lesiones",
            ],
            [
                [
                    item.version,
                    item.created_at.isoformat(),
                    item.superseded_at.isoformat() if item.superseded_at else "",
                    item.sex.value,
                    item.birth_date.isoformat(),
                    item.height_cm,
                    item.weight_kg,
                    item.body_fat_pct if item.body_fat_pct is not None else "",
                    item.body_fat_method.value,
                    item.job_activity.value,
                    item.daily_steps if item.daily_steps is not None else "",
                    item.sleep_hours,
                    item.stress_level,
                    item.training_experience.value,
                    item.training_days_per_week,
                    item.session_minutes,
                    item.training_location.value,
                    item.goal.value,
                    item.aggressiveness.value,
                    item.meals_per_day,
                    item.diet_pattern.value,
                    "; ".join(
                        f"{lesion.area.value}:{lesion.severity.value}" for lesion in item.injuries
                    ),
                ]
                for item in profiles
            ],
        ),
        _sheet(
            "pesajes.csv",
            ["dia", "peso_kg", "nota"],
            [[item.logged_on.isoformat(), item.weight_kg, item.notes or ""] for item in weights],
        ),
        _sheet(
            "ingestas.csv",
            ["dia", "kcal", "proteina_g", "carbos_g", "grasa_g", "adherencia_pct", "nota"],
            [
                [
                    item.logged_on.isoformat(),
                    item.calories,
                    item.protein_g if item.protein_g is not None else "",
                    item.carbs_g if item.carbs_g is not None else "",
                    item.fat_g if item.fat_g is not None else "",
                    item.adherence_pct if item.adherence_pct is not None else "",
                    item.notes or "",
                ]
                for item in intakes
            ],
        ),
        _sheet(
            "actividad.csv",
            ["dia", "pasos", "tipo_cardio", "minutos_cardio", "nota"],
            [
                [
                    item.logged_on.isoformat(),
                    item.steps if item.steps is not None else "",
                    item.cardio_kind.value if item.cardio_kind else "",
                    item.cardio_minutes if item.cardio_minutes is not None else "",
                    item.notes or "",
                ]
                for item in activity
            ],
        ),
        _sheet(
            "perimetros.csv",
            [
                "dia",
                "cuello_cm",
                "pecho_cm",
                "cintura_cm",
                "cadera_cm",
                "brazo_cm",
                "muslo_cm",
                "gemelo_cm",
                "grasa_pct",
                "metodo",
            ],
            [
                [
                    item.measured_on.isoformat(),
                    item.neck_cm if item.neck_cm is not None else "",
                    item.chest_cm if item.chest_cm is not None else "",
                    item.waist_cm if item.waist_cm is not None else "",
                    item.hip_cm if item.hip_cm is not None else "",
                    item.arm_cm if item.arm_cm is not None else "",
                    item.thigh_cm if item.thigh_cm is not None else "",
                    item.calf_cm if item.calf_cm is not None else "",
                    item.body_fat_pct if item.body_fat_pct is not None else "",
                    item.body_fat_method.value,
                ]
                for item in measures
            ],
        ),
        _sheet(
            "planes.csv",
            [
                "version",
                "estado",
                "desde",
                "hasta",
                "kcal",
                "proteina_g",
                "carbos_g",
                "grasa_g",
                "fibra_g",
                "agua_ml",
                "bmr_kcal",
                "tdee_kcal",
                "metodo_bmr",
                "confianza",
            ],
            [
                [
                    item.version,
                    item.status.value,
                    item.starts_on.isoformat(),
                    item.ends_on.isoformat() if item.ends_on else "",
                    item.calorie_target,
                    item.protein_g,
                    item.carbs_g,
                    item.fat_g,
                    item.fiber_g,
                    item.water_ml,
                    item.bmr_kcal,
                    item.tdee_kcal,
                    item.bmr_method.value,
                    item.confidence.value,
                ]
                for item in plans_
            ],
        ),
        _sheet(
            "ajustes.csv",
            [
                "fecha",
                "plan_version",
                "motivo",
                "cambio_esperado_kg",
                "cambio_observado_kg",
                "tdee_observado",
                "delta_kcal",
                "delta_pasos",
                "explicacion",
            ],
            [
                [
                    item.created_at.isoformat(),
                    item.plan.version if item.plan else "",
                    item.reason.value,
                    item.expected_weekly_change_kg
                    if item.expected_weekly_change_kg is not None
                    else "",
                    item.observed_weekly_change_kg
                    if item.observed_weekly_change_kg is not None
                    else "",
                    item.observed_tdee_kcal if item.observed_tdee_kcal is not None else "",
                    item.calorie_delta if item.calorie_delta is not None else "",
                    item.steps_delta if item.steps_delta is not None else "",
                    item.explanation,
                ]
                for item in adjustments
            ],
        ),
        _sheet(
            "rutinas.csv",
            [
                "version",
                "estado",
                "nombre",
                "split",
                "dias",
                "semanas",
                "descarga",
                "desde",
                "dia",
                "posicion",
                "ejercicio",
                "series",
                "rep_min",
                "rep_max",
                "rir_inicio",
                "rir_fin",
                "descanso_s",
            ],
            [
                [
                    routine.version,
                    routine.status.value,
                    routine.name,
                    routine.split_type.value,
                    routine.days_per_week,
                    routine.mesocycle_weeks,
                    routine.deload_every_weeks,
                    routine.starts_on.isoformat() if routine.starts_on else "",
                    day.name,
                    item.position,
                    item.exercise.name_es,
                    item.sets,
                    item.rep_min,
                    item.rep_max,
                    item.rir_start,
                    item.rir_end,
                    item.rest_seconds,
                ]
                for routine in routines
                for day in routine.days
                for item in day.exercises
            ],
        ),
        _sheet(
            "sesiones.csv",
            ["inicio", "fin", "estado", "dia_rutina", "semana_mesociclo", "fatiga", "nota"],
            [
                [
                    item.started_at.isoformat(),
                    item.finished_at.isoformat() if item.finished_at else "",
                    item.status.value,
                    item.routine_day.name if item.routine_day else "",
                    item.mesocycle_week if item.mesocycle_week is not None else "",
                    item.perceived_fatigue if item.perceived_fatigue is not None else "",
                    item.notes or "",
                ]
                for item in sessions
            ],
        ),
        _sheet(
            "series.csv",
            ["momento", "sesion_inicio", "ejercicio", "serie", "tipo", "reps", "kg", "rir"],
            [
                [
                    item.completed_at.isoformat(),
                    item.session.started_at.isoformat(),
                    item.exercise.name_es,
                    item.set_index,
                    item.set_type.value,
                    item.reps,
                    item.weight_kg,
                    item.rir if item.rir is not None else "",
                ]
                for item in sets
            ],
        ),
    ]


def _readme() -> str:
    """Qué lleva el ZIP, en el idioma de quien lo descarga."""
    # El literal va sin sangrar a propósito: el texto del fichero es ese.
    return _(
        """Exportación de datos de Alza
============================

Un fichero por tipo de dato, en CSV con separador de coma y codificación
UTF-8 con BOM (se abre bien en Excel y en LibreOffice).

  cuenta.csv        Tus datos de cuenta.
  cuestionarios.csv Cada versión del cuestionario, con sus lesiones.
  pesajes.csv       Peso por día.
  ingestas.csv      Calorías, macros y adherencia por día.
  actividad.csv     Pasos y cardio por día.
  perimetros.csv    Medidas y porcentaje de grasa.
  planes.csv        Cada versión del plan de nutrición.
  ajustes.csv       Cada recálculo, con lo esperado, lo observado y el motivo.
  rutinas.csv       Cada rutina, una fila por ejercicio de cada día.
  sesiones.csv      Sesiones de entrenamiento.
  series.csv        Cada serie registrada.

Las fechas van en formato ISO (aaaa-mm-dd) y las horas en UTC.

Alza es una herramienta orientativa. No sustituye el consejo de un médico,
dietista-nutricionista ni de ningún otro profesional sanitario.
"""
    )


def data_archive(user: User) -> bytes:
    """Every record of ``user`` as a ZIP of CSV files, with a readme."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("LEEME.txt", _readme())
        for sheet in personal_sheets(user):
            text = io.StringIO(newline="")
            writer = csv.writer(text, lineterminator="\r\n")
            writer.writerow(sheet.header)
            writer.writerows(sheet.rows)
            # BOM so spreadsheets open the accents right.
            archive.writestr(sheet.name, "﻿" + text.getvalue())
    return buffer.getvalue()


def export_filename(user: User, today: date, extension: str) -> str:
    """``alza-plan-ana-rios-2026-09-09.pdf``-style name.

    Only ASCII: the name travels in a ``Content-Disposition`` header, and a
    header carrying "Ríos" (or a name in another script) would break it.
    """
    plain = unicodedata.normalize("NFKD", user.display_name)
    plain = plain.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    kind = "plan" if extension == "pdf" else "datos"
    return f"alza-{kind}-{stem or 'usuario'}-{today.isoformat()}.{extension}"
