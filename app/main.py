import secrets
import threading
from io import BytesIO
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, memory
from .config import settings
from .ratelimit import limiter

app = FastAPI(title="AI Assistant", version="1.0.0")
STATIC = Path(__file__).parent / "static"
app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
OCR_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr import EngineType, LangCls, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

    return RapidOCR(params={
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": LangDet.MULTI,
        "Det.model_type": ModelType.MOBILE,
        "Det.ocr_version": OCRVersion.PPOCRV4,
        "Cls.engine_type": EngineType.ONNXRUNTIME,
        "Cls.lang_type": LangCls.MULTI,
        "Cls.model_type": ModelType.MOBILE,
        "Cls.ocr_version": OCRVersion.PPOCRV4,
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": LangRec.ARABIC,
        "Rec.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV4,
    })


def _ocr_pages(raw: bytes, page_texts: list[str]) -> list[str]:
    try:
        import fitz
        import numpy as np
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise HTTPException(503, "Installez les dépendances OCR avec « pip install -r requirements.txt », puis redémarrez le serveur.") from exc

    blank_pages = [index for index, text in enumerate(page_texts) if not text.strip()]
    if len(blank_pages) > 30:
        raise HTTPException(413, "L’OCR est limitée à 30 pages scannées par import. Scindez le PDF en plusieurs fichiers.")
    if not blank_pages:
        return page_texts

    try:
        with OCR_LOCK:
            engine: RapidOCR = _ocr_engine()
            pdf = fitz.open(stream=raw, filetype="pdf")
            for index in blank_pages:
                pixmap = pdf[index].get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
                result = engine(image)
                recognized = getattr(result, "txts", None) if result else None
                page_texts[index] = "\n".join(part for part in (recognized or ()) if part).strip()
            pdf.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "La reconnaissance OCR a échoué. Vérifiez la qualité du scan et réessayez.") from exc
    return page_texts


def auth(authorization: str = Header(default="")):
    if settings.api_token and not secrets.compare_digest(authorization, f"Bearer {settings.api_token}"):
        raise HTTPException(401, "Token invalide")


def guard(request: Request):
    ip = request.client.host if request.client else "unknown"
    if settings.trust_proxy:
        ip = request.headers.get("x-forwarded-for", ip).split(",")[0].strip()
    ok, reason = limiter.check(ip)
    if not ok:
        raise HTTPException(429, reason)


class ChatIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w\-]+$")
    message: str = Field(min_length=1, max_length=8000)


class ConfirmIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w\-]+$")
    approve: bool


def _check_session_id(session_id: str) -> None:
    if len(session_id) > 64 or not session_id or not all(c.isalnum() or c in "_-" for c in session_id):
        raise HTTPException(400, "Identifiant de conversation invalide")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "auth_required": bool(settings.api_token)}


@app.post("/chat", dependencies=[Depends(auth), Depends(guard)])
def chat(body: ChatIn):
    try:
        context = memory.load_documents_context(body.session_id)
        if context:
            return agent.chat(body.session_id, body.message, document_context=context)
        return agent.chat(body.session_id, body.message)
    except Exception as exc:
        raise HTTPException(502, f"Erreur du modèle : {exc}")


@app.post("/actions/{pending_id}", dependencies=[Depends(auth)])
def action(pending_id: str, body: ConfirmIn):
    return {"result": agent.confirm(body.session_id, pending_id, body.approve)}


@app.delete("/sessions/{session_id}", dependencies=[Depends(auth)])
def reset(session_id: str):
    _check_session_id(session_id)
    memory.clear_session(session_id)
    return {"status": "cleared"}


@app.get("/documents/{session_id}", dependencies=[Depends(auth)])
def documents(session_id: str):
    _check_session_id(session_id)
    return {"documents": memory.list_documents(session_id)}


@app.post("/documents/{session_id}", dependencies=[Depends(auth)])
async def upload_document(session_id: str, file: UploadFile = File(...)):
    _check_session_id(session_id)
    filename = (file.filename or "document.pdf").replace("\\", "/").split("/")[-1][:180]
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Choisissez un fichier PDF.")
    raw = await file.read(15 * 1024 * 1024 + 1)
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "Le PDF dépasse la limite de 15 Mo.")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(415, "Le fichier sélectionné n’est pas un PDF valide.")
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise HTTPException(422, "Ce PDF est protégé par un mot de passe.")
        if len(reader.pages) > 100:
            raise HTTPException(413, "Le PDF dépasse la limite de 100 pages.")
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "Le contenu de ce PDF n’a pas pu être lu.") from exc
    if any(not page_text.strip() for page_text in page_texts):
        page_texts = _ocr_pages(raw, page_texts)
    text = "\n".join(page_text for page_text in page_texts if page_text.strip()).strip()
    if not text:
        raise HTTPException(422, "Aucun texte n’a pu être reconnu dans ce PDF. Vérifiez la qualité du scan.")
    text = text[:30000]
    document = memory.add_document(session_id, filename, text, len(reader.pages))
    return {"document": document, "truncated": len(text) == 30000}


@app.delete("/documents/{session_id}/{document_id}", dependencies=[Depends(auth)])
def remove_document(session_id: str, document_id: str):
    _check_session_id(session_id)
    if not memory.delete_document(session_id, document_id):
        raise HTTPException(404, "PDF introuvable dans cette conversation.")
    return {"status": "deleted"}
