#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

from docx import Document


REQUIRED_DOCX_PARTS = {
    "[Content_Types].xml",
    "word/document.xml",
    "word/styles.xml",
}


def main():
    parser = argparse.ArgumentParser(
        description="Compare Phase 6 PDF visuals and DOCX structure."
    )
    parser.add_argument("baseline_pdf", type=Path)
    parser.add_argument("candidate_pdf", type=Path)
    parser.add_argument("baseline_docx", type=Path)
    parser.add_argument("candidate_docx", type=Path)
    parser.add_argument("--max-different-pixels", type=int, default=0)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="ordinarium-document-compare-") as tmp:
        different_pixels = compare_pdf_visuals(
            args.baseline_pdf,
            args.candidate_pdf,
            Path(tmp),
        )
    if different_pixels > args.max_different_pixels:
        raise AssertionError(
            f"PDF visual difference was {different_pixels} pixels; "
            f"limit is {args.max_different_pixels}."
        )

    baseline_structure = docx_structure(args.baseline_docx)
    candidate_structure = docx_structure(args.candidate_docx)
    if baseline_structure != candidate_structure:
        raise AssertionError("DOCX paragraph/run structure differs from the baseline.")

    print(
        json.dumps(
            {
                "docx_paragraphs": len(candidate_structure),
                "pdf_different_pixels": different_pixels,
                "status": "matched",
            },
            sort_keys=True,
        )
    )


def compare_pdf_visuals(baseline_path, candidate_path, output_directory):
    pdftoppm = required_command("pdftoppm")
    compare = required_command("compare")
    baseline_prefix = output_directory / "baseline"
    candidate_prefix = output_directory / "candidate"
    render_pdf(pdftoppm, baseline_path, baseline_prefix)
    render_pdf(pdftoppm, candidate_path, candidate_prefix)

    baseline_pages = sorted(output_directory.glob("baseline-*.png"))
    candidate_pages = sorted(output_directory.glob("candidate-*.png"))
    if not baseline_pages or len(baseline_pages) != len(candidate_pages):
        raise AssertionError(
            "PDF page count differs or no pages could be rendered: "
            f"baseline={len(baseline_pages)} candidate={len(candidate_pages)}"
        )

    total_difference = 0
    for page_number, (baseline_page, candidate_page) in enumerate(
        zip(baseline_pages, candidate_pages, strict=True), start=1
    ):
        difference_path = output_directory / f"difference-{page_number}.png"
        result = subprocess.run(
            [
                compare,
                "-metric",
                "AE",
                str(baseline_page),
                str(candidate_page),
                str(difference_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or "Image comparison failed.")
        metric = (result.stderr or result.stdout).strip()
        metric_match = re.match(r"[-+]?\d+(?:\.\d+)?", metric)
        if not metric_match:
            raise RuntimeError(f"Unable to parse ImageMagick metric: {metric!r}")
        total_difference += int(float(metric_match.group(0)))
    return total_difference


def render_pdf(pdftoppm, source, destination_prefix):
    subprocess.run(
        [pdftoppm, "-png", "-r", "144", str(source), str(destination_prefix)],
        check=True,
        capture_output=True,
        text=True,
    )


def docx_structure(path):
    with ZipFile(path) as archive:
        missing = REQUIRED_DOCX_PARTS - set(archive.namelist())
        if missing:
            raise AssertionError(f"DOCX is missing required parts: {sorted(missing)}")

    document = Document(path)
    return [
        {
            "alignment": int(paragraph.alignment) if paragraph.alignment else None,
            "runs": [
                {
                    "bold": run.bold,
                    "italic": run.italic,
                    "text": run.text,
                }
                for run in paragraph.runs
            ],
            "style": paragraph.style.name if paragraph.style else None,
            "text": paragraph.text,
        }
        for paragraph in document.paragraphs
    ]


def required_command(name):
    command = shutil.which(name)
    if not command:
        raise RuntimeError(f"Required command is unavailable: {name}")
    return command


if __name__ == "__main__":
    main()
