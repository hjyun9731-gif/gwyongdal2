from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .db import SessionLocal, get_db
from .api.driver import router as driver_router
from .api.admin import router as admin_router
from .api.deps import current_driver, current_admin
from .models import Member, AdminUser
from .services.bootstrap import ensure_seed_data
from .services.legal_form import build_legal_form

STATIC=Path(__file__).parent/'static'

@asynccontextmanager
async def lifespan(app:FastAPI):
    db=SessionLocal()
    try: ensure_seed_data(db)
    finally: db.close()
    yield

app=FastAPI(title='운수종사자 일상점검',version='2.0-phase1',lifespan=lifespan)
app.include_router(driver_router);app.include_router(admin_router)
app.mount('/static',StaticFiles(directory=STATIC),name='static')

@app.get('/health')
def health():return {'ok':True}

@app.get('/',include_in_schema=False)
def driver_page():return FileResponse(STATIC/'driver.html')
@app.get('/admin',include_in_schema=False)
def admin_page():return FileResponse(STATIC/'admin.html')
@app.get('/manifest.webmanifest',include_in_schema=False)
def manifest():return FileResponse(STATIC/'manifest.webmanifest',media_type='application/manifest+json')
@app.get('/sw.js',include_in_schema=False)
def sw():return FileResponse(STATIC/'sw.js',media_type='application/javascript')

@app.get('/print/legal-form',response_class=HTMLResponse,include_in_schema=False)
def print_driver(month:str,db:Session=Depends(get_db),member:Member=Depends(current_driver)):
    try:return HTMLResponse(build_legal_form(db,member.id,month))
    except ValueError:raise HTTPException(404,detail='NOT_FOUND')

@app.get('/print/admin/legal-form/{member_id}',response_class=HTMLResponse,include_in_schema=False)
def print_admin(member_id:int,month:str,db:Session=Depends(get_db),admin:AdminUser=Depends(current_admin)):
    try:return HTMLResponse(build_legal_form(db,member_id,month))
    except ValueError:raise HTTPException(404,detail='NOT_FOUND')
