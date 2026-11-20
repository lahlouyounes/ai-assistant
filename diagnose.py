"""Diagnostic de connexion à Gemini : python diagnose.py   (n'affiche jamais la clé)."""
import os
import socket
import time

import httpx

from app.config import settings

HOST = "generativelanguage.googleapis.com"
print("Fournisseur :", settings.provider, "| modèle :", settings.gemini_model)
print("Clé GEMINI_API_KEY :", "présente" if settings.gemini_api_key else "ABSENTE (vérifiez .env)")
proxies = [k for k in os.environ if "PROXY" in k.upper()]
print("Variables proxy :", proxies or "aucune")

try:
    print("DNS :", sorted({i[4][0] for i in socket.getaddrinfo(HOST, 443)})[:4])
    t = time.time()
    socket.create_connection((HOST, 443), timeout=10).close()
    print(f"Connexion TCP 443 : OK ({time.time() - t:.1f}s)")
except Exception as exc:
    print("Connexion réseau : ÉCHEC ->", exc, "\n=> Pare-feu, VPN ou réseau bloquant Google.")
    raise SystemExit(1)

base, hdr = settings.gemini_base_url.rstrip("/"), {"Authorization": f"Bearer {settings.gemini_api_key}"}
for trust in (True, False):
    label = "avec proxy système" if trust else "sans proxy système"
    try:
        t = time.time()
        r = httpx.get(base + "/models", headers=hdr, timeout=30, trust_env=trust)
        names = [m.get("id", "") for m in r.json().get("data", [])] if r.status_code == 200 else []
        flash = [n.replace("models/", "") for n in names if "flash" in n][:8]
        print(f"Liste des modèles ({label}) : HTTP {r.status_code} en {time.time() - t:.1f}s", flash or r.text[:150])
    except Exception as exc:
        print(f"Liste des modèles ({label}) : ÉCHEC -> {type(exc).__name__}")

for effort in ("low", None):
    body = {"model": settings.gemini_model, "messages": [{"role": "user", "content": "dis bonjour"}]}
    if effort:
        body["reasoning_effort"] = effort
    try:
        t = time.time()
        r = httpx.post(base + "/chat/completions", headers=hdr, json=body, timeout=90)
        txt = r.json()["choices"][0]["message"].get("content", "")[:60] if r.status_code == 200 else r.text[:200]
        print(f"Chat (réflexion={effort}) : HTTP {r.status_code} en {time.time() - t:.1f}s -> {txt}")
    except Exception as exc:
        print(f"Chat (réflexion={effort}) : ÉCHEC -> {type(exc).__name__}")
