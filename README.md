# Victoire Taverne Céramiques

Site vitrine publié par Netlify à partir du dossier `site/`.

- **Textes, prix, pièces, collections** : modifiés dans Notion. GitHub relit Notion toutes les heures (`outil/build.py`, lancé par `.github/workflows/site.yml`) et republie le site s'il a changé. Pour forcer une mise à jour : onglet *Actions* → *Mise à jour du site depuis Notion* → *Run workflow*.
- **Photos** : dossiers « photos fiches produits » sur le Mac. Elles sont converties et ajoutées dans `site/photos/` (+ `outil/photos.json`) lors d'une « MAJ ».
- **Mise en page** : `outil/template.html`.
- La clé Notion est rangée dans *Settings → Secrets and variables → Actions* sous le nom `NOTION_TOKEN`.
