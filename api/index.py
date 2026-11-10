import os
import time

import requests
from fastapi import FastAPI, APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()
router = APIRouter()

SB_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SB_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
CACHE_SECONDS = 300
_cache = {"t": 0, "data": None}


# Vercel entrega /api/index?path=... ; aquí se restaura la ruta original.
@app.middleware("http")
async def restore_original_path(request: Request, call_next):
    original = request.query_params.get("path")
    if request.url.path in ("/api/index", "/api/index/") and original is not None:
        request.scope["path"] = "/api/" + original.lstrip("/")
    return await call_next(request)


# ---------- Datos de respaldo (se usan si la base de datos está vacía) ----------
STORES = [
    {"id": "pns-clarence", "chain": "pns", "name": "Pak'nSave Clarence St"},
    {"id": "pns-mill", "chain": "pns", "name": "Pak'nSave Mill St"},
    {"id": "nw-hillcrest", "chain": "nw", "name": "New World Hillcrest"},
    {"id": "nw-te-rapa", "chain": "nw", "name": "New World Te Rapa"},
    {"id": "nw-glenview", "chain": "nw", "name": "New World Glenview"},
    {"id": "nw-rototuna", "chain": "nw", "name": "New World Rototuna"},
    {"id": "ww-chartwell", "chain": "ww", "name": "Woolworths Chartwell"},
    {"id": "ww-cbd", "chain": "ww", "name": "Woolworths Hamilton CBD"},
    {"id": "ww-te-rapa", "chain": "ww", "name": "Woolworths Te Rapa"},
    {"id": "ww-st-james", "chain": "ww", "name": "Woolworths St James"},
]
RAW = [
    ("p01", "9400000000001", "Anchor Milk 2L", "Anchor", "Milk", 4.19),
    ("p02", "9400000000002", "Pams Eggs 12pk", "Pams", "Eggs", 6.99),
    ("p03", "9400000000003", "Anchor Butter 500g", "Anchor", "Butter", 8.99),
    ("p04", "9400000000004", "Pams White Bread 700g", "Pams", "Bread", 2.29),
    ("p05", "9400000000005", "Vogel's Original Mixed Grain 700g", "Vogel's", "Bread", 5.49),
    ("p06", "9400000000006", "Whittaker's Creamy Milk Chocolate 250g", "Whittaker's", "Chocolate", 5.99),
    ("p07", "9400000000007", "Whittaker's Dark Ghana 250g", "Whittaker's", "Chocolate", 5.99),
    ("p08", "9400000000008", "Pams Tasty Cheese 1kg", "Pams", "Cheese", 12.99),
    ("p09", "9400000000009", "Pams Long Grain Rice 1kg", "Pams", "Pantry", 2.99),
    ("p10", "9400000000010", "Pams Baked Beans 420g", "Pams", "Pantry", 1.29),
    ("p11", "9400000000011", "Coca-Cola 1.5L", "Coca-Cola", "Drinks", 3.79),
    ("p12", "9400000000012", "Pams Toilet Paper 12pk", "Pams", "Household", 7.99),
    ("p13", "9400000000013", "Pams Frozen Peas 1kg", "Pams", "Frozen", 3.49),
    ("p14", "9400000000014", "Anchor Blue Top Milk 1L", "Anchor", "Milk", 2.39),
]
FACTOR = {"pns": 1.0, "ww": 1.07, "nw": 1.12}


def demo_price(base, sid, name):
    f = FACTOR[sid.split("-")[0]] + (sum(map(ord, sid)) % 5) * 0.01
    f += ((len(name) + ord(sid[-1])) % 7) * 0.012 - 0.03
    return round(base * f, 2)


SAMPLE = [
    {"id": i, "barcode": b, "name": n, "brand": br, "category": c, "image": "",
     "prices": {s["id"]: demo_price(base, s["id"], n) for s in STORES}}
    for (i, b, n, br, c, base) in RAW
]


# ---------- Lectura desde Supabase ----------
def sb_get(table):
    headers = {"apikey": SB_KEY, "Range-Unit": "items"}
    if SB_KEY.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + SB_KEY
    rows, start = [], 0
    while True:
        h = {**headers, "Range": f"{start}-{start + 999}"}
        r = requests.get(f"{SB_URL}/rest/v1/{table}", params={"select": "*"}, headers=h, timeout=8)
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < 1000:
            return rows
        start += 1000


def load():
    if _cache["data"] and time.time() - _cache["t"] < CACHE_SECONDS:
        return _cache["data"]
    data = {"stores": STORES, "catalog": SAMPLE, "source": "demo", "error": None, "in_db": 0}
    if SB_URL and SB_KEY:
        try:
            stores, prods, prices = sb_get("stores"), sb_get("products"), sb_get("prices")
            data["in_db"] = len(prods)
            by = {p["id"]: {**p, "prices": {}} for p in prods}
            for pr in prices:
                if pr["product_id"] in by:
                    by[pr["product_id"]]["prices"][pr["store_id"]] = float(pr["price"])
            catalog = [p for p in by.values() if p["prices"]]
            if stores and catalog:
                data.update(stores=stores, catalog=catalog, source="database")
        except Exception as e:
            data["error"] = type(e).__name__
    _cache.update(t=time.time(), data=data)
    return data


class Item(BaseModel):
    name: str
    id: Optional[str] = None
    quantity: int = 1


class CompareIn(BaseModel):
    items: List[Item]
    stores: Optional[List[str]] = None


def find(it, catalog):
    if it.id:
        for p in catalog:
            if p["id"] == it.id:
                return p
    n = it.name.lower().strip()
    for p in catalog:
        if n and n in p["name"].lower():
            return p
    words = n.split()
    for p in catalog:
        if words and all(w in p["name"].lower() for w in words):
            return p
    return None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/status")
def status():
    d = load()
    return {"source": d["source"], "configured": bool(SB_URL and SB_KEY),
            "products_in_db": d["in_db"], "stores": len(d["stores"]), "error": d["error"]}


@router.get("/stores")
def stores():
    return load()["stores"]


@router.get("/products")
def products(q: str = "", category: str = ""):
    out = load()["catalog"]
    if q:
        out = [p for p in out if q.lower() in ((p["name"] or "") + " " + (p.get("brand") or "")).lower()]
    if category:
        out = [p for p in out if (p.get("category") or "").lower() == category.lower()]
    return out


@router.get("/barcode/{code}")
def by_barcode(code: str):
    for p in load()["catalog"]:
        if p.get("barcode") == code:
            return p
    return {"error": "not_found"}


@router.post("/compare")
def compare(body: CompareIn):
    d = load()
    all_stores = d["stores"]
    by_id = {s["id"]: s for s in all_stores}
    chosen = [s for s in all_stores if not body.stores or s["id"] in body.stores] or all_stores
    ids = [s["id"] for s in chosen]
    demo = d["source"] == "demo"

    matched, missing = [], []
    for it in body.items:
        p = find(it, d["catalog"])
        if p and any(i in p["prices"] for i in ids):
            matched.append((p, max(1, it.quantity)))
        else:
            missing.append(it.name)
    if not matched:
        return {"missing": missing, "option1": None, "option2": None, "demo": demo}

    def line(p, q, sid):
        u = p["prices"][sid]
        return {"name": p["name"], "qty": q, "unit": u, "cost": round(u * q, 2)}

    # Opción 1: cada producto donde sale más barato
    stops = {}
    for p, q in matched:
        sid = min((i for i in ids if i in p["prices"]), key=lambda i: p["prices"][i])
        st = stops.setdefault(sid, {"store": by_id[sid], "items": [], "subtotal": 0.0})
        st["items"].append(line(p, q, sid))
        st["subtotal"] = round(st["subtotal"] + p["prices"][sid] * q, 2)
    split_total = round(sum(s["subtotal"] for s in stops.values()), 2)

    # Opción 2: una sola tienda (la que cubre más productos y sale más barata)
    cover = {i: [(p, q) for p, q in matched if i in p["prices"]] for i in ids}
    top = max(len(v) for v in cover.values())
    totals = {i: round(sum(p["prices"][i] * q for p, q in cover[i]), 2) for i in ids}
    cands = [i for i in ids if len(cover[i]) == top]
    best = min(cands, key=lambda i: totals[i])
    full = top == len(matched)
    priciest = max(totals[i] for i in cands)

    return {
        "missing": missing, "demo": demo,
        "option1": {"stops": list(stops.values()), "total": split_total,
                    "saving": round(max(0, priciest - split_total), 2) if full else 0},
        "option2": {"store": by_id[best], "items": [line(p, q, best) for p, q in cover[best]],
                    "total": totals[best], "saving": round(priciest - totals[best], 2) if full else 0,
                    "unavailable": [p["name"] for p, q in matched if best not in p["prices"]]},
    }


@router.post("/sync")
def sync():
    _cache["data"] = None  # fuerza a leer otra vez de la base de datos
    return {"status": "synced"}


app.include_router(router, prefix="/api")
