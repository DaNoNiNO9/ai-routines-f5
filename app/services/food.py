"""Logging food in seconds: a basic table, Open Food Facts, barcodes and your usual foods.

Search looks first in Alza's own table of common foods (``seeds/basic_foods.json``,
average values, works without network) and then in Open Food Facts products sold
in Spain (``search.openfoodfacts.org``). A barcode goes to the product API. The
only things sent to Open Food Facts are the words searched and the barcode; never
anything about the person.

Open Food Facts is open data written by volunteers: a product without calories,
protein, carbohydrates or fat is left out rather than shown with invented zeros,
and kilojoules are converted when the kilocalories are missing.

A day with logged foods has its ``IntakeLog`` totals worked out from them, so the
fortnightly review keeps reading the same table as before.
"""

from __future__ import annotations

import json
import logging
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app
from flask_babel import get_locale
from sqlalchemy import func, select

from app.extensions import db
from app.models import FoodEntry, IntakeLog, User
from app.services import tracking

logger = logging.getLogger(__name__)

BASIC_FOODS_FILE = Path(__file__).resolve().parent.parent / "seeds" / "basic_foods.json"
SEARCH_URL = "https://search.openfoodfacts.org/search"
PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
USER_AGENT = "Alza - https://alza.fit"
TIMEOUT_SECONDS = 6
CACHE_SECONDS = 24 * 3600
MAX_RESULTS = 12
KJ_PER_KCAL = 4.184
OFF_FIELDS = "code,product_name,product_name_es,product_name_en,brands,nutriments,serving_quantity"

# (url) -> parsed JSON. Swapped in tests; ``OFF_ENABLED=False`` turns the network off.
Fetcher = Callable[[str], dict[str, Any]]


class FoodError(Exception):
    """Something the person can be told (``reason`` is a stable code)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Food:
    """A food with its values per 100 g."""

    source: str  # basic | off
    code: str
    name: str
    brand: str | None
    kcal: float
    protein: float
    carbs: float
    fat: float
    portion: float = 100.0


def _plain(text: str) -> str:
    """Lower case without accents, for matching «platano» with «Plátano»."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _english() -> bool:
    return str(get_locale() or "es").startswith("en")


@lru_cache(maxsize=1)
def _basic_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = json.loads(BASIC_FOODS_FILE.read_text(encoding="utf-8"))
    return tuple(rows)


def _basic(row: dict[str, Any]) -> Food:
    return Food(
        source="basic",
        code=row["key"],
        name=row["en"] if _english() else row["es"],
        brand=None,
        kcal=float(row["kcal"]),
        protein=float(row["p"]),
        carbs=float(row["c"]),
        fat=float(row["f"]),
        portion=float(row["portion"]),
    )


def basic_food(key: str) -> Food | None:
    """One food of the basic table by its key."""
    row = next((row for row in _basic_rows() if row["key"] == key), None)
    return _basic(row) if row else None


def search_basic(query: str) -> list[Food]:
    """Foods of the basic table whose name holds every word searched."""
    words = _plain(query).split()
    if not words:
        return []
    found = []
    for row in _basic_rows():
        names = _plain(f"{row['es']} {row['en']}")
        if all(word in names for word in words):
            found.append(_basic(row))
    return found


def _fetch(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data: dict[str, Any] = json.loads(response.read())
            return data
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Open Food Facts unreachable: %s", exc)
        raise FoodError("off_unreachable") from exc


_cache: dict[str, tuple[float, Any]] = {}


def _cached(url: str, fetcher: Fetcher) -> dict[str, Any]:
    hit = _cache.get(url)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        cached: dict[str, Any] = hit[1]
        return cached
    data = fetcher(url)
    if len(_cache) > 500:
        _cache.clear()
    _cache[url] = (time.monotonic(), data)
    return data


def _fetcher() -> Fetcher | None:
    if not current_app.config.get("OFF_ENABLED", True):
        return None
    custom = current_app.config.get("OFF_FETCHER")
    return custom if callable(custom) else _fetch


def _from_off(product: dict[str, Any], code: str | None = None) -> Food | None:
    """A product, or ``None`` if it lacks any of the four values."""
    values = product.get("nutriments") or {}
    kcal = values.get("energy-kcal_100g")
    if kcal is None and values.get("energy-kj_100g") is not None:
        kcal = float(values["energy-kj_100g"]) / KJ_PER_KCAL
    numbers = [
        kcal,
        values.get("proteins_100g"),
        values.get("carbohydrates_100g"),
        values.get("fat_100g"),
    ]
    if any(value is None for value in numbers):
        return None
    try:
        kcal_f, protein, carbs, fat = (float(value) for value in numbers)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not 0 <= kcal_f <= 950 or min(protein, carbs, fat) < 0:
        return None
    lang = "en" if _english() else "es"
    name = (product.get(f"product_name_{lang}") or product.get("product_name") or "").strip()
    if not name:
        return None
    brands = product.get("brands")
    brand = ", ".join(brands) if isinstance(brands, list) else (brands or None)
    serving = product.get("serving_quantity")
    try:
        portion = float(serving) if serving else 100.0
    except (TypeError, ValueError):
        portion = 100.0
    return Food(
        source="off",
        code=str(code or product.get("code") or ""),
        name=name[:160],
        brand=(brand or "").split(",")[0].strip()[:120] or None,
        kcal=round(kcal_f, 1),
        protein=round(protein, 1),
        carbs=round(carbs, 1),
        fat=round(fat, 1),
        portion=portion if 0 < portion <= 2000 else 100.0,
    )


def search_off(query: str) -> list[Food]:
    """Products sold in Spain that match; ``FoodError`` if Open Food Facts does not answer."""
    fetcher = _fetcher()
    if fetcher is None or len(query.strip()) < 2:
        return []
    params = urllib.parse.urlencode(
        {
            "q": f'{query.strip()} countries_tags:"en:spain"',
            "langs": "en,es" if _english() else "es",
            "page_size": str(MAX_RESULTS * 2),
            "fields": OFF_FIELDS,
        }
    )
    data = _cached(f"{SEARCH_URL}?{params}", fetcher)
    found = [food for hit in data.get("hits") or [] if (food := _from_off(hit))]
    return found[:MAX_RESULTS]


def search(query: str) -> tuple[list[Food], bool]:
    """Basic table first, then Open Food Facts; also whether Open Food Facts failed."""
    basics = search_basic(query)
    try:
        products = search_off(query)
    except FoodError:
        return basics, True
    return [*basics, *products][: MAX_RESULTS + len(basics)], False


def by_barcode(code: str) -> Food:
    """The product with that barcode; ``FoodError`` if unknown or incomplete."""
    digits = "".join(char for char in code if char.isdigit())
    if not 6 <= len(digits) <= 14:
        raise FoodError("bad_barcode")
    fetcher = _fetcher()
    if fetcher is None:
        raise FoodError("off_unreachable")
    data = _cached(PRODUCT_URL.format(code=digits) + f"?fields={OFF_FIELDS}", fetcher)
    if data.get("status") != 1 or not data.get("product"):
        raise FoodError("barcode_not_found")
    food = _from_off(data["product"], digits)
    if food is None:
        raise FoodError("barcode_incomplete")
    return food


# --- The diary -----------------------------------------------------------------


def entries(user: User, day: date) -> list[FoodEntry]:
    """Foods logged on a day, in the order they were added."""
    return list(
        db.session.scalars(
            select(FoodEntry)
            .where(FoodEntry.user_id == user.id, FoodEntry.logged_on == day)
            .order_by(FoodEntry.id)
        )
    )


@dataclass(frozen=True)
class Totals:
    """Sum of a day's foods."""

    kcal: float
    protein: float
    carbs: float
    fat: float


def totals(rows: list[FoodEntry]) -> Totals:
    """Add up a day's foods."""
    return Totals(
        kcal=sum(row.kcal for row in rows),
        protein=sum(row.protein_g for row in rows),
        carbs=sum(row.carbs_g for row in rows),
        fat=sum(row.fat_g for row in rows),
    )


def refresh_intake(user: User, day: date) -> None:
    """The day's ``IntakeLog`` follows its foods (adherence and notes are kept)."""
    rows = entries(user, day)
    intake = db.session.scalar(
        select(IntakeLog).where(IntakeLog.user_id == user.id, IntakeLog.logged_on == day)
    )
    if not rows:
        if intake is not None and intake.adherence_pct is None and not intake.notes:
            db.session.delete(intake)
        elif intake is not None:
            intake.calories, intake.protein_g, intake.carbs_g, intake.fat_g = 0, None, None, None
        return
    sums = totals(rows)
    tracking.upsert_intake(
        user,
        day,
        round(sums.kcal),
        protein_g=round(sums.protein, 1),
        carbs_g=round(sums.carbs, 1),
        fat_g=round(sums.fat, 1),
        adherence_pct=intake.adherence_pct if intake else None,
        notes=intake.notes if intake else None,
    )


def add(user: User, day: date, food: Food, grams: float) -> FoodEntry:
    """Log ``grams`` of ``food`` on ``day``."""
    if not 0 < grams <= 5000:
        raise FoodError("bad_grams")
    row = FoodEntry(
        user=user,
        logged_on=day,
        name=food.name,
        brand=food.brand,
        source=food.source,
        code=food.code or None,
        grams=round(grams, 1),
        kcal_100g=food.kcal,
        protein_100g=food.protein,
        carbs_100g=food.carbs,
        fat_100g=food.fat,
    )
    db.session.add(row)
    db.session.flush()
    refresh_intake(user, day)
    return row


def remove(user: User, entry_id: int) -> date | None:
    """Delete one of the person's foods; the day it was on, or ``None`` if not theirs."""
    row = db.session.get(FoodEntry, entry_id)
    if row is None or row.user_id != user.id:
        return None
    day = row.logged_on
    db.session.delete(row)
    db.session.flush()
    refresh_intake(user, day)
    return day


def copy_day(user: User, source: date, target: date) -> int:
    """Log again on ``target`` everything eaten on ``source``; how many foods."""
    rows = entries(user, source)
    for row in rows:
        db.session.add(
            FoodEntry(
                user=user,
                logged_on=target,
                name=row.name,
                brand=row.brand,
                source=row.source,
                code=row.code,
                grams=row.grams,
                kcal_100g=row.kcal_100g,
                protein_100g=row.protein_100g,
                carbs_100g=row.carbs_100g,
                fat_100g=row.fat_100g,
            )
        )
    if rows:
        db.session.flush()
        refresh_intake(user, target)
    return len(rows)


def usual(user: User, limit: int = 8) -> list[tuple[Food, float]]:
    """The foods logged most often, with the grams used last time."""
    counted = db.session.execute(
        select(FoodEntry.name, FoodEntry.code, func.count(), func.max(FoodEntry.id))
        .where(FoodEntry.user_id == user.id)
        .group_by(FoodEntry.name, FoodEntry.code)
        .order_by(func.count().desc(), func.max(FoodEntry.id).desc())
        .limit(limit)
    ).all()
    found = []
    for _name, _code, _times, last_id in counted:
        row = db.session.get(FoodEntry, last_id)
        if row is None:
            continue
        food = Food(
            source=row.source,
            code=row.code or "",
            name=row.name,
            brand=row.brand,
            kcal=row.kcal_100g,
            protein=row.protein_100g,
            carbs=row.carbs_100g,
            fat=row.fat_100g,
            portion=row.grams,
        )
        found.append((food, row.grams))
    return found
