r"""Descarga los vídeos de wger para nuestros ejercicios y los deja listos para la web.

wger (https://wger.de) publica sus vídeos con licencia CC-BY-SA 4.0. Los originales
van en HEVC a 1080p o 4K (hasta 400 MB): Chrome y Firefox en Windows no reproducen
HEVC y pesan demasiado para el móvil. Cada vídeo se convierte a H.264 640x360, sin
sonido, con ``faststart`` (empieza a reproducirse antes de bajar entero) y un
fotograma de portada. La conversión es una obra derivada: se publica con la misma
licencia y con la autoría original (``app/static/video/exercises/CREDITS.json``).

El emparejamiento es a mano (``VIDEOS``): solo cuando el ejercicio de wger es el
mismo que el nuestro. Un emparejamiento automático por nombre confundía «Barbell
Curl» con «Barbell Wrist Curl», y un vídeo equivocado es peor que ninguno.

Uso (necesita ffmpeg en el PATH):
    .venv\Scripts\python.exe scripts\build_videos.py [carpeta-de-descargas]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "video" / "exercises"
API = "https://wger.de/api/v2/video/{id}/"
USER_AGENT = "alza-exercise-catalogue"

# slug de nuestro catálogo -> (id del ejercicio en wger, id del vídeo elegido).
# Descartados al mirarlos: «Pull-ups» (475) es en máquina asistida, y «Bent-over
# Lateral Raises» (82) es sentado, cuando nuestras fotos y pasos son en banco inclinado.
VIDEOS: dict[str, tuple[int, int]] = {
    "barbell-bench-press-medium-grip": (73, 23),
    "dumbbell-bench-press": (75, 17),
    "barbell-curl": (91, 49),
    "dumbbell-bicep-curl": (92, 48),
    "standing-biceps-cable-curl": (95, 50),
    "dips-chest-version": (194, 64),
    "dumbbell-lunges": (205, 31),
    "face-pull": (222, 78),
    "lying-dumbbell-tricep-extension": (245, 60),
    "lying-triceps-press": (246, 61),
    "front-barbell-squat": (257, 27),
    "hammer-curls": (272, 51),
    "cable-hammer-curls-rope-attachment": (275, 47),
    "barbell-hip-thrust": (294, 72),
    "smith-machine-squat": (341, 42),
    "side-lateral-raise": (348, 6),
    "lying-leg-curls": (365, 35),
    "seated-leg-curl": (366, 37),
    "leg-press": (371, 44),
    "hack-squat": (375, 40),
    "stiff-legged-dumbbell-deadlift": (507, 2),  # el vídeo es con mancuernas
    "seated-cable-rows": (512, 1),
    "incline-dumbbell-press": (537, 24),
    "barbell-incline-bench-press-medium-grip": (538, 16),
    "machine-shoulder-military-press": (543, 11),
    "dumbbell-shoulder-press": (567, 12),
    "seated-calf-raise": (590, 13),
    "standing-calf-raises": (622, 14),
    "tricep-dumbbell-kickback": (655, 75),
    "triceps-pushdown": (659, 55),
    "barbell-lunge": (46, 30),
    "thigh-adductor": (12, 74),
}

# Segundos que se recortan al principio: el vídeo empieza colocando la cámara.
TRIM_START: dict[str, float] = {
    "barbell-bench-press-medium-grip": 2.5,
    "barbell-incline-bench-press-medium-grip": 2.5,
}

LICENSES = {
    1: ("CC-BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
    2: ("CC-BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    3: ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    4: ("CC-BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def build(downloads: Path) -> None:
    """Download, convert and credit every mapped video."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit("Hace falta ffmpeg en el PATH.")
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in [*OUT.glob("*.mp4"), *OUT.glob("*.jpg")]:
        if stale.stem not in VIDEOS:
            stale.unlink()
    downloads.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict[str, object]] = {}
    for slug, (exercise_id, video_id) in sorted(VIDEOS.items()):
        meta = json.loads(_get(API.format(id=video_id)))
        if meta["exercise"] != exercise_id:
            raise SystemExit(f"{slug}: el vídeo {video_id} no es del ejercicio {exercise_id}")
        source = downloads / Path(meta["video"]).name
        if not source.exists():
            print(f"descargando {slug} ({meta['size'] // 1_000_000} MB)", flush=True)
            source.write_bytes(_get(meta["video"]))
        target = OUT / f"{slug}.mp4"
        trim = str(TRIM_START.get(slug, 0))
        _ffmpeg(
            "-ss",
            trim,
            "-i",
            str(source),
            "-an",
            "-vf",
            "scale=640:360:force_original_aspect_ratio=decrease,"
            "pad=640:360:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "main",
            "-movflags",
            "+faststart",
            str(target),
        )
        _ffmpeg(
            "-ss", "1", "-i", str(target), "-frames:v", "1", "-q:v", "4", str(OUT / f"{slug}.jpg")
        )
        license_name, license_url = LICENSES[int(meta["license"])]
        credits[slug] = {
            "author": meta["license_author"] or "wger",
            "license": license_name,
            "license_url": license_url,
            "source": f"https://wger.de/exercise/{exercise_id}/view/",
            "changes": "Convertido a H.264 640x360 sin sonido.",
        }
        print(f"{slug}: {target.stat().st_size // 1000} KB", flush=True)
    (OUT / "CREDITS.json").write_text(
        json.dumps(credits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "instance" / "wger-videos")
