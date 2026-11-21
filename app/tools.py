"""Outils de l'agent. Chaque outil renvoie du texte ; les erreurs sont renvoyées proprement, jamais masquées."""
import ast
import ipaddress
import json
import math
import operator as op
import re
import smtplib
import socket
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx

from .config import settings
from .database import execute, open_connection

# ---------- Calculator (évaluation AST sécurisée, pas d'eval) ----------
_BIN = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.Pow: op.pow, ast.Mod: op.mod, ast.FloorDiv: op.floordiv}
_UN = {ast.USub: op.neg, ast.UAdd: op.pos}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
          "log10": math.log10, "exp": math.exp, "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil}
_CONST = {"pi": math.pi, "e": math.e}


def calculator(expression: str) -> str:
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id in _CONST:
            return _CONST[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 1000:
                raise ValueError("exposant trop grand")
            return _BIN[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            return _UN[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("expression non autorisée")
    try:
        result = ev(ast.parse(expression.replace("^", "**"), mode="eval").body)
        return str(round(result, 10) if isinstance(result, float) else result)
    except ZeroDivisionError:
        return "Erreur : division par zéro"
    except Exception as exc:
        return f"Erreur de calcul : {exc}"


# ---------- HTTP Request (protégé contre le SSRF) ----------
def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def http_request(url: str, method: str = "GET", headers: dict | None = None, body: dict | None = None) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return "Erreur : URL invalide (http/https uniquement)."
    host = p.hostname.lower()
    if settings.http_allowed_hosts and host not in settings.http_allowed_hosts:
        return f"Erreur : hôte '{host}' non autorisé."
    if not _host_is_public(host):
        return "Erreur : adresse privée, locale ou introuvable — requête bloquée."
    method = method.upper()
    if method not in ("GET", "POST"):
        return "Erreur : seules les méthodes GET et POST sont autorisées."
    safe_headers = {k: v for k, v in (headers or {}).items() if k.lower() not in ("host", "content-length")}
    try:
        r = httpx.request(method, url, headers=safe_headers, json=body if method == "POST" else None,
                          timeout=15, follow_redirects=False)
        return f"HTTP {r.status_code}\n{r.text[:4000]}"
    except httpx.HTTPError as exc:
        return f"Erreur réseau : {exc}"


# ---------- Web search ----------
def web_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=min(max_results, 8))
    except Exception as exc:
        return f"Erreur de recherche web : {exc}"
    if not results:
        return "Aucun résultat."
    return "\n\n".join(f"{r.get('title')}\n{r.get('href')}\n{r.get('body')}" for r in results)


# ---------- Database (notes) ----------
def _notes_con(readonly: bool = False):
    con = open_connection(settings.notes_db, readonly=readonly)
    if not readonly:
        if settings.database_url:
            con.execute("""CREATE TABLE IF NOT EXISTS notes(
                id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        else:
            con.execute("""CREATE TABLE IF NOT EXISTS notes(
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        con.commit()
    return con


def db_save_note(title: str, content: str) -> str:
    con = _notes_con()
    try:
        if settings.database_url:
            cur = con.execute("INSERT INTO notes(title, content) VALUES (%s,%s) RETURNING id", (title, content))
            note_id = cur.fetchone()["id"]
        else:
            cur = con.execute("INSERT INTO notes(title, content) VALUES (?,?)", (title, content))
            note_id = cur.lastrowid
        con.commit()
        return f"Note enregistrée (id={note_id})."
    finally:
        con.close()


def db_query(sql: str) -> str:
    """SELECT uniquement, sur la table notes, connexion en lecture seule."""
    _notes_con().close()  # garantit l'existence du schéma
    s = sql.strip().rstrip(";")
    if not re.match(r"(?is)^select\b", s) or ";" in s or not re.search(r"(?i)\bnotes\b", s):
        return "Erreur : seule une requête SELECT unique sur la table 'notes' est autorisée."
    con = _notes_con(readonly=True)
    try:
        cur = con.execute(s)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchmany(50)
        data = rows if rows and isinstance(rows[0], dict) else [dict(zip(cols, r)) for r in rows]
        return json.dumps(data, ensure_ascii=False) if rows else "Aucun résultat."
    except Exception as exc:
        return f"Erreur SQL : {exc}"
    finally:
        con.close()


def db_delete_note(note_id: int) -> str:
    con = _notes_con()
    try:
        cur = execute(con, "DELETE FROM notes WHERE id=?", (int(note_id),))
        con.commit()
        return f"{cur.rowcount} note(s) supprimée(s)."
    finally:
        con.close()


# ---------- Email ----------
def send_email(to: str, subject: str, body: str) -> str:
    if not (settings.smtp_host and settings.smtp_from):
        return "Erreur : SMTP non configuré (SMTP_HOST / SMTP_FROM). Aucun email envoyé."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
        return "Erreur : adresse email invalide."
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return f"Email envoyé à {to}."
    except Exception as exc:
        return f"Erreur d'envoi : {exc}"


# ---------- Registre ----------
SENSITIVE = {"send_email", "db_delete_note"}  # nécessitent une confirmation humaine

FUNCTIONS = {"calculator": calculator, "http_request": http_request, "web_search": web_search,
             "db_query": db_query, "db_save_note": db_save_note, "db_delete_note": db_delete_note,
             "send_email": send_email}


def _s(d):
    return {"type": "string", "description": d}


TOOLS = [
    {"name": "calculator", "description": "Évalue une expression mathématique (+ - * / ** % sqrt sin cos log pi e…).",
     "input_schema": {"type": "object", "properties": {"expression": _s("Ex : (12.5*8)/3")}, "required": ["expression"]}},
    {"name": "web_search", "description": "Recherche sur Internet (infos récentes ou inconnues).",
     "input_schema": {"type": "object", "properties": {"query": _s("Requête courte et précise")}, "required": ["query"]}},
    {"name": "http_request", "description": "Appelle une API REST publique (GET/POST).",
     "input_schema": {"type": "object", "properties": {
         "url": _s("URL complète"), "method": {"type": "string", "enum": ["GET", "POST"]},
         "headers": {"type": "object"}, "body": {"type": "object"}}, "required": ["url"]}},
    {"name": "db_query", "description": "Lit les notes : requête SELECT sur la table notes(id, title, content, created_at).",
     "input_schema": {"type": "object", "properties": {"sql": _s("Ex : SELECT * FROM notes ORDER BY id DESC LIMIT 5")}, "required": ["sql"]}},
    {"name": "db_save_note", "description": "Enregistre une note en base de données.",
     "input_schema": {"type": "object", "properties": {"title": _s("Titre"), "content": _s("Contenu")}, "required": ["title", "content"]}},
    {"name": "db_delete_note", "description": "Supprime une note par id. NÉCESSITE la confirmation de l'utilisateur.",
     "input_schema": {"type": "object", "properties": {"note_id": {"type": "integer"}}, "required": ["note_id"]}},
    {"name": "send_email", "description": "Envoie un email. NÉCESSITE la confirmation de l'utilisateur.",
     "input_schema": {"type": "object", "properties": {"to": _s("Destinataire"), "subject": _s("Objet"), "body": _s("Corps")},
                      "required": ["to", "subject", "body"]}},
]


def active_tools() -> list:
    return [t for t in TOOLS if t["name"] not in settings.disabled_tools]


def run_tool(name: str, args: dict) -> str:
    if name in settings.disabled_tools:
        return f"Erreur : l'outil '{name}' est désactivé sur ce serveur."
    fn = FUNCTIONS.get(name)
    if not fn:
        return f"Erreur : outil inconnu '{name}'."
    try:
        return fn(**args)
    except TypeError as exc:
        return f"Erreur d'arguments : {exc}"
    except Exception as exc:
        return f"Erreur de l'outil {name} : {exc}"
