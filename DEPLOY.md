# Mettre l'assistant en ligne

## Checklist avant ouverture au public
- [ ] `API_TOKEN` défini (sinon n'importe qui consomme votre clé Claude)
- [ ] `PUBLIC_MODE=true` (désactive l'envoi d'emails)
- [ ] `DAILY_MESSAGE_CAP` réglé selon votre budget
- [ ] `TRUST_PROXY=true` si derrière Render/Caddy, `false` sinon
- [ ] Base PostgreSQL Render connectée via `DATABASE_URL`
- [ ] Dépôt Git privé, `.env` jamais commité

## Option A : Render (le plus simple)
1. Poussez le dossier sur GitHub.
2. Render → New → Blueprint → choisissez le dépôt (`render.yaml` crée le service web gratuit et PostgreSQL gratuit).
3. Saisissez `GEMINI_API_KEY`. `DATABASE_URL` est relié automatiquement à PostgreSQL. `API_TOKEN` est généré : retrouvez-le dans Environment et donnez-le à vos utilisateurs.
4. Ouvrez l'URL fournie : l'interface demande le code d'accès.

### Limites de l'offre gratuite Render
- Le service web gratuit s'arrête après une période d'inactivité et redémarre au prochain accès. Son système de fichiers est éphémère : les données de l'application sont donc stockées dans PostgreSQL, pas sur le disque local.
- PostgreSQL gratuit est limité à **1 Go** et expire **30 jours après sa création** (avec 14 jours de grâce pour passer à une offre payante avant suppression). Il n'inclut pas de sauvegardes gérées. Exportez régulièrement les données et migrez/renouvelez la base avant expiration si vous souhaitez conserver les conversations.
- Le navigateur conserve aussi sa propre liste de conversations. La base Render conserve la mémoire liée aux sessions envoyées au serveur.
- Le service et la base doivent être dans la même région. Cette configuration choisit Frankfurt.

## Option B : Railway / Fly.io
Déployez le `Dockerfile` et ajoutez les variables du `.env.example`. Sans `DATABASE_URL`, l'application utilise SQLite localement. Sur une plateforme sans disque persistant, configurez PostgreSQL et `DATABASE_URL`.

## Option C : VPS avec HTTPS automatique
1. Pointez votre domaine vers le serveur, puis éditez le `Caddyfile`.
2. `cp .env.example .env`, renseignez-le (`PUBLIC_MODE=true`, `API_TOKEN=...`).
3. `docker compose up -d --build`

## Accès sans code d'accès (démo ouverte)
Laissez `API_TOKEN` vide uniquement si le plafond `DAILY_MESSAGE_CAP` est bas : c'est alors votre seule protection.

## Surveillance
`GET /health` pour les sondes de disponibilité. Surveillez votre quota dans Google AI Studio. Les quotas gratuits sont limités : le plafond `DAILY_MESSAGE_CAP` doit rester sous ces limites.
