# AI Assistant — agent IA polyvalent (FR / EN / AR)

Agent propulsé par **Google Gemini** (offre gratuite) ou **Claude**, avec outils, mémoire par session, interface web et API REST.
Le fournisseur se choisit dans `.env` (`LLM_PROVIDER=gemini` ou `anthropic`).

## Fonctionnalités
| Besoin | Implémentation |
|---|---|
| Calculs | `calculator` — évaluation AST sécurisée (pas de `eval`) |
| Recherche web | `web_search` (DuckDuckGo via `ddgs`) |
| API REST | `http_request` — GET/POST, **protection SSRF** (IP privées bloquées), liste d'hôtes autorisés optionnelle |
| Base de données | SQLite en local ou PostgreSQL avec `DATABASE_URL` : `db_query` (SELECT en lecture seule), `db_save_note`, `db_delete_note` |
| Email | `send_email` via SMTP |
| Mémoire | SQLite en local ou PostgreSQL sur Render, isolée par `session_id` (`app/memory.py`) |
| Historique web | Conversations conservées dans le navigateur, avec recherche, reprise et suppression |
| Documents PDF | Import de PDF textuels (15 Mo, 100 pages max) et questions dans la conversation |
| Sécurité | Actions sensibles (`send_email`, `db_delete_note`) **jamais exécutées sans confirmation humaine** ; contenu des outils traité comme donnée ; secrets jamais exposés ; token d'API optionnel |

## Démarrage rapide
```bash
python -m venv .venv && source .venv/bin/activate    # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # puis renseignez GEMINI_API_KEY (clé gratuite : aistudio.google.com/apikey)
uvicorn app.main:app --reload
```
Ouvrez http://localhost:8000. Avec Docker : `docker compose up --build`.

### Développer l’interface React
Lancez `npm ci` puis `npm run dev`. Dans un second terminal, démarrez FastAPI sur le port 8000. Vite transmet les requêtes API à FastAPI. Pour régénérer les fichiers React servis par FastAPI, lancez `npm run build`.
L’export PDF ouvre la boîte d’impression du navigateur : choisissez « Enregistrer au format PDF ». Les PDF scannés sont lus par OCR (français, anglais et arabe) ; limitez chaque import à 30 pages scannées.

## API
```bash
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"demo-1","message":"Combien font 15% de 2340 ?"}'
# -> {"reply":"...", "pending_actions":[]}
```
- `POST /chat` : `{session_id, message}` → `{reply, pending_actions}`
- `POST /actions/{id}` : `{session_id, approve}` → confirme ou refuse une action sensible
- `DELETE /sessions/{session_id}` : efface l'historique
- `GET /health`

Si `API_TOKEN` est défini, ajoutez `-H "Authorization: Bearer <token>"`.

## Mise en ligne publique
Voir **DEPLOY.md** (Render, Railway, VPS + HTTPS). En bref : définissez `API_TOKEN`, `PUBLIC_MODE=true` et `DAILY_MESSAGE_CAP`.
L'interface demande le code d'accès ; l'API applique une limite par IP/minute et un plafond quotidien (429 au-delà).
Le Blueprint Render fourni utilise les services gratuits et PostgreSQL (1 Go, expiration après 30 jours). Consultez `DEPLOY.md` pour les limites et la conservation des données.

## Tests
```bash
pytest -q
```
Les tests n'appellent aucune API (réponses simulées).

## Structure
```
app/prompts.py   prompt système       app/tools.py    outils + schémas
app/agent.py     boucle agent         app/memory.py   mémoire + actions en attente
app/main.py      API FastAPI          src/            interface React
```

## Personnaliser
- Ajouter un outil : fonction dans `tools.py`, entrée dans `FUNCTIONS` et `TOOLS` (et dans `SENSITIVE` s'il exige confirmation).
- Changer le comportement : éditez `app/prompts.py`.
- Changer de modèle : `ANTHROPIC_MODEL` dans `.env`.

## Limites connues
Le code d'accès est partagé (pas de comptes individuels) et la limite de débit est en mémoire (une seule instance). Il n'y a pas de comptes utilisateurs : l'isolation repose sur le `session_id` (à rendre non devinable côté client) et sur `API_TOKEN`. La liste de conversations est enregistrée dans le navigateur courant ; elle n'est pas synchronisée entre appareils. L'import PDF lit les fichiers comportant une couche texte (pas d'OCR). Pour la production, placez le service derrière HTTPS et une vraie authentification.
