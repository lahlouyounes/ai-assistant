from types import SimpleNamespace as NS

from app import agent, memory, tools


def test_calculator():
    assert tools.calculator("(12.5*8)/3") == "33.3333333333"
    assert tools.calculator("2^10") == "1024"
    assert "Erreur" in tools.calculator("__import__('os').system('ls')")
    assert "Erreur" in tools.calculator("1/0")
    assert "Erreur" in tools.calculator("9**9**9")


def test_ssrf_blocked():
    assert "bloquée" in tools.http_request("http://127.0.0.1:8000")
    assert "bloquée" in tools.http_request("http://169.254.169.254/latest/meta-data")
    assert "invalide" in tools.http_request("file:///etc/passwd")


def test_db_roundtrip_and_readonly():
    assert "enregistrée" in tools.db_save_note("t", "c")
    assert "t" in tools.db_query("SELECT * FROM notes")
    assert "Erreur" in tools.db_query("DELETE FROM notes")
    assert "Erreur" in tools.db_query("SELECT 1; DROP TABLE notes")


def test_memory_isolated_by_session():
    memory.save_message("a", "user", "salut A")
    memory.save_message("b", "user", "salut B")
    assert memory.load_history("a") == [{"role": "user", "content": "salut A"}]
    memory.clear_session("a")
    assert memory.load_history("a") == []


def test_sensitive_tool_requires_confirmation(monkeypatch):
    sent = []
    monkeypatch.setitem(tools.FUNCTIONS, "send_email", lambda **k: sent.append(k) or "ok")
    call = NS(type="tool_use", id="1", name="send_email", input={"to": "a@b.co", "subject": "s", "body": "b"})
    replies = iter([NS(stop_reason="tool_use", content=[call]),
                    NS(stop_reason="end_turn", content=[NS(type="text", text="En attente de confirmation")])])
    client = NS(messages=NS(create=lambda **k: next(replies)))
    out = agent.chat("s1", "envoie un mail", client=client)
    assert sent == [] and len(out["pending_actions"]) == 1
    pid = out["pending_actions"][0]["id"]
    assert agent.confirm("other-session", pid, True) == "Action introuvable ou déjà traitée."
    assert agent.confirm("s1", pid, True) == "ok" and len(sent) == 1
    assert "introuvable" in agent.confirm("s1", pid, True)


# ---------- Mode public : accès, débit, outils désactivés ----------
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.ratelimit import Limiter


def _client(monkeypatch, **cfg):
    for k, v in cfg.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(main, "limiter", Limiter())
    monkeypatch.setattr(main.agent, "chat", lambda sid, msg: {"reply": "ok", "pending_actions": []})
    return TestClient(main.app)


def test_auth_required(monkeypatch):
    c = _client(monkeypatch, api_token="secret", rate_limit_per_min=100)
    body = {"session_id": "s", "message": "hi"}
    assert c.get("/health").json()["auth_required"] is True
    assert c.post("/chat", json=body).status_code == 401
    assert c.post("/chat", json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.post("/chat", json=body, headers={"Authorization": "Bearer secret"}).status_code == 200


def test_rate_limit_and_daily_cap(monkeypatch):
    c = _client(monkeypatch, api_token="", rate_limit_per_min=2, daily_cap=0)
    body = {"session_id": "s", "message": "hi"}
    assert [c.post("/chat", json=body).status_code for _ in range(3)] == [200, 200, 429]
    c = _client(monkeypatch, api_token="", rate_limit_per_min=0, daily_cap=1)
    assert [c.post("/chat", json=body).status_code for _ in range(2)] == [200, 429]


def test_disabled_tools(monkeypatch):
    monkeypatch.setattr(settings, "disabled_tools", ["send_email"])
    assert "send_email" not in [t["name"] for t in tools.active_tools()]
    assert "désactivé" in tools.run_tool("send_email", {"to": "a@b.co", "subject": "s", "body": "b"})


# ---------- Fournisseur Gemini (API compatible OpenAI) ----------
import json as _json


def _gemini_reply(content=None, calls=None):
    m = {"role": "assistant", "content": content}
    if calls:
        m["tool_calls"] = [{"id": f"c{i}", "type": "function",
                            "function": {"name": n, "arguments": _json.dumps(a)}} for i, (n, a) in enumerate(calls)]
    return {"choices": [{"message": m}]}


def test_gemini_tool_loop(monkeypatch):
    monkeypatch.setattr(settings, "provider", "gemini")
    seen = []
    replies = iter([_gemini_reply(calls=[("calculator", {"expression": "2+2"})]),
                    _gemini_reply(content="Le résultat est 4")])

    def fake(messages):
        seen.append(list(messages))
        return next(replies)
    monkeypatch.setattr(agent, "_openai_call", fake)
    out = agent.chat("g1", "2+2 ?")
    assert out["reply"] == "Le résultat est 4"
    tool_msg = [m for m in seen[1] if m["role"] == "tool"][0]
    assert tool_msg["content"] == "4"
    assert memory.load_history("g1")[-1]["content"] == "Le résultat est 4"


def test_gemini_sensitive_needs_confirmation(monkeypatch):
    monkeypatch.setattr(settings, "provider", "gemini")
    sent = []
    monkeypatch.setitem(tools.FUNCTIONS, "send_email", lambda **k: sent.append(k) or "ok")
    replies = iter([_gemini_reply(calls=[("send_email", {"to": "a@b.co", "subject": "s", "body": "b"})]),
                    _gemini_reply(content="En attente de votre confirmation")])
    monkeypatch.setattr(agent, "_openai_call", lambda m: next(replies))
    out = agent.chat("g2", "envoie")
    assert sent == [] and len(out["pending_actions"]) == 1
    assert agent.confirm("g2", out["pending_actions"][0]["id"], True) == "ok" and len(sent) == 1


def test_gemini_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    import pytest
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        agent._openai_call([])
