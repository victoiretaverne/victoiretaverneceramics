# Importe les photos des dossiers « photos fiches produits » vers photos/ + manifeste photos.json
import os, re, json, unicodedata, hashlib
from PIL import Image, ImageOps
ROOT = "/mnt/user-data/uploads/Documents/WORK/4. CÉRAMIQUE/photos fiches produits"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "photos")
os.makedirs(OUT, exist_ok=True)
def slug(s):
    s = s.replace('œ', 'oe').replace('Œ', 'OE')
    s = unicodedata.normalize('NFC', s)
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')
COLL = {"terre-melees": "terre-melees", "les-pois": "pois", "graphics": "graphics", "les-carreaux": "carreaux"}
CAT = {"art-de-la-table": "table", "vases": "vases", "petits-objets": "objets"}
man = {"pieces": {}, "collections": {}, "categories": {}, "cover": None}
def conv(src, name, w=1600):
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB')
    if max(im.size) > w:
        r = w / max(im.size); im = im.resize((round(im.width*r), round(im.height*r)), Image.LANCZOS)
    dst = os.path.join(OUT, name); im.save(dst, 'JPEG', quality=80, optimize=True, progressive=True)
    return "photos/" + name
IMG = re.compile(r'\.(jpe?g|png|heic|webp)$', re.I)
for dirpath, dirs, files in os.walk(ROOT):
    files = sorted(f for f in files if IMG.search(f))
    if not files: continue
    rel = os.path.relpath(dirpath, ROOT); parts = [unicodedata.normalize('NFC', x) for x in rel.split(os.sep)]
    if parts[0] == "00 - Cover du site":
        man["cover"] = conv(os.path.join(dirpath, files[0]), "bandeau.jpg", 2400).replace("photos/", ""); continue
    if parts[0] == "00 - Covers collections" and len(parts) > 1:
        key = COLL.get(re.sub(r"^(collection-)?n-?\d+-", "", slug(parts[1])))
        bucket, prefix = man["collections"], "coll-"
    elif parts[0] == "00 - Covers catégories" and len(parts) > 1:
        key = CAT.get(slug(parts[1])); bucket, prefix = man["categories"], "cat-"
    else:
        # pièces rangées par type : « 0X - Type/Nom de la pièce »
        if not (re.match(r'^\d+ - ', parts[0]) and len(parts) > 1): continue  # anciens dossiers à la racine ignorés
        piece = parts[1]
        key = slug(piece); bucket, prefix = man["pieces"], ""
    if not key: print("ignoré :", rel); continue
    lst = bucket.setdefault(key, [])
    for i, f in enumerate(files):
        try: lst.append(conv(os.path.join(dirpath, f), f"{prefix}{key}-{len(lst)+1}.jpg"))
        except Exception as e: print("échec", rel, f, e)
json.dump(man, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(man, ensure_ascii=False, indent=1))
