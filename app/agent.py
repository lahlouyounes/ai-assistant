"""Boucle agent : comprendre → outil → vérifier → répondre. Fournisseurs : Gemini (défaut) ou Claude."""
import json
import os
import time

import httpx

from . import memory
from .config import settings
from .prompts import build_system_prompt
from .tools import SENSITIVE, active_tools, run_tool

NO_TEXT = "(pas de réponse textuelle)"
TOO_MANY = "Je n'ai pas pu terminer : trop d'étapes d'outils. Pouvez-vous préciser la demande ?"


def _execute(session_id: str, name: str, args: dict, pending: list) -> str:
    if name in SENSITIVE:
        pid = memory.add_pending(session_id, name, args)
        pending.append({"id": pid, "tool": name, "args": args})
        return (f"Action '{name}' NON exécutée : en attente de confirmation de l'utilisateur (id={pid}). "
                "Présente-lui le contenu exact et dis-lui de confirmer dans l'interface.")
    return run_tool(name, args)


# ---------------- Gemini (API compatible OpenAI) ----------------
def _openai_tools() -> list:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in active_tools()]


def _gemini_models() -> list:
    fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-lite-latest,gemini-flash-latest")
    out = []
    for m in [settings.gemini_model] + [x.strip() for x in fallbacks.split(",")]:
        if m and m not in out:
            out.append(m)
    return out


def _openai_call(messages: list) -> dict:
    """Appelle Gemini ; si le modèle est lent/surchargé (503, 429, délai, 404), passe au modèle de secours suivant."""
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY manquante : ajoutez-la dans le fichier .env puis redémarrez le serveur.")
    effort = os.getenv("GEMINI_REASONING", "low").strip()  # "" pour laisser le modèle choisir
    timeout = float(os.getenv("GEMINI_TIMEOUT", "30"))
    url = f"{settings.gemini_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.gemini_api_key}"}
    fatal = {400: "requête refusée (paramètre invalide ?)", 401: "clé API invalide",
             403: "clé refusée ou région non prise en charge"}
    errors: list = []
    for round_no in range(2):
        transient_only = True
        for model in _gemini_models():
            payload = {"model": model, "messages": messages, "tools": _openai_tools(), "tool_choice": "auto"}
            if effort:
                payload["reasoning_effort"] = effort
            for _ in range(2):  # 2e essai seulement si le réglage de réflexion est refusé
                try:
                    r = httpx.post(url, headers=headers, json=payload, timeout=httpx.Timeout(timeout, connect=10))
                except httpx.TimeoutException:
                    errors.append(f"{model}: délai dépassé")
                    r = None
                    break
                except httpx.HTTPError as exc:
                    raise RuntimeError(f"Connexion à Gemini impossible : {exc}")
                error_text = r.text.lower()
                rejects_reasoning = any(term in error_text for term in
                                        ("reasoning_effort", "reasoning effort", "thinking level", "thinking_level"))
                if r.status_code == 400 and "reasoning_effort" in payload and rejects_reasoning:
                    payload.pop("reasoning_effort")
                    continue
                break
            if r is None:
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in fatal:
                raise RuntimeError(f"Gemini a répondu {r.status_code} — {fatal[r.status_code]} : {r.text[:300]}")
            if r.status_code not in (404, 429, 500, 503):
                transient_only = False
            errors.append(f"{model}: HTTP {r.status_code}")
        if not transient_only or round_no == 1:
            break
        time.sleep(3)
    raise RuntimeError("Gemini indisponible ou trop lent sur tous les modèles essayés (" + "; ".join(errors[-6:])
                       + "). Réessayez dans un instant, ou lancez : python diagnose.py")


def _chat_gemini(session_id: str, message: str, pending: list, document_context: str = "") -> str:
    msgs = [{"role": "system", "content": build_system_prompt(document_context)}] + memory.load_history(session_id) \
        + [{"role": "user", "content": message}]
    msg: dict = {}
    for _ in range(settings.max_tool_rounds):
        msg = _openai_call(msgs)["choices"][0]["message"]
        msgs.append(msg)  # renvoyé tel quel (signatures de réflexion de Gemini 3)
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or ""
        for c in calls:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out = _execute(session_id, c["function"]["name"], args, pending)
            msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["function"]["name"], "content": out})
    return (msg.get("content") or "") or TOO_MANY


# ---------------- Claude (Anthropic) ----------------
def _chat_anthropic(session_id: str, message: str, pending: list, client=None, document_context: str = "") -> str:
    import anthropic
    client = client or anthropic.Anthropic()
    msgs = memory.load_history(session_id) + [{"role": "user", "content": message}]
    resp = None
    for _ in range(settings.max_tool_rounds):
        resp = client.messages.create(model=settings.model, max_tokens=2000,
                                      system=build_system_prompt(document_context), tools=active_tools(), messages=msgs)
        msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = [{"type": "tool_result", "tool_use_id": b.id,
                    "content": _execute(session_id, b.name, b.input, pending)}
                   for b in resp.content if b.type == "tool_use"]
        msgs.append({"role": "user", "content": results})
    text = "".join(b.text for b in resp.content if b.type == "text") if resp else ""
    if resp is not None and resp.stop_reason == "tool_use":
        text = text or TOO_MANY
    return text


# ---------------- Points d'entrée ----------------
def chat(session_id: str, message: str, client=None, document_context: str = "") -> dict:
    pending: list = []
    if client is not None or settings.provider == "anthropic":
        text = _chat_anthropic(session_id, message, pending, client, document_context)
    else:
        text = _chat_gemini(session_id, message, pending, document_context)
    memory.save_message(session_id, "user", message)
    memory.save_message(session_id, "assistant", text or NO_TEXT)
    return {"reply": text, "pending_actions": pending}


def confirm(session_id: str, pending_id: str, approve: bool) -> str:
    p = memory.get_pending(pending_id, session_id)
    if not p or p["status"] != "pending":
        return "Action introuvable ou déjà traitée."
    if not approve:
        memory.set_pending_status(pending_id, "rejected")
        result = "Action annulée par l'utilisateur."
    else:
        memory.set_pending_status(pending_id, "approved")
        result = run_tool(p["tool"], json.loads(p["args"]))
    memory.save_message(session_id, "user", f"[Système] Action {p['tool']} {'confirmée' if approve else 'refusée'}.")
    memory.save_message(session_id, "assistant", result)
    return result
