from fastapi import FastAPI, APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()
router = APIRouter()


# Vercel entrega /api/index?path=... ; aquí se restaura la ruta original.
@app.middleware("http")
async def restore_original_path(request: Request, call_next):
    original = request.query_params.get("path")
    if request.url.path in ("/api/index", "/api/index/") and original is not None:
        request.scope["path"] = "/api/" + original.lstrip("/")
    return await call_next(request)


# ---- Supermercados de Hamilton: agrega o quita sucursales aquí ----
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

# (id, código de barras, nombre, marca, categoría, precio base, foto opcional)
RAW = [
    ("p01", "9400000000001", "Anchor Milk 2L", "Anchor", "Milk", 4.19, ""),
    ("p02", "9400000000002", "Pams Eggs 12pk", "Pams", "Eggs", 6.99, ""),
    ("p03", "9400000000003", "Anchor Butter 500g", "Anchor", "Butter", 8.99, ""),
    ("p04", "9400000000004", "Pams White Bread 700g", "Pams", "Bread", 2.29, ""),
    ("p05", "9400000000005", "Vogel's Original Mixed Grain 700g", "Vogel's", "Bread", 5.49, ""),
    ("p06", "9400000000006", "Whittaker's Creamy Milk Chocolate 250g", "Whittaker's", "Chocolate", 5.99, ""),
    ("p07", "9400000000007", "Whittaker's Dark Ghana 250g", "Whittaker's", "Chocolate", 5.99, ""),
    ("p08", "9400000000008", "Pams Tasty Cheese 1kg", "Pams", "Cheese", 12.99, ""),
    ("p09", "9400000000009", "Pams Long Grain Rice 1kg", "Pams", "Pantry", 2.99, ""),
    ("p10", "9400000000010", "Pams Baked Beans 420g", "Pams", "Pantry", 1.29, ""),
    ("p11", "9400000000011", "Coca-Cola 1.5L", "Coca-Cola", "Drinks", 3.79, ""),
    ("p12", "9400000000012", "Pams Toilet Paper 12pk", "Pams", "Household", 7.99, ""),
    ("p13", "9400000000013", "Pams Frozen Peas 1kg", "Pams", "Frozen", 3.49, ""),
    ("p14", "9400000000014", "Anchor Blue Top Milk 1L", "Anchor", "Milk", 2.39, ""),
]
FACTOR = {"pns": 1.0, "ww": 1.07, "nw": 1.12}


def demo_price(base, sid, name):
    f = FACTOR[sid.split("-")[0]] + (sum(map(ord, sid)) % 5) * 0.01
    f += ((len(name) + ord(sid[-1])) % 7) * 0.012 - 0.03
    return round(base * f, 2)


# PRECIOS DE EJEMPLO: se reemplazan cuando conectemos los precios reales.
CATALOG = [
    {"id": i, "barcode": b, "name": n, "brand": br, "category": c, "image": img,
     "prices": {s["id"]: demo_price(base, s["id"], n) for s in STORES}}
    for (i, b, n, br, c, base, img) in RAW
]


class Item(BaseModel):
    name: str
    id: Optional[str] = None
    quantity: int = 1


class CompareIn(BaseModel):
    items: List[Item]
    stores: Optional[List[str]] = None


def find(it):
    if it.id:
        for p in CATALOG:
            if p["id"] == it.id:
                return p
    n = it.name.lower().strip()
    for p in CATALOG:
        if n and n in p["name"].lower():
            return p
    words = n.split()
    for p in CATALOG:
        if words and all(w in p["name"].lower() for w in words):
            return p
    return None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/stores")
def stores():
    return STORES


@router.get("/products")
def products(q: str = "", category: str = ""):
    out = CATALOG
    if q:
        out = [p for p in out if q.lower() in (p["name"] + " " + p["brand"]).lower()]
    if category:
        out = [p for p in out if p["category"].lower() == category.lower()]
    return out


@router.get("/barcode/{code}")
def by_barcode(code: str):
    for p in CATALOG:
        if p["barcode"] == code:
            return p
    return {"error": "not_found"}


@router.post("/compare")
def compare(body: CompareIn):
    chosen = [s for s in STORES if not body.stores or s["id"] in body.stores] or STORES
    matched, missing = [], []
    for it in body.items:
        p = find(it)
        if p:
            matched.append((p, max(1, it.quantity)))
        else:
            missing.append(it.name)
    if not matched:
        return {"missing": missing, "option1": None, "option2": None}

    def line(p, q, sid):
        u = p["prices"][sid]
        return {"name": p["name"], "qty": q, "unit": u, "cost": round(u * q, 2)}

    # Opción 1: cada producto donde sale más barato
    stops = {}
    for p, q in matched:
        s = min(chosen, key=lambda s: p["prices"][s["id"]])
        st = stops.setdefault(s["id"], {"store": s, "items": [], "subtotal": 0.0})
        st["items"].append(line(p, q, s["id"]))
        st["subtotal"] = round(st["subtotal"] + p["prices"][s["id"]] * q, 2)
    split_total = round(sum(s["subtotal"] for s in stops.values()), 2)

    # Opción 2: una sola tienda donde toda la lista sale más barata
    totals = {s["id"]: round(sum(p["prices"][s["id"]] * q for p, q in matched), 2) for s in chosen}
    best = min(chosen, key=lambda s: totals[s["id"]])
    priciest = max(totals.values())

    return {
        "missing": missing,
        "option1": {"stops": list(stops.values()), "total": split_total,
                    "saving": round(priciest - split_total, 2)},
        "option2": {"store": best, "items": [line(p, q, best["id"]) for p, q in matched],
                    "total": totals[best["id"]], "saving": round(priciest - totals[best["id"]], 2)},
    }


@router.post("/sync")
def sync():
    # Aquí irá la actualización automática de precios
    return {"status": "synced"}


app.include_router(router, prefix="/api")
