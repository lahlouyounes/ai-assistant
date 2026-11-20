# Mettre l'assistant en ligne

## Checklist avant ouverture au public
- [ ] `API_TOKEN` défini (sinon n'importe qui consomme votre clé Claude)
- [ ] `PUBLIC_MODE=true` (désactive l'envoi d'emails)
- [ ] `DAILY_MESSAGE_CAP` réglé selon votre budget
- [ ] `TRUST_PROXY=true` si derrière Render/Caddy, `false` sinon
- [ ] Volume persistant monté sur `/srv/data`
- [ ] Dépôt Git privé, `.env` jamais commité

## Option A : Render (le plus simple)
1. Poussez le dossier sur un dépôt GitHub privé.
2. Render → New → Blueprint → choisissez le dépôt (`render.yaml` est lu automatiquement).
3. Saisissez `GEMINI_API_KEY`. `API_TOKEN` est généré : retrouvez-le dans l'onglet Environment et donnez-le à vos utilisateurs.
4. Ouvrez l'URL fournie : l'interface demande le code d'accès.

## Option B : Railway / Fly.io
Déployez le `Dockerfile`, ajoutez les variables du `.env.example` et un volume sur `/srv/data`. Le port est lu via `$PORT`.

## Option C : VPS avec HTTPS automatique
1. Pointez votre domaine vers le serveur, puis éditez le `Caddyfile`.
2. `cp .env.example .env`, renseignez-le (`PUBLIC_MODE=true`, `API_TOKEN=...`).
3. `docker compose up -d --build`

## Accès sans code d'accès (démo ouverte)
Laissez `API_TOKEN` vide uniquement si le plafond `DAILY_MESSAGE_CAP` est bas : c'est alors votre seule protection.

## Surveillance
`GET /health` pour les sondes de disponibilité. Surveillez votre quota dans Google AI Studio. Les quotas gratuits sont limités : le plafond `DAILY_MESSAGE_CAP` doit rester sous ces limites.
