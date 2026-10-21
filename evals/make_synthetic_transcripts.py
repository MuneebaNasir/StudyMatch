"""Generate the synthetic transcript eval cases (fictional student and university).

    python -m evals.make_synthetic_transcripts

Writes <id>.png + <id>.json (ground truth) for a clean render and a degraded,
scan-like copy of the same transcript. Content is fixed by RANDOM_SEED so the
ground truth is reproducible.
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .datasets import DATASETS_DIR

RANDOM_SEED = 20261021
GRADE_POINTS = {"A": 4.0, "A-": 3.67, "B+": 3.33, "B": 3.0, "B-": 2.67, "C+": 2.33, "C": 2.0, "D": 1.0}
COURSES = [
    ("CS1 01", "Introduction to Programming"), ("MT1 02", "Calculus I"), ("MT1 05", "Discrete Mathematics"),
    ("SS1 03", "Academic Writing"), ("CS1 10", "Object Oriented Programming"), ("MT1 12", "Linear Algebra"),
    ("CS2 01", "Data Structures"), ("EE2 04", "Digital Logic Design"), ("CS2 07", "Database Systems"),
    ("MT2 03", "Probability and Statistics"), ("CS2 11", "Computer Architecture"), ("CS3 02", "Operating Systems"),
    ("CS3 05", "Design and Analysis of Algorithms"), ("CS3 08", "Computer Networks"), ("CS3 12", "Software Engineering"),
    ("CS3 15", "Theory of Computation"), ("CS4 01", "Machine Learning"), ("CS4 04", "Information Security"),
    ("MG4 02", "Entrepreneurship"), ("CS4 09", "Final Year Project"),
]
SEMESTERS = ["Fall 2019", "Spring 2020", "Fall 2020", "Spring 2021"]


def build_truth() -> dict:
    rng = random.Random(RANDOM_SEED)
    courses = [{"code": code, "name": name, "grade": rng.choice(list(GRADE_POINTS))} for code, name in COURSES]
    gpa = round(sum(GRADE_POINTS[c["grade"]] for c in courses) / len(courses), 2)
    return {"courses": courses, "grade_value": gpa}


def render(truth: dict) -> Image.Image:
    width, row_h = 1240, 34
    image = Image.new("RGB", (width, 1754), "white")
    draw = ImageDraw.Draw(image)
    title, body, small = (ImageFont.load_default(size=s) for s in (40, 22, 18))
    draw.text((80, 60), "Northfield Institute of Technology", font=title, fill="navy")
    draw.text((80, 120), "Official Academic Transcript", font=body, fill="black")
    draw.text((80, 170), "Student: Alex Example        Programme: BS Computer Science", font=body, fill="black")
    y = 230
    per_semester = len(truth["courses"]) // len(SEMESTERS)
    for i, semester in enumerate(SEMESTERS):
        draw.text((80, y), semester, font=body, fill="black")
        y += row_h
        for x, header in ((80, "Code"), (200, "Course Name"), (640, "Grade")):
            draw.text((x, y), header, font=small, fill="gray")
        y += row_h
        for course in truth["courses"][i * per_semester:(i + 1) * per_semester]:
            draw.text((80, y), course["code"], font=small, fill="black")
            draw.text((200, y), course["name"], font=small, fill="black")
            draw.text((640, y), course["grade"], font=small, fill="black")
            y += row_h
        y += row_h // 2
    draw.text((80, y + 20), f"Cumulative GPA: {truth['grade_value']:.2f} / 4.00", font=body, fill="black")
    return image


def degrade(image: Image.Image) -> Image.Image:
    rng = random.Random(RANDOM_SEED)
    smaller = image.resize((image.width * 3 // 5, image.height * 3 // 5)).rotate(0.8, expand=True, fillcolor="white")
    noisy = smaller.copy()
    pixels = noisy.load()
    for _ in range(noisy.width * noisy.height // 60):
        x, y = rng.randrange(noisy.width), rng.randrange(noisy.height)
        shade = rng.randrange(150, 230)
        pixels[x, y] = (shade, shade, shade)
    return noisy.filter(ImageFilter.GaussianBlur(0.6))


def write_cases(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    truth = build_truth()
    clean = render(truth)
    stored = {"courses": [{"name": c["name"], "grade": c["grade"]} for c in truth["courses"]], "grade_value": truth["grade_value"]}
    for case_id, image in (("synthetic_clean", clean), ("synthetic_scan", degrade(clean))):
        image.save(out_dir / f"{case_id}.png")
        (out_dir / f"{case_id}.json").write_text(json.dumps(stored, indent=2) + "\n")


if __name__ == "__main__":
    write_cases(Path(sys.argv[1]) if len(sys.argv) > 1 else DATASETS_DIR / "transcripts")
