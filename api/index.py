
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
 
app = FastAPI()
router = APIRouter()
 
# Catálogo de ejemplo (luego lo reemplazas por datos reales)
CATALOG = [
    {"barcode": "9400000000001", "name": "Anchor Milk 2L", "category": "Milk",
     "prices": {"Pak'nSave": 4.19, "Woolworths": 4.50, "New World": 4.69}},
    {"barcode": "9400000000002", "name": "Pams Eggs 12pk", "category": "Eggs",
     "prices": {"Pak'nSave": 6.99, "Woolworths": 7.20, "New World": 7.49}},
]
 
 
class Item(BaseModel):
    name: str
    quantity: int = 1
    format: Optional[str] = "Individual"
    notes: Optional[str] = ""
 
 
@router.get("/health")
def health():
    return {"status": "ok"}
 
 
@router.get("/products")
def products(q: str = "", category: str = ""):
    results = CATALOG
    if q:
        results = [p for p in results if q.lower() in p["name"].lower()]
    if category:
        results = [p for p in results if p["category"].lower() == category.lower()]
    return results
 
 
@router.get("/barcode/{code}")
def by_barcode(code: str):
    for p in CATALOG:
        if p["barcode"] == code:
            cheapest = min(p["prices"], key=p["prices"].get)
            return {**p, "cheapest_store": cheapest}
    return {"error": "not_found"}
 
 
@router.post("/compare")
def compare(items: List[Item]):
    stores = ["Pak'nSave", "Woolworths", "New World"]
    totals = {s: 0.0 for s in stores}
    split_plan, split_total = [], 0.0
 
    for it in items:
        match = next((p for p in CATALOG if it.name.lower() in p["name"].lower()), None)
        if not match:
            continue
        for s in stores:
            totals[s] += match["prices"][s] * it.quantity
        best = min(match["prices"], key=match["prices"].get)
        cost = match["prices"][best] * it.quantity
        split_total += cost
        split_plan.append({"item": match["name"], "store": best, "cost": round(cost, 2)})
 
    best_single = min(totals, key=totals.get)
    return {
        "option1_max_savings": {"plan": split_plan, "total": round(split_total, 2)},
        "option2_single_store": {"store": best_single, "total": round(totals[best_single], 2)},
    }
 
 
@router.post("/sync")
def sync():
    # Aquí irá la lógica de actualización de precios
    return {"status": "synced"}
 
 
# Las mismas rutas con y sin el prefijo /api, para que funcione
# sin importar cómo Vercel le pase la dirección a FastAPI.
app.include_router(router, prefix="/api")
app.include_router(router)
 
 
# Diagnóstico temporal: muestra qué ruta recibió el servidor
@app.api_route("/{full_path:path}", methods=["GET", "POST"])
def not_found(full_path: str, request: Request):
    return JSONResponse(
        {"detail": "Not Found", "seen_path": request.url.path},
        status_code=404,
    )
 
