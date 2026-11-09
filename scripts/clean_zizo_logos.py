"""One-off: remove YouTube/TikTok brand logos from Zizo's approved image (owner asked for a plain hoodie).
Input: assets/characters/source/zizo_trend_half_original_with_logos.png → assets/characters/approved/zizo_trend_half.png"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SRC = "assets/characters/source/zizo_trend_half_original_with_logos.png"
DST = "assets/characters/approved/zizo_trend_half.png"

im = Image.open(SRC).convert("RGB")
# hoodie patch: clone plain fabric from just below the logo
box = (657, 814, 752, 918)
h = box[3] - box[1]
patch = im.crop((box[0], box[3] + 4, box[2], box[3] + 4 + h))
m = Image.new("L", patch.size, 0)
ImageDraw.Draw(m).rectangle([4, 4, patch.width - 4, patch.height - 4], fill=255)
im.paste(patch, box[:2], m.filter(ImageFilter.GaussianBlur(2)))

# phone: pass 1 — anything that is not the case colour and not skin inside the logo boxes
a = np.array(im)
hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV)
x0, y0, x1, y1 = 845, 640, 955, 800
reg = a[y0:y1, x0:x1].astype(int)
r, g, b = reg[..., 0], reg[..., 1], reg[..., 2]
sat = hsv[y0:y1, x0:x1, 1].astype(int)
case = a[705, 828].astype(int)
dist = np.abs(reg - case).sum(-1)
skin = (sat > 45) & (sat < 150) & (r - b > 35) & (r > g) & (g > b)
ys, xs = np.mgrid[y0:y1, x0:x1]
inside = ((xs >= 853) & (xs <= 948) & (ys <= 737)) | ((xs >= 828) & (xs <= 890) & (ys >= 744) & (ys <= 797))
mask = np.zeros(a.shape[:2], np.uint8)
mask[y0:y1, x0:x1] = ((dist > 45) & ~skin & inside).astype(np.uint8) * 255
a = cv2.inpaint(a, cv2.dilate(mask, np.ones((7, 7), np.uint8)), 9, cv2.INPAINT_TELEA)

# pass 2 — leftover red/white of the small YouTube badge
x0, y0, x1, y1 = 815, 735, 900, 805
reg = a[y0:y1, x0:x1].astype(int)
r, g, b = reg[..., 0], reg[..., 1], reg[..., 2]
mask = np.zeros(a.shape[:2], np.uint8)
mask[y0:y1, x0:x1] = (((r > 110) & (r - g > 60) & (r - b > 50)) | ((r > 170) & (g > 170) & (b > 170))).astype(np.uint8) * 255
a = cv2.inpaint(a, cv2.dilate(mask, np.ones((7, 7), np.uint8)), 9, cv2.INPAINT_TELEA)
Image.fromarray(a).save(DST)
