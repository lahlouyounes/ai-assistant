import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const HISTORY_KEY = 'atelierai-conversations-v1';
const makeSession = () => `web-${Math.random().toString(36).slice(2, 12)}`;
const makeConversation = () => ({ id: makeSession(), title: 'Nouvelle conversation', updatedAt: Date.now(), messages: [], documents: [] });
function loadHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    if (Array.isArray(saved) && saved.length) return saved;
  } catch { /* Start with an empty conversation if browser storage is unavailable. */ }
  const oldId = (() => { try { return localStorage.getItem('sid'); } catch { return ''; } })();
  return [{ ...makeConversation(), ...(oldId ? { id: oldId } : {}) }];
}

function Icon({ name, size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };
  const paths = {
    sparkle: <><path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 11l6.1-2.2L12 3Z"/><path d="m19 15 1 2.5 2.5 1-2.5 1L19 22l-1-2.5-2.5-1 2.5-1L19 15Z"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>, send: <><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></>,
    check: <path d="m5 12 4 4L19 6"/>, close: <><path d="m18 6-12 12M6 6l12 12"/></>,
    lock: <><rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 1 1 8 0v3"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    trash: <><path d="M3 6h18M8 6V4h8v2m3 0-1 14H6L5 6m4 4v6m6-6v6"/></>,
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function App() {
  const [history, setHistory] = useState(loadHistory);
  const [sessionId, setSessionId] = useState(() => {
    try { const active = localStorage.getItem('atelierai-active'); return history.some((item) => item.id === active) ? active : history[0].id; } catch { return history[0].id; }
  });
  const [messages, setMessages] = useState(() => history.find((item) => item.id === sessionId)?.messages || []);
  const [documents, setDocuments] = useState(() => history.find((item) => item.id === sessionId)?.documents || []);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(() => { try { return sessionStorage.getItem('tok') || ''; } catch { return ''; } });
  const [tokenInput, setTokenInput] = useState(() => { try { return sessionStorage.getItem('tok') || ''; } catch { return ''; } });
  const [needsAuth, setNeedsAuth] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const fileRef = useRef(null);
  const inputRef = useRef(null);
  const endRef = useRef(null);
  const activeSessionRef = useRef(sessionId);
  const headers = () => ({ ...(token ? { Authorization: `Bearer ${token}` } : {}) });
  const activeConversation = history.find((item) => item.id === sessionId);
  const filteredHistory = useMemo(() => history.filter((item) => item.title.toLowerCase().includes(search.toLowerCase())), [history, search]);

  useEffect(() => {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)); localStorage.setItem('atelierai-active', sessionId); } catch { setError('Le stockage du navigateur est plein. Supprimez quelques anciennes conversations.'); }
  }, [history, sessionId]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, busy]);
  useEffect(() => {
    fetch('/health').then((response) => response.json()).then((health) => { if (health.auth_required && !token) setNeedsAuth(true); }).catch(() => {});
  }, []);

  function updateConversation(id, patch) {
    setHistory((items) => items.map((item) => item.id === id ? { ...item, ...patch, updatedAt: Date.now() } : item));
  }

  async function loadDocuments(id, authToken = token) {
    try {
      const response = await fetch(`/documents/${encodeURIComponent(id)}`, { headers: authToken ? { Authorization: `Bearer ${authToken}` } : {} });
      if (response.status === 401) { setNeedsAuth(true); return; }
      if (response.ok) { const result = await response.json(); updateConversation(id, { documents: result.documents || [] }); if (activeSessionRef.current === id) setDocuments(result.documents || []); }
    } catch { /* Conversation text remains available when the API is offline. */ }
  }

  function startConversation() {
    const next = makeConversation();
    activeSessionRef.current = next.id; setHistory((items) => [next, ...items]); setSessionId(next.id); setMessages([]); setDocuments([]); setError(''); setDraft(''); inputRef.current?.focus();
  }

  function openConversation(item) {
    activeSessionRef.current = item.id; setSessionId(item.id); setMessages(item.messages || []); setDocuments(item.documents || []); setError(''); setDraft(''); loadDocuments(item.id);
  }

  async function deleteConversation(item) {
    try {
      const response = await fetch(`/sessions/${encodeURIComponent(item.id)}`, { method: 'DELETE', headers: headers() });
      if (response.status === 401) { setNeedsAuth(true); return; }
      if (!response.ok) throw new Error('Impossible de supprimer la conversation du serveur.');
    } catch (deleteError) { setError(deleteError.message); return; }
    const remaining = history.filter((entry) => entry.id !== item.id);
    if (!remaining.length) remaining.push(makeConversation());
    setHistory(remaining);
    if (item.id === activeSessionRef.current) { activeSessionRef.current = remaining[0].id; setSessionId(remaining[0].id); setMessages(remaining[0].messages || []); setDocuments(remaining[0].documents || []); }
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    const targetId = sessionId;
    setDraft(''); setError(''); setBusy(true);
    const userId = crypto.randomUUID(); const answerId = crypto.randomUUID();
    const nextMessages = [...messages, { id: userId, role: 'user', text }, { id: answerId, role: 'assistant', text: '', loading: true }];
    setMessages(nextMessages);
    const title = messages.length === 0 ? text.slice(0, 46) + (text.length > 46 ? '…' : '') : activeConversation?.title;
    updateConversation(targetId, { messages: nextMessages, title });
    try {
      const response = await fetch('/chat', { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: targetId, message: text }) });
      const result = await response.json();
      if (response.status === 401) { setNeedsAuth(true); throw new Error("Le code d’accès est requis pour continuer."); }
      if (!response.ok) throw new Error(result.detail || 'Une erreur est survenue. Réessayez.');
      const finalMessages = [...nextMessages.map((message) => message.id === answerId ? { ...message, text: result.reply || 'Je n’ai pas reçu de réponse.', loading: false } : message), ...(result.pending_actions || []).map((action) => ({ id: crypto.randomUUID(), role: 'action', action }))];
      updateConversation(targetId, { messages: finalMessages, title }); if (activeSessionRef.current === targetId) setMessages(finalMessages);
    } catch (requestError) {
      const failedMessages = nextMessages.map((message) => message.id === answerId ? { ...message, text: requestError.message || 'Erreur réseau. Vérifiez votre connexion.', loading: false } : message);
      updateConversation(targetId, { messages: failedMessages, title }); if (activeSessionRef.current === targetId) setMessages(failedMessages);
    } finally { setBusy(false); }
  }

  async function handleAction(messageId, action, approve) {
    const targetId = sessionId;
    setMessages((current) => current.map((message) => message.id === messageId ? { ...message, pending: true } : message));
    try {
      const response = await fetch(`/actions/${encodeURIComponent(action.id)}`, { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: targetId, approve }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Impossible de traiter cette action.');
      const changed = messages.map((message) => message.id === messageId ? { ...message, role: 'notice', text: result.result || (approve ? 'Action confirmée.' : 'Action refusée.'), pending: false } : message);
      updateConversation(targetId, { messages: changed }); if (activeSessionRef.current === targetId) setMessages(changed);
    } catch (requestError) { setMessages((current) => current.map((message) => message.id === messageId ? { ...message, pending: false } : message)); setError(requestError.message); }
  }

  async function importPdf(event) {
    const file = event.target.files?.[0]; event.target.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) { setError('Choisissez un fichier PDF.'); return; }
    if (file.size > 15 * 1024 * 1024) { setError('Le PDF doit faire 15 Mo ou moins.'); return; }
    const targetId = sessionId;
    setBusy(true); setError('');
    const form = new FormData(); form.append('file', file);
    try {
      const response = await fetch(`/documents/${encodeURIComponent(targetId)}`, { method: 'POST', headers: headers(), body: form });
      const result = await response.json();
      if (response.status === 401) { setNeedsAuth(true); throw new Error('Saisissez le code d’accès pour importer un PDF.'); }
      if (!response.ok) throw new Error(result.detail || 'Le PDF n’a pas pu être importé.');
      const nextDocs = [...(history.find((item) => item.id === targetId)?.documents || []), result.document]; updateConversation(targetId, { documents: nextDocs }); if (activeSessionRef.current === targetId) setDocuments(nextDocs);
      if (result.truncated) setError('Le PDF est importé, mais son texte a été raccourci pour tenir dans le contexte de l’assistant.');
    } catch (uploadError) { setError(uploadError.message || 'Erreur réseau pendant l’import.'); }
    finally { setBusy(false); }
  }

  async function removePdf(document) {
    const targetId = sessionId;
    try {
      const response = await fetch(`/documents/${encodeURIComponent(targetId)}/${encodeURIComponent(document.id)}`, { method: 'DELETE', headers: headers() });
      if (response.status === 401) { setNeedsAuth(true); return; }
      if (!response.ok) throw new Error('Impossible de retirer le PDF.');
      const nextDocs = (history.find((item) => item.id === targetId)?.documents || []).filter((item) => item.id !== document.id); updateConversation(targetId, { documents: nextDocs }); if (activeSessionRef.current === targetId) setDocuments(nextDocs);
    } catch (removeError) { setError(removeError.message); }
  }

  function saveToken(event) {
    event.preventDefault(); const nextToken = tokenInput.trim(); setToken(nextToken); setNeedsAuth(false); setError('');
    try { sessionStorage.setItem('tok', nextToken); } catch { /* Optional browser storage. */ }
    loadDocuments(sessionId, nextToken);
  }

  function printConversation() {
    if (!messages.some((message) => message.role === 'user' || message.role === 'assistant')) { setError('Écrivez au moins un message avant d’exporter la conversation.'); return; }
    window.print();
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#home" aria-label="Atelier AI, accueil"><span className="brand-icon"><Icon name="sparkle" size={19}/></span><span className="brand-name">atelier<span>ai</span></span></a>
        <button className="new-chat" onClick={startConversation}><Icon name="plus" size={17}/> Nouvelle conversation</button>
        <label className="history-search"><Icon name="search" size={16}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Rechercher une conversation"/></label>
        <div className="history-heading">RÉCENTES <span>{filteredHistory.length}</span></div>
        <nav className="conversation-history" aria-label="Historique des conversations">
          {filteredHistory.length ? filteredHistory.map((item) => <div className={`history-item ${item.id === sessionId ? 'active' : ''}`} key={item.id}>
            <button className="history-open" onClick={() => openConversation(item)} title={item.title}><span className="history-title">{item.title}</span><span className="history-date">{new Intl.DateTimeFormat('fr', { dateStyle: 'short' }).format(new Date(item.updatedAt))}</span></button>
            <button className="history-delete" onClick={() => deleteConversation(item)} aria-label={`Supprimer ${item.title}`} title="Supprimer"><Icon name="trash" size={14}/></button>
          </div>) : <p className="history-empty">Aucune conversation trouvée.</p>}
        </nav>
        <div className="sidebar-bottom"><span className="status-dot"/> Assistant disponible</div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="mobile-brand"><span className="brand-icon"><Icon name="sparkle" size={17}/></span> atelier<span>ai</span></div>
          <div className="model-pill"><span className="model-dot"/> Assistant IA <span className="model-separator">·</span> Multilingue</div>
          <div className="topbar-actions"><button className="export-btn" onClick={printConversation}><Icon name="download" size={15}/><span>Exporter PDF</span></button><button className="topbar-new" onClick={startConversation}><Icon name="plus" size={16}/><span>Nouveau chat</span></button></div>
        </header>

        <section className={`conversation ${messages.length ? 'has-messages' : ''}`} aria-live="polite">
          {messages.length === 0 ? <div className="welcome"><div className="welcome-mark"><Icon name="sparkle" size={25}/></div><p className="eyebrow">VOTRE ESPACE DE RÉFLEXION</p><h1>Bonjour, que pouvons-nous<br className="desktop-break"/> <span>imaginer ensemble&nbsp;?</span></h1><p className="welcome-copy">Posez une question, explorez une idée ou demandez un coup de main.<br className="desktop-break"/> On part de là.</p><div className="suggestions">{['Explique-moi quelque chose de complexe simplement', 'Aide-moi à organiser mes idées', 'Que peux-tu faire pour moi ?'].map((suggestion, index) => <button key={suggestion} className="suggestion" onClick={() => { setDraft(suggestion); inputRef.current?.focus(); }}><span className="suggestion-index">0{index + 1}</span><span>{suggestion}</span><span className="suggestion-arrow">↗</span></button>)}</div></div> : <div className="message-list">
            {messages.map((message) => message.role === 'action' ? <article className="action-card" key={message.id}><div className="action-header"><span className="action-lock"><Icon name="lock" size={15}/></span><div><strong>Votre confirmation est requise</strong><span>L’assistant souhaite utiliser {message.action.tool}</span></div></div><pre>{JSON.stringify(message.action.args, null, 2)}</pre><div className="action-buttons"><button disabled={message.pending} onClick={() => handleAction(message.id, message.action, false)}>Refuser</button><button className="approve" disabled={message.pending} onClick={() => handleAction(message.id, message.action, true)}><Icon name="check" size={15}/> Confirmer</button></div></article> : message.role === 'notice' ? <div className="notice" key={message.id}><Icon name="check" size={15}/> {message.text}</div> : <article className={`message ${message.role}`} key={message.id}>{message.role === 'assistant' && <span className="avatar"><Icon name="sparkle" size={15}/></span>}<div className="message-content"><span className="message-label">{message.role === 'user' ? 'VOUS' : 'ATELIER AI'}</span><div className="message-text">{message.loading ? <span className="typing"><i/><i/><i/></span> : message.text}</div></div></article>)}
            <div ref={endRef}/>
          </div>}
        </section>

        {error && <div className="error-banner" role="alert">{error}<button aria-label="Fermer" onClick={() => setError('')}><Icon name="close" size={15}/></button></div>}

        <footer className="composer-wrap">
          {documents.length > 0 && <div className="document-chips">{documents.map((document) => <div className="document-chip" key={document.id}><Icon name="file" size={14}/><span title={document.filename}>{document.filename}</span><button onClick={() => removePdf(document)} aria-label={`Retirer ${document.filename}`}><Icon name="close" size={13}/></button></div>)}</div>}
          <form className="composer" onSubmit={sendMessage}>
            <input ref={fileRef} className="file-input" type="file" accept="application/pdf,.pdf" onChange={importPdf}/>
            <button className="attach-button" type="button" onClick={() => fileRef.current?.click()} disabled={busy} title="Importer un PDF" aria-label="Importer un PDF"><Icon name="file" size={18}/></button>
            <textarea ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); } }} rows={1} dir="auto" placeholder={documents.length ? 'Posez une question sur le PDF…' : 'Écrivez votre message… / Type a message… / اكتب رسالتك'} aria-label="Votre message"/>
            <button className="send-button" type="submit" disabled={!draft.trim() || busy} aria-label="Envoyer"><Icon name="send" size={17}/></button>
          </form>
          <p className="composer-hint">Entrée pour envoyer <span>·</span> Maj + Entrée pour une nouvelle ligne <span>·</span> PDF jusqu’à 15 Mo</p>
        </footer>
      </main>

      {needsAuth && <div className="modal-backdrop" role="presentation"><section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title"><button className="modal-close" onClick={() => setNeedsAuth(false)} aria-label="Fermer"><Icon name="close"/></button><span className="auth-icon"><Icon name="lock" size={19}/></span><p className="eyebrow">ACCÈS SÉCURISÉ</p><h2 id="auth-title">Un petit code, et c’est parti.</h2><p className="auth-copy">Saisissez le code d’accès pour retrouver votre assistant.</p><form onSubmit={saveToken}><label htmlFor="access-code">Code d’accès</label><input id="access-code" type="password" autoFocus value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} placeholder="Votre code d’accès"/><button className="auth-submit" type="submit">Continuer <span>→</span></button></form></section></div>}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
