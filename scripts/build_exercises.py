"""Build ``app/seeds/exercises.json`` and the exercise images from free-exercise-db.

Usage (from the project root, inside the venv)::

    python scripts/build_exercises.py [--dataset PATH] [--skip-images]

Steps:
1. Load the source dataset (downloaded to ``scripts/cache/`` when missing).
2. For every entry of ``scripts/exercise_catalogue.py`` merge the curated data
   with the source record (English name, instructions, mechanic, force, level,
   muscles, images).
3. Download the two source images per exercise, resize them to at most
   560 px wide and store them under ``app/static/img/exercises/<slug>/``.
4. Compute alternatives (same pattern and primary muscle, other equipment).
5. Validate everything against the domain enums and the equipment codes, then
   write the JSON sorted by slug.

Source: https://github.com/yuhonas/free-exercise-db (The Unlicense).
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from functools import partial
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.exercise_catalogue import CATALOGUE  # noqa: E402

# Pasos en castellano, escritos a partir de las instrucciones originales (dominio
# público) y revisados uno a uno: breves, en el orden de las fotos del ejercicio.
INSTRUCTIONS_ES: dict[str, str] = json.loads(
    (Path(__file__).resolve().parent / "exercise_instructions_es.json").read_text(encoding="utf-8")
)

from app.engine.enums import (  # noqa: E402
    Force,
    InjuryArea,
    Mechanic,
    MovementPattern,
    MuscleGroup,
    Severity,
    TechnicalLevel,
)

logger = logging.getLogger("build_exercises")

DATASET_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMAGE_BASE_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
CACHE_DIR = ROOT / "scripts" / "cache"
IMAGES_DIR = ROOT / "app" / "static" / "img" / "exercises"
OUTPUT_FILE = ROOT / "app" / "seeds" / "exercises.json"
EQUIPMENT_FILE = ROOT / "app" / "seeds" / "equipment.json"

MAX_IMAGE_WIDTH = 560
JPEG_QUALITY = 75
MAX_ALTERNATIVES = 4

SOURCE_MUSCLES: dict[str, str | None] = {
    "abdominals": "abs",
    "abductors": "glutes",
    "adductors": "adductors",
    "biceps": "biceps",
    "calves": "calves",
    "chest": "chest",
    "forearms": "forearms",
    "glutes": "glutes",
    "hamstrings": "hamstrings",
    "lats": "back",
    "lower back": "lower_back",
    "middle back": "back",
    "neck": None,
    "quadriceps": "quads",
    "shoulders": "shoulders",
    "traps": "traps",
    "triceps": "triceps",
}

# Equipment that loads the movement; anything else means a bodyweight exercise.
LOADED_EQUIPMENT = {
    "barbell",
    "ez_bar",
    "trap_bar",
    "dumbbells",
    "kettlebell",
    "medicine_ball",
    "cable_machine",
    "lat_pulldown",
    "seated_row_machine",
    "smith_machine",
    "leg_press",
    "hack_squat",
    "leg_extension",
    "leg_curl",
    "chest_press_machine",
    "shoulder_press_machine",
    "pec_deck",
    "calf_raise_machine",
    "hip_thrust_machine",
    "hip_abductor_adductor_machine",
    "arm_curl_machine",
    "resistance_bands",
}


class BuildError(RuntimeError):
    """A curated entry does not match the source data or the domain vocabulary."""


def slugify(source_id: str) -> str:
    """``Barbell_Bench_Press_-_Medium_Grip`` -> ``barbell-bench-press-medium-grip``."""
    slug = re.sub(r"[^a-z0-9]+", "-", source_id.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def load_dataset(path: Path | None) -> dict[str, dict[str, Any]]:
    """Return the source exercises keyed by id, downloading the dataset if needed."""
    if path is None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / "exercises.json"
        if not path.exists():
            logger.info("Downloading dataset to %s", path)
            with urllib.request.urlopen(DATASET_URL, timeout=60) as response:
                path.write_bytes(response.read())
    with path.open(encoding="utf-8") as handle:
        records = json.load(handle)
    return {record["id"]: record for record in records}


def load_equipment_codes() -> set[str]:
    """Codes defined in ``equipment.json``; every exercise must only use these."""
    with EQUIPMENT_FILE.open(encoding="utf-8") as handle:
        return {row["code"] for row in json.load(handle)}


def fetch_image(source_id: str, index: int) -> bytes:
    """Download one source image."""
    url = IMAGE_BASE_URL + urllib.parse.quote(f"{source_id}/{index}.jpg")
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def store_image(data: bytes, target: Path) -> None:
    """Resize to ``MAX_IMAGE_WIDTH`` and save as an optimised JPEG."""
    with Image.open(io.BytesIO(data)) as image:
        rgb = image.convert("RGB")
        if rgb.width > MAX_IMAGE_WIDTH:
            ratio = MAX_IMAGE_WIDTH / rgb.width
            rgb = rgb.resize((MAX_IMAGE_WIDTH, round(rgb.height * ratio)), Image.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(target, format="JPEG", quality=JPEG_QUALITY, optimize=True)


def ensure_images(source_id: str, slug: str, source_images: list[str]) -> list[str]:
    """Download missing images; return the relative static paths that exist."""
    paths: list[str] = []
    for index, _ in enumerate(source_images[:2]):
        target = IMAGES_DIR / slug / f"{index}.jpg"
        if not target.exists():
            logger.info("Fetching image %s/%s", source_id, index)
            store_image(fetch_image(source_id, index), target)
        paths.append(f"img/exercises/{slug}/{index}.jpg")
    return paths


def video_search_url(name_en: str) -> str:
    """YouTube search for a demonstration (decision T-25: search link, not a fixed video)."""
    query = urllib.parse.quote_plus(f"{name_en} exercise proper form")
    return f"https://www.youtube.com/results?search_query={query}"


def map_muscles(names: list[str], primary: str) -> list[str]:
    """Translate source muscle names to ``MuscleGroup`` values, dropping the primary."""
    mapped: list[str] = []
    for name in names:
        if name not in SOURCE_MUSCLES:
            raise BuildError(f"Unknown source muscle {name!r}")
        value = SOURCE_MUSCLES[name]
        if value and value != primary and value not in mapped:
            mapped.append(value)
    return mapped


def build_entry(
    entry: dict[str, Any], source: dict[str, Any], equipment_codes: set[str], skip_images: bool
) -> dict[str, Any]:
    """Merge one curated entry with its source record."""
    slug = entry.get("slug") or slugify(entry["id"])
    primary = MuscleGroup(entry["primary"]).value
    pattern = MovementPattern(entry["pattern"]).value
    equipment = list(entry["eq"])
    unknown = set(equipment) - equipment_codes
    if unknown:
        raise BuildError(f"{entry['id']}: unknown equipment codes {sorted(unknown)}")
    level = TechnicalLevel(entry.get("level") or source["level"]).value
    mechanic = Mechanic(source["mechanic"] or "compound").value
    force = Force(source["force"] or "static").value
    contraindications = [
        {"area": InjuryArea(area).value, "min_severity": Severity(severity).value}
        for area, severity in entry.get("contra", [])
    ]
    secondary = entry.get("secondary")
    if secondary is None:
        secondary = map_muscles(source.get("secondaryMuscles", []), primary)
    else:
        secondary = [MuscleGroup(muscle).value for muscle in secondary]

    images = [] if skip_images else ensure_images(entry["id"], slug, source.get("images", []))
    return {
        "slug": slug,
        "source_id": entry["id"],
        "name_es": entry["es"],
        "name_en": source["name"],
        "primary_muscle": primary,
        "secondary_muscles": secondary,
        "movement_pattern": pattern,
        "mechanic": mechanic,
        "force": force,
        "technical_level": level,
        "is_unilateral": bool(entry.get("unilateral", False)),
        "is_bodyweight": not any(code in LOADED_EQUIPMENT for code in equipment),
        "equipment": equipment,
        "contraindications": contraindications,
        "instructions_en": "\n".join(source.get("instructions", [])) or None,
        "instructions_es": INSTRUCTIONS_ES.get(slug),
        "video_url": video_search_url(source["name"]),
        "image_path": images[0] if images else None,
        "images": images,
        "alternatives": [],
    }


def _alternative_rank(current: dict[str, Any], other: dict[str, Any]) -> tuple[int, int, str]:
    """Sort key: other equipment first, then same mechanic, then slug."""
    same_equipment = set(other["equipment"]) == set(current["equipment"])
    same_mechanic = other["mechanic"] == current["mechanic"]
    return (1 if same_equipment else 0, 0 if same_mechanic else 1, other["slug"])


def compute_alternatives(exercises: list[dict[str, Any]]) -> None:
    """Fill ``alternatives``: same pattern and primary muscle, preferring other equipment."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for exercise in exercises:
        by_key[(exercise["movement_pattern"], exercise["primary_muscle"])].append(exercise)
    for exercise in exercises:
        candidates = [
            other
            for other in by_key[(exercise["movement_pattern"], exercise["primary_muscle"])]
            if other["slug"] != exercise["slug"]
        ]

        candidates.sort(key=partial(_alternative_rank, exercise))
        exercise["alternatives"] = [
            {
                "slug": other["slug"],
                "priority": position,
                "reason": f"Mismo patrón ({exercise['movement_pattern']}) y músculo "
                f"({exercise['primary_muscle']}); material: {', '.join(other['equipment'])}",
            }
            for position, other in enumerate(candidates[:MAX_ALTERNATIVES], start=1)
        ]


def summarise(exercises: list[dict[str, Any]]) -> str:
    """Human-readable counts per pattern and per primary muscle."""
    patterns = Counter(e["movement_pattern"] for e in exercises)
    muscles = Counter(e["primary_muscle"] for e in exercises)
    lines = [
        f"total: {len(exercises)}",
        "patterns: " + ", ".join(f"{k}={v}" for k, v in sorted(patterns.items())),
    ]
    lines.append("muscles: " + ", ".join(f"{k}={v}" for k, v in sorted(muscles.items())))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=None, help="local copy of exercises.json")
    parser.add_argument("--skip-images", action="store_true", help="do not download images")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    dataset = load_dataset(args.dataset)
    equipment_codes = load_equipment_codes()
    exercises: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in CATALOGUE:
        if entry["id"] in seen_ids:
            raise BuildError(f"Duplicated catalogue id {entry['id']!r}")
        seen_ids.add(entry["id"])
        source = dataset.get(entry["id"])
        if source is None:
            raise BuildError(f"Source id not found in dataset: {entry['id']!r}")
        exercises.append(build_entry(entry, source, equipment_codes, args.skip_images))

    slugs = Counter(e["slug"] for e in exercises)
    duplicated = [slug for slug, count in slugs.items() if count > 1]
    if duplicated:
        raise BuildError(f"Duplicated slugs: {duplicated}")

    compute_alternatives(exercises)
    exercises.sort(key=lambda e: e["slug"])
    OUTPUT_FILE.write_text(
        json.dumps(exercises, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    logger.info("Wrote %s", OUTPUT_FILE)
    logger.info("%s", summarise(exercises))
    return 0


if __name__ == "__main__":
    sys.exit(main())
