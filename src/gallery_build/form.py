"""Static local-only exhibition editor, included in deployed sites, not preview ZIPs."""

from .builder import ENV, FONT_FILES, ROOT


def form_files():
    files = {"new/index.html": ENV.get_template("form.html").render().encode()}
    for path in (ROOT / "form-assets").iterdir():
        if path.is_file():
            files["assets/" + path.name] = path.read_bytes()
    css = ""
    for filename, family, weights in FONT_FILES.values():
        for suffix, style in (("", "normal"), ("-Italic", "italic")):
            name = f"{filename}{suffix}.ttf"
            files["assets/form-fonts/" + name] = (
                ROOT / "assets/fonts" / name
            ).read_bytes()
            css += f"@font-face{{font-family:'{family}';src:url('form-fonts/{name}');font-weight:{weights};font-style:{style};font-display:swap}}\n"
    files["assets/form-fonts.css"] = css.encode()
    return files
