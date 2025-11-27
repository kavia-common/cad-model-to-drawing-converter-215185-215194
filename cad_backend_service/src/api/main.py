import os
import shutil
import uuid
import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr
from starlette.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session as SASession
from sqlalchemy.exc import IntegrityError

import jwt
from jwt import PyJWTError

from passlib.context import CryptContext

# For stubbed conversion
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import ezdxf

# Settings via env
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change")
JWT_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "60"))
STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")] if os.getenv("ALLOWED_ORIGINS") else ["*"]

os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(os.path.join(STORAGE_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_DIR, "outputs"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_DIR, "previews"), exist_ok=True)

# SQLAlchemy setup
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    jobs = relationship("Job", back_populates="user", cascade="all,delete-orphan")


class FileRecord(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    original_filename = Column(String(255), nullable=False)
    stored_path = Column(Text, nullable=False)
    content_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User")
    job = relationship("Job", back_populates="file", uselist=False, cascade="all,delete")


class JobStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default=JobStatus.PENDING, index=True)
    input_format = Column(String(20), nullable=True)
    output_pdf_path = Column(Text, nullable=True)
    output_dxf_path = Column(Text, nullable=True)
    preview_image_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", back_populates="jobs")
    file = relationship("FileRecord", back_populates="job")


def create_all():
    Base.metadata.create_all(bind=engine)

# Pydantic Schemas
class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")

class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")

class UserOut(BaseModel):
    id: int
    email: EmailStr

    class Config:
        from_attributes = True

class UploadResponse(BaseModel):
    file_id: int
    job_id: int
    status: str

class JobOut(BaseModel):
    id: int
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    file_id: int
    input_format: Optional[str] = None
    output_pdf_path: Optional[str] = None
    output_dxf_path: Optional[str] = None
    preview_image_path: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True

# Utility functions
def get_db() -> SASession:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(sub: str) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXPIRE_MIN)
    to_encode = {"sub": sub, "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")


def verify_password(plain_password: str, hashed: str) -> bool:
    return pwd_context.verify(plain_password, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def get_current_user(token: str = Depends(oauth2_scheme), db: SASession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
    except PyJWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == sub).first()
    if not user:
        raise credentials_exception
    return user


# App setup
app = FastAPI(
    title="CAD Backend Service",
    description="API for CAD model to 2D drawing conversion with auth, upload, conversion, jobs, and downloads.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Health", "description": "Service health and metadata"},
        {"name": "Auth", "description": "User registration and authentication"},
        {"name": "Files", "description": "Upload and file handling"},
        {"name": "Jobs", "description": "Conversion job management"},
        {"name": "Downloads", "description": "Secure download endpoints"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# optional session
app.add_middleware(SessionMiddleware, secret_key=JWT_SECRET)

# Create tables on startup
create_all()


# PUBLIC_INTERFACE
@app.get("/", tags=["Health"], summary="Health Check")
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}

# Auth Endpoints
# PUBLIC_INTERFACE
@app.post("/auth/register", response_model=UserOut, tags=["Auth"], summary="Register")
def register(payload: RegisterRequest, db: SASession = Depends(get_db)):
    """Register a new user."""
    u = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(u)
    try:
        db.commit()
        db.refresh(u)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    return u

# PUBLIC_INTERFACE
@app.post("/auth/login", response_model=Token, tags=["Auth"], summary="Login with password (OAuth2)")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: SASession = Depends(get_db)):
    """
    Authenticate user and return JWT.

    Parameters:
    - username: email
    - password: user password
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token(sub=user.email)
    return Token(access_token=token, token_type="bearer")


# Upload and conversion orchestration

ALLOWED_UPLOAD_EXTS = {".step", ".stp", ".iges", ".igs", ".stl"}

def _ext_of(filename: str) -> str:
    _, ext = os.path.splitext(filename.lower())
    return ext

def _safe_store_upload(user_id: int, up: UploadFile) -> str:
    uid = str(uuid.uuid4())
    ext = _ext_of(up.filename)
    filename = f"{user_id}_{uid}{ext}"
    dest = os.path.join(STORAGE_DIR, "uploads", filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(up.file, f)
    return dest

def _make_preview_image(job_id: int, preview_path: str):
    # Generate a simple placeholder preview
    img = Image.new("RGB", (800, 600), color=(245, 247, 250))
    draw = ImageDraw.Draw(img)
    text = f"Preview for Job #{job_id}"
    draw.text((50, 50), text, fill=(0, 0, 0))
    img.save(preview_path, format="PNG")

def _make_pdf(job_id: int, pdf_path: str):
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 16)
    c.drawString(72, height - 72, f"CAD Conversion PDF for Job #{job_id}")
    c.setFont("Helvetica", 12)
    c.drawString(72, height - 100, "This is a stubbed PDF generated by the backend.")
    c.showPage()
    c.save()

def _make_dxf(job_id: int, dxf_path: str):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_text(f"Job {job_id} DXF", dxfattribs={"height": 2.5}).set_pos((0, 0))
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_line((10, 10), (0, 10))
    msp.add_line((0, 10), (0, 0))
    doc.saveas(dxf_path)

def _run_conversion(db_session: SASession, job_id: int):
    job: Job = db_session.query(Job).get(job_id)
    if not job:
        return
    try:
        job.status = JobStatus.PROCESSING
        db_session.commit()

        # Prepare output paths
        base_name = f"job_{job_id}"
        out_pdf = os.path.join(STORAGE_DIR, "outputs", base_name + ".pdf")
        out_dxf = os.path.join(STORAGE_DIR, "outputs", base_name + ".dxf")
        preview = os.path.join(STORAGE_DIR, "previews", base_name + ".png")

        _make_pdf(job_id, out_pdf)
        _make_dxf(job_id, out_dxf)
        _make_preview_image(job_id, preview)

        job.output_pdf_path = out_pdf
        job.output_dxf_path = out_dxf
        job.preview_image_path = preview
        job.status = JobStatus.COMPLETED
        db_session.commit()
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        db_session.commit()

# PUBLIC_INTERFACE
@app.post(
    "/files/upload",
    response_model=UploadResponse,
    tags=["Files"],
    summary="Upload CAD file and create conversion job",
    description="Accepts a CAD model file (STEP/IGES/STL) and starts a background conversion job."
)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CAD model to convert"),
    db: SASession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = _ext_of(file.filename)
    if ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    stored_path = _safe_store_upload(current_user.id, file)
    file_size = os.path.getsize(stored_path)
    fr = FileRecord(
        user_id=current_user.id,
        original_filename=file.filename,
        stored_path=stored_path,
        content_type=file.content_type,
        size_bytes=file_size,
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)

    job = Job(
        user_id=current_user.id,
        file_id=fr.id,
        status=JobStatus.PENDING,
        input_format=ext.replace(".", "").upper(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Launch background conversion
    background_tasks.add_task(_run_conversion, db, job.id)

    return UploadResponse(file_id=fr.id, job_id=job.id, status=job.status)

# Jobs endpoints
# PUBLIC_INTERFACE
@app.get("/jobs", response_model=List[JobOut], tags=["Jobs"], summary="List my jobs")
def list_jobs(db: SASession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List jobs belonging to the authenticated user."""
    jobs = db.query(Job).filter(Job.user_id == current_user.id).order_by(Job.created_at.desc()).all()
    return jobs

# PUBLIC_INTERFACE
@app.get("/jobs/{job_id}", response_model=JobOut, tags=["Jobs"], summary="Get job detail")
def get_job(job_id: int, db: SASession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get detail for a specific job."""
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

# Downloads
def _ensure_job_access(db: SASession, job_id: int, user_id: int) -> Job:
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Job not ready: {job.status}")
    return job

# PUBLIC_INTERFACE
@app.get("/downloads/{job_id}/pdf", tags=["Downloads"], summary="Download PDF result")
def download_pdf(job_id: int, db: SASession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download the generated PDF for the completed job."""
    job = _ensure_job_access(db, job_id, current_user.id)
    if not job.output_pdf_path or not os.path.exists(job.output_pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(job.output_pdf_path, filename=os.path.basename(job.output_pdf_path), media_type="application/pdf")

# PUBLIC_INTERFACE
@app.get("/downloads/{job_id}/dxf", tags=["Downloads"], summary="Download DXF result")
def download_dxf(job_id: int, db: SASession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download the generated DXF for the completed job."""
    job = _ensure_job_access(db, job_id, current_user.id)
    if not job.output_dxf_path or not os.path.exists(job.output_dxf_path):
        raise HTTPException(status_code=404, detail="DXF not found")
    return FileResponse(job.output_dxf_path, filename=os.path.basename(job.output_dxf_path), media_type="application/dxf")

# PUBLIC_INTERFACE
@app.get("/downloads/{job_id}/preview", tags=["Downloads"], summary="Download preview image (PNG)")
def download_preview(job_id: int, db: SASession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Download the generated preview image for the completed job."""
    job = _ensure_job_access(db, job_id, current_user.id)
    if not job.preview_image_path or not os.path.exists(job.preview_image_path):
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(job.preview_image_path, filename=os.path.basename(job.preview_image_path), media_type="image/png")
