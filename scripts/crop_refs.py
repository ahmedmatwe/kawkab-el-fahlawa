"""Cut approved per-character reference crops out of the two official posters.
Boxes are (left, top, right, bottom) in the 1536x1024 posters. Re-run only when
the approved posters change; output = assets/characters/refs/<id>_<poster>.png"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BOXES = {
    # poster_a = character cards poster (name plaques start at y≈650)
    "poster_a": {
        "abdo_ekhtera": (0, 140, 320, 650),
        "om_abdo": (290, 190, 610, 650),
        "sayed_fahlawa": (570, 245, 1000, 650),
        "zizo_trend": (930, 160, 1220, 650),
        "am_ragab": (1215, 180, 1536, 650),
    },
    # poster_b = group scene poster (name plaques start at y≈800)
    "poster_b": {
        "abdo_ekhtera": (0, 200, 330, 790),
        "om_abdo": (290, 220, 620, 790),
        "sayed_fahlawa": (600, 290, 1090, 790),
        "zizo_trend": (920, 170, 1230, 680),
        "am_ragab": (1190, 190, 1536, 790),
    },
}

def main():
    out = ROOT / "assets/characters/refs"
    out.mkdir(parents=True, exist_ok=True)
    for poster, boxes in BOXES.items():
        im = Image.open(ROOT / f"assets/characters/source/{poster}.png").convert("RGB")
        for cid, box in boxes.items():
            im.crop(box).save(out / f"{cid}_{poster}.png")

if __name__ == "__main__":
    main()
