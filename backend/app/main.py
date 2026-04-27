from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.rules import router as rules_router
from app.routes.validate import router as validate_router

app = FastAPI(title="Tawthiq API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://tawthiq-frontend-273154047321.us-central1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rules_router)
app.include_router(validate_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
