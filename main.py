import os
import json
import asyncio
import logging
import hashlib
import base64
import datetime
from collections import defaultdict
from typing import Optional, List, Any

import easyocr
import cv2
import numpy as np
from PIL import Image
from io import BytesIO

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, validator, ValidationError

import requests
from groq import Groq
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  APP SETUP
# ══════════════════════════════════════════════════════════════════════

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Eatlytic API — Production")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════
#  PATHS & FILE-BASED CACHE
#  Redis-ready: replace load_cache/save_cache with redis.get / redis.set
# ══════════════════════════════════════════════════════════════════════

DATA_DIR   = os.path.join(os.getcwd(), "data")
CACHE_DIR  = os.environ.get("HF_HOME", "/app/.cache")
MODEL_DIR  = os.path.join(CACHE_DIR, "easyocr_models")

for d in [MODEL_DIR, DATA_DIR]:
    os.makedirs(d, exist_ok=True)

OCR_CACHE_FILE = os.path.join(DATA_DIR, "ocr_cache.json")
AI_CACHE_FILE  = os.path.join(DATA_DIR, "ai_cache.json")


def load_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache: dict, path: str) -> None:
    try:
        with open(path, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


ocr_cache = load_cache(OCR_CACHE_FILE)
ai_cache  = load_cache(AI_CACHE_FILE)

# ══════════════════════════════════════════════════════════════════════
#  CLIENTS & KEYS
# ══════════════════════════════════════════════════════════════════════

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY missing!")
    client = None
else:
    client = Groq(api_key=GROQ_API_KEY)

SERPER_KEY = os.environ.get("SERPER_KEY")
if not SERPER_KEY:
    logger.warning("SERPER_KEY missing — web search disabled.")

HF_TOKEN = os.environ.get("HF_TOKEN")
if HF_TOKEN:
    os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN
    logger.info("HF_TOKEN loaded.")

reader = easyocr.Reader(
    ["en", "ch_sim"],
    gpu=False,
    model_storage_directory=MODEL_DIR,
)


# ══════════════════════════════════════════════════════════════════════
#  SECTION A: FREEMIUM QUOTA SYSTEM  (P0 fix)
#
#  In-memory with UTC midnight reset.
#  To switch to Redis (recommended for production):
#    check_scan_quota  →  r.get(f"quota:{ip}:{today}") with EXPIREAT
#    consume_scan      →  r.incr(f"quota:{ip}:{today}") + r.expireat(...)
# ══════════════════════════════════════════════════════════════════════

FREE_DAILY_LIMIT = 5
_quota_store: dict = defaultdict(lambda: {"count": 0, "date": ""})


def _today_utc() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def check_scan_quota(ip: str) -> dict:
    today = _today_utc()
    rec   = _quota_store[ip]
    if rec["date"] != today:
        rec["count"] = 0
        rec["date"]  = today
    used = rec["count"]
    return {
        "used":      used,
        "remaining": max(0, FREE_DAILY_LIMIT - used),
        "limit":     FREE_DAILY_LIMIT,
        "allowed":   used < FREE_DAILY_LIMIT,
    }


def consume_scan(ip: str) -> None:
    today = _today_utc()
    rec   = _quota_store[ip]
    if rec["date"] != today:
        rec["count"] = 0
        rec["date"]  = today
    rec["count"] += 1


# ══════════════════════════════════════════════════════════════════════
#  SECTION B: PERSONA CONTEXTS
#  6 deep clinical contexts injected into the LLM chain-of-thought prompt.
# ══════════════════════════════════════════════════════════════════════

PERSONA_CONTEXT: dict = {
    "general": (
        "Evaluating for a general health-conscious adult. Focus on overall nutritional quality, "
        "additive transparency, ultra-processed food markers (NOVA score signals), and balanced "
        "macronutrient ratio. Flag E-numbers, artificial colours, and preservatives with known "
        "health concerns."
    ),
    "gym": (
        "Evaluating for an active gym-goer / athlete. Prioritise: complete amino acid profile, "
        "BCAA content (leucine, isoleucine, valine), anabolic vs catabolic signals (protein:carb "
        "ratio post-workout), creatine presence, beta-alanine, electrolyte balance (Na/K/Mg), and "
        "total caloric density. Flag high-fructose corn syrup, excessive added sugar, and artificial "
        "sweeteners that may impair insulin sensitivity or gut health during training."
    ),
    "baby": (
        "Evaluating for infants and toddlers (0–3 years). Apply SAFETY-FIRST clinical standard. "
        "Flag: sodium >100mg/serving (WHO 0–12mo limit), added sugars in any form, artificial "
        "sweeteners (aspartame, saccharin, sucralose), honey (Clostridium botulinum risk <12mo), "
        "whole nuts (choking hazard), high-allergen ingredients (peanut, tree nut, milk, egg, soy, "
        "wheat, fish, shellfish), nitrates/nitrites in processed meats. Reference NHS, WHO, EFSA "
        "infant nutrition guidelines. Never state 'safe' without qualification."
    ),
    "skin": (
        "Evaluating for someone focused on skin health and appearance. Highlight: omega-3 fatty "
        "acids (anti-inflammatory), zinc (sebum regulation), vitamin C (collagen synthesis), lysine "
        "(collagen precursor), vitamin A/beta-carotene (cell turnover), selenium (antioxidant). "
        "Flag: high glycaemic index foods (glycation = collagen degradation), dairy (IGF-1 / acne "
        "link), trans fats, high omega-6:omega-3 ratio (pro-inflammatory). Map each nutrient to a "
        "visible skin outcome."
    ),
    "keto": (
        "Evaluating for a strict ketogenic diet (<20g net carbs/day). Calculate NET CARBS = Total "
        "Carbohydrates − Dietary Fiber − Sugar Alcohols (erythritol=0, xylitol=2.4 cal/g, "
        "maltitol=2.1 cal/g). Flag HIDDEN SUGARS: maltodextrin (GI=130), dextrose, modified starch, "
        "corn syrup solids, fruit juice concentrate, agave, honey. Check electrolytes (Na, K, Mg) — "
        "keto increases renal excretion. Flag any 'keto' claims that fail net carb scrutiny."
    ),
    "heart": (
        "Evaluating for cardiovascular disease risk or existing heart condition. Apply AHA guidelines. "
        "Flag: sodium >600mg/serving (AHA limit 1500mg/day for heart patients), saturated fat >7% "
        "of daily calories, trans fats (zero tolerance), cholesterol >200mg/serving. Highlight: "
        "plant sterols/stanols (>0.8g/serving — proven LDL reduction), soluble fiber (beta-glucan, "
        "psyllium), omega-3 DHA/EPA (anti-arrhythmic), potassium (BP regulation). Note warfarin "
        "interactions: flag vitamin K-rich foods."
    ),
}


# ══════════════════════════════════════════════════════════════════════
#  SECTION C: PYDANTIC RESPONSE MODELS  (P0 fix — LLM output validation)
#
#  These models catch invalid/hallucinated LLM output before it reaches
#  the client. Bad fields fall back to sensible defaults automatically.
# ══════════════════════════════════════════════════════════════════════

class HealthWarning(BaseModel):
    severity:        str       = "low"
    category:        str       = ""
    warning:         str       = ""
    affected_groups: List[str] = []

    @validator("severity")
    def check_sev(cls, v):
        return v if v in {"critical", "moderate", "low"} else "low"


class NutrientItem(BaseModel):
    name:   str = ""
    value:  Any = 0
    unit:   str = ""
    rating: str = "moderate"
    impact: str = ""

    @validator("rating")
    def check_rating(cls, v):
        return v if v in {"good", "moderate", "caution", "bad"} else "moderate"


class AgeWarning(BaseModel):
    group:   str = ""
    emoji:   str = "👤"
    status:  str = "caution"
    message: str = ""

    @validator("status")
    def check_status(cls, v):
        return v if v in {"good", "caution", "warning"} else "caution"


class SpotlightItem(BaseModel):
    name:      str = ""
    role:      str = ""
    curiosity: str = ""


class AnalysisResponse(BaseModel):
    product_name:            str              = "Unknown Product"
    product_category:        str              = "Food"
    score:                   int              = 5
    verdict:                 str              = "Needs Review"
    is_low_confidence:       bool             = False
    chart_data:              List[float]      = [34, 33, 33]
    summary:                 str              = ""
    eli5_explanation:        str              = ""
    molecular_insight:       str              = ""
    paragraph_benefits:      str              = ""
    paragraph_uniqueness:    str              = ""
    is_unique:               bool             = False
    ingredients_list:        List[str]        = []
    health_warnings:         List[HealthWarning]   = []
    allergens:               List[str]        = []
    contraindications:       List[str]        = []
    nutrient_breakdown:      List[NutrientItem]    = []
    pros:                    List[str]        = []
    cons:                    List[str]        = []
    age_warnings:            List[AgeWarning]     = []
    daily_limit:             str              = ""
    optimal_timing:          str              = ""
    overconsumption_effects: str              = ""
    dietary_advice:          str              = ""
    curiosity_fact:          str              = ""
    wellness_tip:            str              = ""
    ingredients_spotlight:   List[SpotlightItem]  = []
    better_alternative:      str              = ""

    @validator("score")
    def clamp_score(cls, v):
        try:
            return max(1, min(10, int(v)))
        except Exception:
            return 5

    @validator("chart_data")
    def normalise_chart(cls, v):
        if not v or len(v) != 3:
            return [34, 33, 33]
        total = sum(v)
        if total == 0:
            return [34, 33, 33]
        norm = [round(x * 100 / total) for x in v]
        norm[0] += 100 - sum(norm)   # fix rounding drift
        return norm


# ══════════════════════════════════════════════════════════════════════
#  SECTION 1: MULTI-METHOD BLUR DETECTION
# ══════════════════════════════════════════════════════════════════════

def _laplacian_score(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _tenengrad_score(gray: np.ndarray) -> float:
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    return float(np.mean(gx ** 2 + gy ** 2))


def _brenner_score(gray: np.ndarray) -> float:
    diff = gray[:, 2:].astype(np.float64) - gray[:, :-2].astype(np.float64)
    return float(np.mean(diff ** 2))


def _local_blur_map(gray: np.ndarray, block: int = 64) -> float:
    h, w = gray.shape
    scores = [
        cv2.Laplacian(gray[y:y + block, x:x + block], cv2.CV_64F).var()
        for y in range(0, h - block, block)
        for x in range(0, w - block, block)
    ]
    return float(np.median(scores)) if scores else 0.0


def assess_image_quality(content: bytes) -> dict:
    try:
        img   = Image.open(BytesIO(content)).convert("RGB")
        gray  = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

        lap   = _laplacian_score(gray)
        ten   = _tenengrad_score(gray)
        bren  = _brenner_score(gray)
        local = _local_blur_map(gray)

        composite = (
            0.25 * min(lap   / 300.0 * 100, 100) +
            0.20 * min(ten   / 500.0 * 100, 100) +
            0.20 * min(bren  / 200.0 * 100, 100) +
            0.35 * min(local / 300.0 * 100, 100)
        )

        if composite < 15:
            severity, is_blurry = "severe",   True
        elif composite < 35:
            severity, is_blurry = "moderate", True
        elif composite < 55:
            severity, is_blurry = "mild",     True
        else:
            severity, is_blurry = "none",     False

        return {
            "blur_score":        round(composite, 2),
            "laplacian_score":   round(lap, 2),
            "tenengrad_score":   round(ten, 2),
            "brenner_score":     round(bren, 2),
            "local_median_score": round(local, 2),
            "is_blurry":         is_blurry,
            "blur_severity":     severity,
            "quality":           "poor" if composite < 35 else ("fair" if composite < 55 else "good"),
        }
    except Exception as e:
        logger.error(f"Blur detection error: {e}")
        return {"blur_score": 999, "is_blurry": False, "blur_severity": "unknown", "quality": "unknown"}


# ══════════════════════════════════════════════════════════════════════
#  SECTION 2: DEBLURRING & ENHANCEMENT PIPELINE
# ══════════════════════════════════════════════════════════════════════

def _wiener_deconvolution(gray: np.ndarray, psf_size: int = 5,
                           noise_ratio: float = 0.02) -> np.ndarray:
    psf_size   = max(3, psf_size | 1)
    psf        = cv2.getGaussianKernel(psf_size, psf_size / 3.0)
    psf        = psf @ psf.T
    psf       /= psf.sum()
    h, w       = gray.shape
    psf_padded = np.zeros_like(gray, dtype=np.float64)
    ph, pw     = psf.shape
    psf_padded[:ph, :pw] = psf
    psf_padded = np.roll(np.roll(psf_padded, -ph // 2, axis=0), -pw // 2, axis=1)
    Y = np.fft.fft2(gray.astype(np.float64) / 255.0)
    H = np.fft.fft2(psf_padded)
    W = np.conj(H) / (np.abs(H) ** 2 + noise_ratio)
    return np.clip(np.real(np.fft.ifft2(W * Y)) * 255.0, 0, 255).astype(np.uint8)


def _unsharp_mask(img: np.ndarray, strength: float = 1.5, radius: int = 3) -> np.ndarray:
    blurred = cv2.GaussianBlur(img, (radius * 2 + 1, radius * 2 + 1), 0)
    mask    = cv2.subtract(img.astype(np.int16), blurred.astype(np.int16))
    return np.clip(img.astype(np.float32) + strength * mask, 0, 255).astype(np.uint8)


def _apply_clahe(img: np.ndarray, clip: float = 2.5, tile: int = 8) -> np.ndarray:
    lab           = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    lab[:, :, 0]  = cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def _denoise(img: np.ndarray, h: int = 6) -> np.ndarray:
    bgr = cv2.fastNlMeansDenoisingColored(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), None, h, h, 7, 21)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def deblur_and_enhance(content: bytes, severity: str = "moderate") -> tuple:
    img    = Image.open(BytesIO(content)).convert("RGB")
    img_np = np.array(img)
    log    = []

    h, w = img_np.shape[:2]
    if min(h, w) < 1200:
        scale  = 1200 / min(h, w)
        img_np = cv2.resize(img_np, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)
        log.append(f"upscale({img_np.shape[1]}x{img_np.shape[0]})")

    if severity in ("severe", "moderate"):
        img_np = _denoise(img_np, h=8 if severity == "severe" else 5)
        log.append("NLM-denoise")

    if severity != "mild":
        gray            = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        psf             = 9 if severity == "severe" else 5
        noise           = 0.01 if severity == "severe" else 0.025
        restored        = _wiener_deconvolution(gray, psf, noise)
        lab             = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
        lab[:, :, 0]    = restored
        img_np          = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        log.append(f"Wiener(psf={psf})")

    strength = {"severe": 2.2, "moderate": 1.8, "mild": 1.2}.get(severity, 1.8)
    radius   = {"severe": 4,   "moderate": 3,   "mild": 2}.get(severity, 3)
    img_np   = _unsharp_mask(img_np, strength, radius)
    log.append(f"unsharp(s={strength})")

    clip   = {"severe": 3.0, "moderate": 2.5, "mild": 1.8}.get(severity, 2.5)
    img_np = _apply_clahe(img_np, clip)
    log.append(f"CLAHE(clip={clip})")

    kernel = np.array([[0,-0.3,0],[-0.3,2.2,-0.3],[0,-0.3,0]], dtype=np.float32)
    img_np = np.clip(cv2.filter2D(img_np, -1, kernel), 0, 255).astype(np.uint8)
    log.append("sharpen")

    buf = BytesIO()
    Image.fromarray(img_np).save(buf, format="JPEG", quality=92)
    return buf.getvalue(), " -> ".join(log)


def image_to_b64(content: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(content).decode()


# ══════════════════════════════════════════════════════════════════════
#  SECTION 3: OCR QUALITY COMPARISON
# ══════════════════════════════════════════════════════════════════════

def _ocr_quality_score(r: dict) -> float:
    return r.get("word_count", 0) * 0.6 + r.get("avg_confidence", 0) * 100 * 0.4


# ══════════════════════════════════════════════════════════════════════
#  SECTION 4: LABEL CONTENT DETECTION
# ══════════════════════════════════════════════════════════════════════

LABEL_KEYWORDS = [
    'ingredients','nutrition','nutritional','calories','calorie','protein','fat',
    'carbohydrate','carbs','sodium','sugar','sugars','fiber','fibre','serving',
    'cholesterol','saturated','trans','vitamin','calcium','iron','potassium',
    'per 100g','per 100 g','daily value','daily values','amount per','total fat',
    'contains','may contain','preservative','flavour','flavor','colour','color',
    'emulsifier','stabilizer','antioxidant','wheat','milk','soy','salt','water',
    'oil','starch','extract','mg','mcg','kcal','kj','% dv','%dv','g per','per serving',
    'fssai','veg','non-veg','best before','mfg','mrp','net wt','manufactured','packed',
]
FRONT_PACK_SIGNALS = [
    'new','improved','original','classic','natural','organic','premium','delicious',
    'flavoured','variety','crunchy','crispy','fresh','tasty','yummy','light','baked','roasted',
]


def detect_label_presence(ocr_text: str) -> dict:
    if not ocr_text:
        return {"has_label": False, "confidence": "high", "label_hits": [], "front_hits": [], "suggestion": "no_text"}
    low        = ocr_text.lower()
    label_hits = [kw for kw in LABEL_KEYWORDS if kw in low]
    front_hits = [kw for kw in FRONT_PACK_SIGNALS if kw in low]
    ls, fs     = len(label_hits), len(front_hits)

    if ls >= 3:
        return {"has_label": True, "confidence": "high" if ls >= 6 else "medium",
                "label_hits": label_hits[:5], "front_hits": front_hits[:3], "suggestion": None}
    elif ls >= 1 and fs <= 2:
        return {"has_label": True, "confidence": "low", "label_hits": label_hits, "front_hits": front_hits, "suggestion": None}
    elif fs > ls:
        return {"has_label": False, "confidence": "high", "label_hits": label_hits, "front_hits": front_hits[:3], "suggestion": "wrong_side"}
    else:
        return {"has_label": True, "confidence": "low", "label_hits": label_hits, "front_hits": front_hits, "suggestion": "partial"}


# ══════════════════════════════════════════════════════════════════════
#  SECTION 5: OCR
# ══════════════════════════════════════════════════════════════════════

def get_server_ocr(content: bytes, lang_hint: str = "en") -> dict:
    cache_key = f"{hashlib.md5(content).hexdigest()}_{lang_hint}"
    if cache_key in ocr_cache:
        return ocr_cache[cache_key]

    img = Image.open(BytesIO(content)).convert("RGB")
    img.thumbnail((1200, 1200))
    results     = reader.readtext(np.array(img), detail=1)
    words       = [r[1] for r in results]
    confidences = [r[2] for r in results]
    avg_conf    = sum(confidences) / len(confidences) if confidences else 0

    result = {
        "text":           " ".join(words),
        "word_count":     len(words),
        "avg_confidence": round(avg_conf, 3),
        "is_readable":    len(words) >= 3 and avg_conf > 0.15,
    }
    ocr_cache[cache_key] = result
    save_cache(ocr_cache, OCR_CACHE_FILE)
    return result


# ══════════════════════════════════════════════════════════════════════
#  SECTION 6: WEB SEARCH (Serper.dev)
# ══════════════════════════════════════════════════════════════════════

def get_live_search(query: str) -> str:
    if not SERPER_KEY:
        return "No web data available."
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 3},
            timeout=6,
        )
        resp.raise_for_status()
        data    = resp.json()
        results = []
        if data.get("answerBox", {}).get("answer"):
            results.append(data["answerBox"]["answer"])
        for r in data.get("organic", [])[:3]:
            t, s = r.get("title", ""), r.get("snippet", "")
            if t or s:
                results.append(f"{t}: {s}")
        return "\n".join(results) or "No web data available."
    except Exception as e:
        logger.warning(f"Serper error: {e}")
        return "No web data available."


LANGUAGE_MAP = {
    "en": "English",
    "zh": "Simplified Chinese (简体中文)",
    "es": "Spanish (Español)",
    "ar": "Arabic (العربية)",
    "fr": "French (Français)",
    "hi": "Hindi (हिन्दी)",
    "pt": "Portuguese (Português)",
    "de": "German (Deutsch)",
}


# ══════════════════════════════════════════════════════════════════════
#  SECTION 7: LLM PROMPT BUILDER  — Chain-of-Thought, 18-field schema
# ══════════════════════════════════════════════════════════════════════

def build_analysis_prompt(
    extracted_text:   str,
    persona:          str,
    age_group:        str,
    product_category: str,
    language:         str,
    web_context:      str,
    blur_context:     str,
    label_confidence: str,
) -> str:
    lang_name       = LANGUAGE_MAP.get(language, "English")
    persona_ctx     = PERSONA_CONTEXT.get(persona.lower(), PERSONA_CONTEXT["general"])
    confidence_note = (
        "NOTE: Label text may be partially visible. Set is_low_confidence=true."
        if label_confidence == "low" else ""
    )

    return f"""[INST]
You are Eatlytic — an expert nutritional scientist and clinical health auditor.
Analyse the food label text below using 6-step chain-of-thought reasoning.
Complete ALL steps internally, then output ONLY the final JSON.

PERSONA CONTEXT:
{persona_ctx}

INPUTS:
Target Persona     : {persona}
Age Group          : {age_group}
Product Category   : {product_category}
Output Language    : {lang_name}
Label Text         : "{extracted_text}"
Web Research Data  : "{web_context}"
{confidence_note}
{blur_context}

CHAIN-OF-THOUGHT STEPS (reason internally — do NOT output):
Step 1 — IDENTIFY: Determine product name, category, brand from OCR text.
Step 2 — MAP NUTRIENTS: Extract all nutrient values (quantity + unit per serving).
         Compute net carbs if relevant. Cross-check with label's % DV column.
Step 3 — CROSS-REFERENCE: Use Web Research Data to verify allergen warnings,
         recall notices, and ingredient safety flags from regulatory bodies.
Step 4 — PERSONA APPLY: Apply Persona Context. Score each nutrient and additive
         against that persona's specific thresholds and clinical guidelines.
Step 5 — GENERATE WARNINGS: Create health_warnings with severity critical/moderate/low.
         Build allergens list. Build contraindications list.
         Use curiosity-positive language. Never use shame. Use "Worth Knowing /
         Smart Choice / Occasional Treat" style verdicts. Label cons as "Watch Out".
Step 6 — OUTPUT JSON: Produce strictly valid JSON matching the schema below.
         Every text field value MUST be written in {lang_name}.

OUTPUT JSON SCHEMA (return ONLY this JSON, no markdown, no extra text):
{{
  "product_name"            : "Short product name",
  "product_category"        : "Snack | Dairy | Beverage | etc.",
  "score"                   : 7,
  "verdict"                 : "Smart Choice",
  "is_low_confidence"       : false,
  "chart_data"              : [65, 20, 15],
  "summary"                 : "2-sentence summary in {lang_name}.",
  "eli5_explanation"        : "Child-friendly explanation with emojis in {lang_name}.",
  "molecular_insight"       : "Biochemical impact on the body in {lang_name}.",
  "paragraph_benefits"      : "Full paragraph on main benefits in {lang_name}.",
  "paragraph_uniqueness"    : "Unique traits or 2 better alternatives in {lang_name}.",
  "is_unique"               : true,
  "ingredients_list"        : ["Ingredient 1", "Ingredient 2"],
  "health_warnings"         : [
    {{
      "severity"       : "critical",
      "category"       : "Allergen",
      "warning"        : "Warning in {lang_name}.",
      "affected_groups": ["Children", "Pregnant women"]
    }}
  ],
  "allergens"               : ["Milk", "Gluten"],
  "contraindications"       : ["Avoid if on warfarin due to high Vitamin K."],
  "nutrient_breakdown"      : [
    {{"name":"Protein","value":12,"unit":"g","rating":"good",    "impact":"Impact in {lang_name}."}},
    {{"name":"Sugar",  "value":8, "unit":"g","rating":"moderate","impact":"Impact in {lang_name}."}},
    {{"name":"Fat",    "value":5, "unit":"g","rating":"good",    "impact":"Impact in {lang_name}."}},
    {{"name":"Sodium", "value":200,"unit":"mg","rating":"caution","impact":"Impact in {lang_name}."}},
    {{"name":"Fiber",  "value":3, "unit":"g","rating":"good",    "impact":"Impact in {lang_name}."}}
  ],
  "pros"                    : ["Benefit 1 in {lang_name}", "Benefit 2"],
  "cons"                    : ["Watch-out 1 in {lang_name}"],
  "age_warnings"            : [
    {{"group":"Children","emoji":"👶","status":"warning","message":"Warning in {lang_name}."}},
    {{"group":"Adults",  "emoji":"🧑","status":"good",   "message":"Info in {lang_name}."}},
    {{"group":"Seniors", "emoji":"👴","status":"caution","message":"Advice in {lang_name}."}},
    {{"group":"Pregnant","emoji":"🤰","status":"caution","message":"Safety in {lang_name}."}}
  ],
  "daily_limit"             : "Recommended daily limit in {lang_name}.",
  "optimal_timing"          : "Best time to consume and why in {lang_name}.",
  "overconsumption_effects" : "Effects of eating too much in {lang_name}.",
  "dietary_advice"          : "How to include in a balanced diet in {lang_name}.",
  "curiosity_fact"          : "One surprising food-science fact in {lang_name}.",
  "wellness_tip"            : "One practical persona-specific tip in {lang_name}.",
  "ingredients_spotlight"   : [
    {{"name":"Ingredient","role":"What it does","curiosity":"Interesting fact in {lang_name}."}}
  ],
  "better_alternative"      : "Specific healthier product recommendation in {lang_name}."
}}

STRICT RULES:
- chart_data = [Safe%, Moderate%, Risky%] — must sum to exactly 100
- nutrient rating: "good" | "moderate" | "caution" | "bad"
- health_warnings severity: "critical" | "moderate" | "low"
- age_warnings status: "good" | "caution" | "warning"
- score: integer 1–10
- verdict: curiosity-positive, never "Bad" / "Dangerous" / "Avoid"
- ALL text field values MUST be in {lang_name}
[/INST]"""


# ══════════════════════════════════════════════════════════════════════
#  SECTION 8: ASYNC LLM CALL  (P0 fix — asyncio.to_thread)
#
#  The Groq SDK is synchronous. Running it directly in an async route
#  would block the FastAPI event loop, causing crashes at ~20 concurrent
#  users.  asyncio.to_thread() offloads the blocking call to a thread
#  pool, keeping the event loop free.
# ══════════════════════════════════════════════════════════════════════

def _groq_call_sync(prompt: str) -> dict:
    """Synchronous Groq call — always run via asyncio.to_thread."""
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2500,
            response_format={"type": "json_object"},
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as primary_err:
        logger.warning(f"Primary model failed ({primary_err}), trying fallback…")
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2500,
            response_format={"type": "json_object"},
        )
        return json.loads(completion.choices[0].message.content)


async def call_llm(prompt: str) -> dict:
    """Non-blocking LLM wrapper."""
    return await asyncio.to_thread(_groq_call_sync, prompt)


# ══════════════════════════════════════════════════════════════════════
#  SECTION 9: ROUTES
# ══════════════════════════════════════════════════════════════════════

@app.get("/")
async def home():
    return FileResponse("index.html")


# ── /scan-quota — freemium status ────────────────────────────────────

@app.get("/scan-quota")
async def scan_quota(request: Request):
    """
    Returns daily quota status for the calling IP.
    Does NOT consume a scan. Called by frontend on page load.
    """
    ip = get_remote_address(request)
    return check_scan_quota(ip)


# ── /ingredient-info — tap-to-learn ──────────────────────────────────

@app.get("/ingredient-info")
@limiter.limit("30/minute")
async def ingredient_info(
    request:  Request,
    name:     str = "",
    context:  str = "general",
    language: str = "en",
):
    """
    Curiosity-focused ingredient explainer.
    Tap-to-learn from Ingredients Spotlight.
    Does NOT consume freemium quota.
    """
    if not client or not name:
        return JSONResponse({"error": "Missing ingredient name or server config."}, status_code=400)

    lang_name = LANGUAGE_MAP.get(language, "English")
    prompt    = f"""You are a friendly food scientist.
Explain the ingredient "{name}" in a curious, educational, shame-free way.
Dietary context: {context}.
Respond ONLY in {lang_name}.
Return ONLY valid JSON (no markdown):
{{
  "name"        : "{name}",
  "what_it_is"  : "One sentence definition.",
  "why_its_used": "Why manufacturers add it.",
  "body_impact" : "What happens inside the body.",
  "curiosity"   : "One fascinating food-science fact.",
  "verdict"     : "Worth Knowing",
  "tip"         : "One practical consumer tip."
}}"""

    try:
        raw = await call_llm(prompt)
        return JSONResponse(raw)
    except Exception as e:
        logger.error(f"ingredient-info error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ── /search-product — pre-shopping intelligence ───────────────────────

@app.get("/search-product")
@limiter.limit("10/minute")
async def search_product(
    request:  Request,
    q:        str = "",
    language: str = "en",
):
    """
    Pre-shopping product intelligence via web search + LLM.
    Does NOT consume freemium quota.
    """
    if not q:
        return JSONResponse({"error": "Query parameter 'q' is required."}, status_code=400)

    lang_name   = LANGUAGE_MAP.get(language, "English")
    web_context = get_live_search(f"{q} nutritional health review ingredients")

    prompt = f"""You are Eatlytic, an expert food intelligence assistant.
A user is considering buying: "{q}"
Web research: "{web_context}"
Respond ONLY in {lang_name}.
Return ONLY valid JSON (no markdown):
{{
  "product_name"  : "Best guess at product name",
  "summary"       : "2-sentence health overview.",
  "pros"          : ["Pro 1", "Pro 2"],
  "cons"          : ["Watch-out 1"],
  "health_score"  : 6,
  "verdict"       : "Worth Knowing",
  "better_option" : "A healthier specific alternative."
}}"""

    try:
        raw = await call_llm(prompt)
        return JSONResponse(raw)
    except Exception as e:
        logger.error(f"search-product error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ── /check-image & /enhance-preview & /ocr ───────────────────────────

@app.post("/check-image")
@limiter.limit("30/minute")
async def check_image(request: Request, image: UploadFile = File(...)):
    return assess_image_quality(await image.read())


@app.post("/enhance-preview")
@limiter.limit("20/minute")
async def enhance_preview(request: Request, image: UploadFile = File(...)):
    content = await image.read()
    quality = assess_image_quality(content)
    if not quality["is_blurry"]:
        return JSONResponse({"deblurred": False, "message": "Image already clear.", "quality": quality})
    enhanced_bytes, method_log = deblur_and_enhance(content, quality["blur_severity"])
    return JSONResponse({
        "deblurred":      True,
        "image_b64":      image_to_b64(enhanced_bytes),
        "method_log":     method_log,
        "blur_severity":  quality["blur_severity"],
        "quality_before": quality,
    })


@app.post("/ocr")
@limiter.limit("20/minute")
async def perform_ocr(
    request:  Request,
    image:    UploadFile = File(...),
    language: str        = Form("en"),
):
    return get_server_ocr(await image.read(), language)


# ── /analyze — main pipeline ─────────────────────────────────────────

@app.post("/analyze")
@limiter.limit("15/minute")
async def analyze_product(
    request:          Request,
    persona:          str             = Form(...),
    age_group:        str             = Form("adult"),
    product_category: str             = Form("general"),
    language:         str             = Form("en"),
    extracted_text:   Optional[str]   = Form(None),
    image:            UploadFile      = File(...),
):
    """
    Full nutrition-label analysis pipeline.

    Step 0  — Quota check (P0: freemium enforcement)
    Step 1  — Multi-method blur detection
    Step 2  — Conditional deblurring + dual OCR comparison
    Step 3  — OCR extraction
    Step 4  — Label presence detection
    Step 5  — Cache lookup  (cache hit = quota NOT consumed)
    Step 6  — Quota enforcement (after cache, before expensive LLM call)
    Step 7  — Web search for allergen context
    Step 8  — Chain-of-Thought LLM call (P0: async, non-blocking)
    Step 9  — Pydantic validation (P0: catches invalid/hallucinated JSON)
    Step 10 — Quota consumption + metadata attachment
    Step 11 — Cache store + return
    """
    if not client:
        return JSONResponse({"error": "Server Error: Missing GROQ_API_KEY"}, status_code=500)

    ip = get_remote_address(request)

    try:
        content = await image.read()

        # ── Step 0: Blur detection ────────────────────────────────────
        quality   = assess_image_quality(content)
        blur_info = {
            "detected":   quality["is_blurry"],
            "severity":   quality["blur_severity"],
            "score":      quality["blur_score"],
            "deblurred":  False,
            "method_log": None,
            "image_b64":  None,
            "ocr_source": "original",
        }
        working_content = content

        # ── Step 1: Conditional deblurring ───────────────────────────
        if quality["is_blurry"]:
            logger.info(f"Blur detected: severity={quality['blur_severity']}, score={quality['blur_score']}")
            try:
                enhanced_bytes, method_log = deblur_and_enhance(content, quality["blur_severity"])
                ocr_orig     = get_server_ocr(content,        language)
                ocr_enhanced = get_server_ocr(enhanced_bytes, language)

                if _ocr_quality_score(ocr_enhanced) >= _ocr_quality_score(ocr_orig) * 0.85:
                    working_content         = enhanced_bytes
                    blur_info["deblurred"]  = True
                    blur_info["method_log"] = method_log
                    blur_info["image_b64"]  = image_to_b64(enhanced_bytes)
                    blur_info["ocr_source"] = "deblurred"
                    extracted_text          = None  # force re-OCR from enhanced
                    logger.info("Using deblurred image.")
                else:
                    logger.info("Original OCR was better; keeping original.")
            except Exception as e:
                logger.warning(f"Deblurring failed, using original: {e}")

        # ── Step 2: OCR ───────────────────────────────────────────────
        if not extracted_text:
            ocr_result     = get_server_ocr(working_content, language)
            extracted_text = ocr_result["text"]
            ocr_word_count = ocr_result["word_count"]
        else:
            ocr_word_count = len(extracted_text.split())

        if not extracted_text or ocr_word_count == 0:
            return {"error": "no_text",
                    "message": "No text found. Make sure the label side faces the camera.",
                    "tip": "flip_product"}

        # ── Step 3: Label presence check ─────────────────────────────
        label_check = detect_label_presence(extracted_text)
        if not label_check["has_label"]:
            tip = "wrong_side" if label_check.get("suggestion") == "wrong_side" else "flip_product"
            msg = (
                "This looks like the front of the product. Flip it and scan the back label."
                if tip == "wrong_side" else
                "Could not find nutrition information. Please upload a clear photo of the back label."
            )
            return {"error": "no_label", "message": msg, "tip": tip}

        label_confidence = label_check.get("confidence", "medium")

        # ── Step 4: Cache lookup (no quota consumed for cache hits) ───
        cache_key = f"{language}:{persona}:{age_group}:{extracted_text[:80]}"
        if cache_key in ai_cache:
            cached              = dict(ai_cache[cache_key])
            cached["blur_info"] = blur_info
            cached["quota"]     = check_scan_quota(ip)
            return cached

        # ── Step 5: Quota enforcement (after cache, before LLM) ───────
        quota = check_scan_quota(ip)
        if not quota["allowed"]:
            return JSONResponse({
                "error":   "quota_exceeded",
                "message": f"You've used all {quota['limit']} free scans today. Come back tomorrow or upgrade to Pro.",
                "quota":   quota,
            }, status_code=429)

        # ── Step 6: Web search ────────────────────────────────────────
        web_context = get_live_search(
            f"allergen safety health warning {extracted_text[:120]}"
        )

        # ── Step 7: Blur context string for the LLM ──────────────────
        blur_ctx = ""
        if blur_info["detected"]:
            if blur_info["deblurred"]:
                blur_ctx = (
                    f"The image was {blur_info['severity']}ly blurry and enhanced via deblurring. "
                    "OCR text is from the enhanced image. Prioritise nutrients identifiable with confidence."
                )
            else:
                blur_ctx = (
                    f"Image has {blur_info['severity']} blur. "
                    "Where text is ambiguous, infer likely values from domain knowledge."
                )

        # ── Step 8: Build prompt + non-blocking LLM call ─────────────
        prompt = build_analysis_prompt(
            extracted_text=extracted_text,
            persona=persona,
            age_group=age_group,
            product_category=product_category,
            language=language,
            web_context=web_context,
            blur_context=blur_ctx,
            label_confidence=label_confidence,
        )

        raw_result = await call_llm(prompt)

        # ── Step 9: Pydantic validation ───────────────────────────────
        try:
            validated = AnalysisResponse(**raw_result)
            result    = validated.dict()
        except ValidationError as ve:
            logger.warning(f"LLM validation errors (partial recovery): {ve}")
            # Merge valid fields with safe defaults
            safe = AnalysisResponse().dict()
            for key, default_val in safe.items():
                if key in raw_result:
                    safe[key] = raw_result[key]
            result = AnalysisResponse(**safe).dict()

        # ── Step 10: Consume quota + attach metadata ──────────────────
        consume_scan(ip)
        result["blur_info"] = blur_info
        result["quota"]     = check_scan_quota(ip)   # post-consume state

        # ── Step 11: Cache + return ───────────────────────────────────
        ai_cache[cache_key] = result
        save_cache(ai_cache, AI_CACHE_FILE)
        return result

    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {"error": f"Scan failed: {str(e)[:120]}. Please try again."}