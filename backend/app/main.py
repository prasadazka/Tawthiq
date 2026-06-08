from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.pdf_tables import router as pdf_tables_router
from app.routes.rules import router as rules_router
from app.routes.validate import router as validate_router
from app.routes.xbrl_india import router as xbrl_india_router
from app.routes.xbrl_saudi import router as xbrl_saudi_router

app = FastAPI(title="Tawthiq API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://tawthiq-frontend-pn5c6ojp4a-uc.a.run.app",
        "https://tawthiq-frontend-273154047321.us-central1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rules_router)
app.include_router(validate_router)
app.include_router(xbrl_india_router)
app.include_router(pdf_tables_router)
app.include_router(xbrl_saudi_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
