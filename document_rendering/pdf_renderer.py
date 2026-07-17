def render_pdf_bytes(html_text, base_url=None):
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise RuntimeError("PDF export requires weasyprint to be installed.") from exc
    try:
        return HTML(string=html_text, base_url=base_url).write_pdf()
    except Exception as exc:
        raise RuntimeError(
            "PDF export failed in WeasyPrint runtime. Verify server libraries for "
            "Pango, Cairo, and Fontconfig are installed."
        ) from exc
