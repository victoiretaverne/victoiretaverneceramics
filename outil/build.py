#!/usr/bin/env python3
"""
Construit site/index.html à partir de Notion.

- Lit la base « Pièces », la base « Collections », la base « Couleurs » et la page « Textes du site ».
- Injecte ces données dans outil/template.html (mise en page du site).
- Injecte la liste des photos (outil/photos.json, mise à jour à chaque « MAJ » photos).
- Coche / décoche la case « Photo manquante » de chaque pièce dans Notion.

Sans la variable d'environnement NOTION_TOKEN, le site est reconstruit tel quel
(données déjà présentes dans le gabarit).
Bibliothèque standard uniquement : rien à installer.
"""
import json, os, re, sys, unicodedata, urllib.request, urllib.error

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
TEMPLATE = os.path.join(ICI, "template.html")
PHOTOS_JSON = os.path.join(ICI, "photos.json")
SORTIE = os.path.join(RACINE, "site", "index.html")

DS_PIECES = "13c40088-7a5d-44b0-89c4-220c341d7849"
DS_COLLECTIONS = "f01af7fc-c98d-488c-bf6b-b3021c5cd7ba"
DS_COULEURS = "11998360-3be7-4cee-991e-5c975c80a625"
PAGE_TEXTES = "3f7943906724811ca36ad0c7d3561e2b"
NOTION_VERSION = "2025-09-03"

# Identifiants des collections déjà en place sur le site (id de page Notion -> id du site)
COLL_IDS = {
    "3f794390672480158447f52dd1198606": "pois",
    "3f7943906724808dac34ea4969459c1d": "graphics",
    "3f794390672480f6999eef738964afef": "terre-melees",
    "3f894390672480be94e3cf230453aaff": "carreaux",
}

TOKEN = os.environ.get("NOTION_TOKEN", "").strip()


def slug(s):
    s = s.replace("œ", "oe").replace("Œ", "OE")
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


MOTS_IGNORES = {"vase", "vases"}


def cle_souple(s):
    """« vase-ikebana-mini » ~ « ikebana-mini », « bol-v-uni » ~ « bol-v-unie »."""
    return "-".join(t[:-1] if len(t) > 2 and t.endswith("e") else t
                    for t in s.split("-") if t not in MOTS_IGNORES)


def photos_de(photos, sid):
    """Photos d'une pièce : nom exact du dossier, sinon nom approchant (pièce renommée dans Notion)."""
    if photos["pieces"].get(sid):
        return sid
    souple = cle_souple(sid)
    for k in photos["pieces"]:
        if cle_souple(k) == souple:
            return k
    return None


def api(method, chemin, corps=None):
    req = urllib.request.Request(
        "https://api.notion.com/v1/" + chemin,
        method=method,
        data=json.dumps(corps).encode() if corps is not None else None,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Erreur Notion {e.code} sur {chemin} : {e.read().decode()[:500]}")


def toutes_les_lignes(ds):
    lignes, curseur = [], None
    while True:
        corps = {"page_size": 100}
        if curseur:
            corps["start_cursor"] = curseur
        r = api("POST", f"data_sources/{ds}/query", corps)
        lignes += r["results"]
        if not r.get("has_more"):
            return lignes
        curseur = r["next_cursor"]


def texte_riche(rt):
    """Texte riche Notion -> texte du site (*italique* conservé)."""
    out = ""
    for t in rt or []:
        s = t.get("plain_text", "")
        if t.get("annotations", {}).get("italic") and s.strip():
            s = f"*{s}*"
        out += s
    return out


def prop(p, nom):
    v = p["properties"].get(nom)
    if not v:
        return None
    t = v["type"]
    if t == "title":
        return texte_riche(v["title"]).strip()
    if t == "rich_text":
        return texte_riche(v["rich_text"]).strip()
    if t == "checkbox":
        return v["checkbox"]
    if t == "number":
        return v["number"]
    if t == "select":
        return v["select"]["name"] if v["select"] else None
    if t == "multi_select":
        return [o["name"] for o in v["multi_select"]]
    if t == "relation":
        return [r["id"].replace("-", "") for r in v["relation"]]
    return None


def remplacer_bloc(html, debut, fin, nouveau):
    a = html.index(debut)
    b = html.index(fin, a)
    return html[:a] + nouveau + html[b:]


def js(v):
    return json.dumps(v, ensure_ascii=False)


def construire():
    html = open(TEMPLATE, encoding="utf-8").read()
    photos = json.load(open(PHOTOS_JSON, encoding="utf-8"))

    if TOKEN:
        # ---------- Collections ----------
        cols = []
        id_site = {}
        for c in toutes_les_lignes(DS_COLLECTIONS):
            pid = c["id"].replace("-", "")
            nom = prop(c, "Nom") or ""
            cid = COLL_IDS.get(pid) or slug(re.sub(r"^(collection\s*)?n°\s*\d+\s*:\s*", "", nom, flags=re.I)) or pid
            id_site[pid] = cid
            cols.append({
                "id": cid, "nom": nom, "ordre": prop(c, "Ordre"),
                "publie": bool(prop(c, "Publié")),
                "intro": prop(c, "Introduction") or "",
                "pieces": prop(c, "Pièces") or [],
            })
        coll_de_piece = {}
        for c in cols:
            for pid in c["pieces"]:
                coll_de_piece.setdefault(pid, []).append(c["id"])
        bloc = "const NOTION_COLLECTIONS = [\n" + ",\n".join(
            "  {id:%s, nom:%s, ordre:%s, publie:%s, intro:%s}" % (
                js(c["id"]), js(c["nom"]), js(c["ordre"]), "true" if c["publie"] else "false", js(c["intro"]))
            for c in cols if c["publie"])
        html = remplacer_bloc(html, "const NOTION_COLLECTIONS = [", "\n];", bloc)

        # ---------- Couleurs ----------
        couleurs, id_coul = [], {}
        for c in toutes_les_lignes(DS_COULEURS):
            nom = prop(c, "Nom") or ""
            c1 = (prop(c, "Code 1") or "").strip()
            if not nom or not re.fullmatch(r"#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", c1):
                continue
            c2 = (prop(c, "Code 2") or "").strip()
            if not re.fullmatch(r"#?[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", c2):
                c2 = ""
            hexa = lambda s: ("#" + s.lstrip("#")).upper() if s else ""
            cid = slug(nom)
            id_coul[c["id"].replace("-", "")] = cid
            couleurs.append({"id": cid, "nom": nom, "c1": hexa(c1), "c2": hexa(c2), "ordre": prop(c, "Ordre")})
        couleurs.sort(key=lambda d: (d["ordre"] is None, d["ordre"] or 0, d["nom"]))
        bloc = "const NOTION_COULEURS = [\n" + ",\n".join(
            "  " + js({k: d[k] for k in ("id", "nom", "c1", "c2")}) for d in couleurs)
        if "const NOTION_COULEURS = [" in html:  # gabarit sans pastilles : on ignore
            html = remplacer_bloc(html, "const NOTION_COULEURS = [", "\n];", bloc)

        # ---------- Pièces ----------
        pieces, maj_photos = [], []
        for p in toutes_les_lignes(DS_PIECES):
            pid = p["id"].replace("-", "")
            nom = prop(p, "Nom") or ""
            sid = slug(nom)
            k = photos_de(photos, sid)
            if k and k != sid:
                photos["pieces"][sid] = photos["pieces"][k]
            a_photo = bool(k)
            if "Photo manquante" in p["properties"] and bool(prop(p, "Photo manquante")) == a_photo:
                maj_photos.append((p["id"], not a_photo))
            if not prop(p, "Publié"):
                continue
            d = {"id": sid, "nom": nom, "cats": prop(p, "Catégories") or [],
                 "colls": coll_de_piece.get(pid, []),
                 "coul": [id_coul[c] for c in (prop(p, "Couleurs") or []) if c in id_coul],
                 "desc": prop(p, "Description") or "", "formats": prop(p, "Formats") or ""}
            for cle, nomp in (("sous", "Sous-catégorie"), ("compo", "Composition"), ("ordre", "Ordre"), ("delai", "Délai")):
                v = prop(p, nomp)
                if v not in (None, ""):
                    d[cle] = v
            pieces.append(d)
        pieces.sort(key=lambda d: (d.get("ordre") is None, d.get("ordre") or 0, d["nom"]))
        bloc = "const NOTION_PIECES = [\n" + ",\n".join("  " + js(d) for d in pieces)
        html = remplacer_bloc(html, "const NOTION_PIECES = [", "\n];", bloc)

        # ---------- Textes du site ----------
        blocs, curseur = [], None
        while True:
            r = api("GET", f"blocks/{PAGE_TEXTES}/children?page_size=100" + (f"&start_cursor={curseur}" if curseur else ""))
            blocs += r["results"]
            if not r.get("has_more"):
                break
            curseur = r["next_cursor"]
        textes, titre = {}, None
        for b in blocs:
            t = b["type"]
            if t in ("heading_1", "heading_2", "heading_3"):
                titre = texte_riche(b[t]["rich_text"]).strip()
                textes[titre] = []
            elif titre and t == "paragraph":
                s = texte_riche(b[t]["rich_text"]).strip()
                if s:
                    textes[titre].append(s)
        T = {k: "\n\n".join(v) for k, v in textes.items()}
        champs = {"Accroche": "accroche", "Présentation": "intro", "Commander": "commande", "Délais": "delais",
                  "Livraison": "livraison", "Personnalisation": "personnalisation", "Compte Instagram": "instagram"}
        for titre, cle in champs.items():
            if T.get(titre):
                val = T[titre].lstrip("@") if cle == "instagram" else T[titre]
                html = re.sub(r'(\n  %s: )"(?:[^"\\\n]|\\.)*"(,?\n)' % cle, lambda m: m.group(1) + js(val) + m.group(2), html, count=1)
        for titre, cid in (("Présentation Art de la table", "table"), ("Présentation Vases", "vases"), ("Présentation Petits objets", "objets")):
            if titre in T:
                html = re.sub(r'(\{id:"%s", nom:"[^"]*", texte:)"(?:[^"\\\n]|\\.)*"' % cid, lambda m: m.group(1) + js(T[titre].strip()), html, count=1)

        # ---------- Case « Photo manquante » ----------
        for page_id, manquante in maj_photos:
            api("PATCH", f"pages/{page_id}", {"properties": {"Photo manquante": {"checkbox": manquante}}})
        print(f"Notion : {len(pieces)} pièces publiées, {len(cols)} collections, {len(maj_photos)} cases photo mises à jour.")
    else:
        print("NOTION_TOKEN absent : reconstruction sans relire Notion.")

    # ---------- Photos ----------
    bloc = "const PHOTOS = " + js({k: photos[k] for k in ("pieces", "collections", "categories")}) + ";"
    html = re.sub(r"const PHOTOS = .*?;\n", lambda m: bloc + "\n", html, count=1, flags=re.S)

    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    ancien = open(SORTIE, encoding="utf-8").read() if os.path.exists(SORTIE) else ""
    if html != ancien:
        open(SORTIE, "w", encoding="utf-8").write(html)
        print("site/index.html mis à jour.")
    else:
        print("Aucun changement.")


if __name__ == "__main__":
    construire()
