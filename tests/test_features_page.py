"""The features page (web/features.html): the README's and docs' links reach its sections, and its demos and icons load."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "features.html"
URL = "https://wisemandenny.github.io/hxtra/web/features.html"


def page():
    return PAGE.read_text()


def ids():
    return set(re.findall(r'\bid="([^"]+)"', page()))


def test_links_to_the_page_reach_a_section():
    docs = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *(ROOT / "docs").glob("*.md")]
    broken = [f"{d.name}: #{a}" for d in docs for a in re.findall(re.escape(URL) + r"#([\w-]+)", d.read_text())
              if a not in ids()]
    assert not broken


def test_readme_watch_demo_badges_link_to_the_page():
    readme = (ROOT / "README.md").read_text()
    badges = re.findall(r'<a href="([^"]+)"><img src="docs/assets/icons/watch-demo.svg"', readme)
    assert len(badges) == readme.count("watch-demo.svg") > 0
    assert all(b.startswith(URL + "#") for b in badges)
    assert "<details>" not in readme


def test_page_files_exist():
    # Pages publishes docs/assets beside web/, so ../docs/assets resolves there as in a checkout.
    missing = [s for s in re.findall(r'src="([^":]+)"', page()) if not (PAGE.parent / s).resolve().exists()]
    assert not missing


def test_every_demo_slot_has_sized_media():
    # Sized media keep the layout still while the demos load, so an anchor lands on its section.
    slots = re.findall(r'<!-- demo: [^>]*-->\n\s*<div class="demos[^"]*">(.*?)</div>', page(), re.S)
    assert len(slots) == page().count("<!-- demo:") > 0
    for slot in slots:
        media = re.findall(r"<(?:img|video) [^>]*>", slot)
        assert media and all(re.search(r'width="\d+" height="\d+"', m) for m in media)


def test_every_feature_card_ends_with_its_settings():
    cards = re.findall(r'<section class="card feat" id="[\w-]+">(.*?)</section>', page(), re.S)
    assert cards
    for card in cards:
        settings = card.rfind('<div class="settings">')
        assert settings >= 0 and "<table>" not in card[:settings]
