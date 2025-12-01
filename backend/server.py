from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import aiofiles
import shutil
import json
import subprocess
import asyncio
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np
import io
import base64

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'photosync_db')]

# Create directories for uploads
UPLOAD_DIR = ROOT_DIR / 'uploads'
PHOTOS_DIR = UPLOAD_DIR / 'photos'
MUSIC_DIR = UPLOAD_DIR / 'music'
EXPORT_DIR = UPLOAD_DIR / 'exports'
THUMBNAILS_DIR = UPLOAD_DIR / 'thumbnails'
PREVIEW_DIR = UPLOAD_DIR / 'previews'

for d in [PHOTOS_DIR, MUSIC_DIR, EXPORT_DIR, THUMBNAILS_DIR, PREVIEW_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Models
class Photo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    original_name: str
    width: int
    height: int
    orientation: str  # 'landscape', 'portrait', 'square'
    duration: float = 2.0  # seconds this photo displays
    order: int = 0
    thumbnail: Optional[str] = None
    preview: Optional[str] = None  # Preview with blurred background

class MusicInfo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    original_name: str
    duration: float  # in seconds
    tempo: float  # BPM
    beats: List[float] = []  # beat times in seconds

class ProjectSettings(BaseModel):
    format: str = "horizontal"  # 'horizontal' or 'vertical'
    resolution: str = "1080p"  # '720p' or '1080p'
    transition: str = "none"  # 'none' or 'fade'
    transition_duration: float = 0.3  # seconds
    global_rhythm_multiplier: float = 1.0  # multiply beat interval
    animation_type: str = "zoom"  # 'zoom', 'pan', 'both'

class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    photos: List[Photo] = []
    music: Optional[MusicInfo] = None
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    export_status: str = "idle"  # 'idle', 'processing', 'completed', 'error'
    export_progress: float = 0.0
    export_file: Optional[str] = None

class PhotoReorderRequest(BaseModel):
    photo_ids: List[str]

class PhotoDurationUpdate(BaseModel):
    photo_id: str
    duration: float

class SettingsUpdate(BaseModel):
    format: Optional[str] = None
    resolution: Optional[str] = None
    transition: Optional[str] = None
    transition_duration: Optional[float] = None
    global_rhythm_multiplier: Optional[float] = None
    animation_type: Optional[str] = None

# Helper functions
def get_orientation(width: int, height: int) -> str:
    ratio = width / height
    if ratio > 1.1:
        return "landscape"
    elif ratio < 0.9:
        return "portrait"
    return "square"

def get_resolution(resolution: str, format: str) -> tuple:
    resolutions = {
        "720p": {"horizontal": (1280, 720), "vertical": (720, 1280)},
        "1080p": {"horizontal": (1920, 1080), "vertical": (1080, 1920)},
    }
    return resolutions.get(resolution, resolutions["1080p"]).get(format, (1920, 1080))

async def create_thumbnail(image_path: Path, thumb_path: Path, size=(200, 200)):
    """Create thumbnail for preview"""
    try:
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if needed
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (0, 0, 0))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85)
        return True
    except Exception as e:
        logging.error(f"Error creating thumbnail: {e}")
        return False

def create_preview_with_blur(image_path: Path, preview_path: Path, target_format: str = "horizontal"):
    """Create preview image with blurred background for different aspect ratios"""
    try:
        # Target sizes for preview (smaller for web)
        target_sizes = {
            "horizontal": (960, 540),  # 16:9
            "vertical": (540, 960),     # 9:16
        }
        target_size = target_sizes.get(target_format, (960, 540))
        
        with Image.open(image_path) as img:
            # Convert to RGB
            if img.mode == 'RGBA':
                bg = Image.new('RGB', img.size, (0, 0, 0))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Create blurred background
            bg = create_blurred_background(img, target_size)
            
            # Fit the image
            fitted = fit_image_to_frame(img, target_size)
            
            # Center the fitted image on the background
            x = (target_size[0] - fitted.width) // 2
            y = (target_size[1] - fitted.height) // 2
            
            bg.paste(fitted, (x, y))
            bg.save(preview_path, "JPEG", quality=85)
        
        return True
    except Exception as e:
        logging.error(f"Error creating preview: {e}")
        return False

def create_blurred_background(img: Image.Image, target_size: tuple) -> Image.Image:
    """Create a blurred background from the image"""
    # Scale image to fill the target size
    img_ratio = img.width / img.height
    target_ratio = target_size[0] / target_size[1]
    
    if img_ratio > target_ratio:
        # Image is wider, scale by height
        new_height = target_size[1]
        new_width = int(new_height * img_ratio)
    else:
        # Image is taller, scale by width
        new_width = target_size[0]
        new_height = int(new_width / img_ratio)
    
    # Resize and center crop
    bg = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Center crop to target size
    left = (new_width - target_size[0]) // 2
    top = (new_height - target_size[1]) // 2
    bg = bg.crop((left, top, left + target_size[0], top + target_size[1]))
    
    # Apply blur
    bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
    
    # Darken slightly
    enhancer = ImageEnhance.Brightness(bg)
    bg = enhancer.enhance(0.5)
    
    return bg

def fit_image_to_frame(img: Image.Image, target_size: tuple) -> Image.Image:
    """Fit image to frame while maintaining aspect ratio"""
    img_ratio = img.width / img.height
    target_ratio = target_size[0] / target_size[1]
    
    if img_ratio > target_ratio:
        # Image is wider, fit by width
        new_width = target_size[0]
        new_height = int(new_width / img_ratio)
    else:
        # Image is taller, fit by height
        new_height = target_size[1]
        new_width = int(new_height * img_ratio)
    
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

def create_frame_with_background(img_path: Path, target_size: tuple) -> Image.Image:
    """Create a frame with the image on a blurred background"""
    with Image.open(img_path) as img:
        # Convert to RGB
        if img.mode == 'RGBA':
            bg_img = Image.new('RGB', img.size, (0, 0, 0))
            bg_img.paste(img, mask=img.split()[3])
            img = bg_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Create blurred background
        bg = create_blurred_background(img, target_size)
        
        # Fit the image
        fitted = fit_image_to_frame(img, target_size)
        
        # Center the fitted image on the background
        x = (target_size[0] - fitted.width) // 2
        y = (target_size[1] - fitted.height) // 2
        
        bg.paste(fitted, (x, y))
        
        return bg

async def analyze_audio(file_path: Path) -> dict:
    """Analyze audio file to extract tempo and beats"""
    try:
        import librosa
        y, sr = librosa.load(str(file_path), sr=22050)
        duration = librosa.get_duration(y=y, sr=sr)
        
        # Get tempo and beats
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        
        # Convert tempo to float if it's an array
        if hasattr(tempo, '__iter__'):
            tempo = float(tempo[0]) if len(tempo) > 0 else 120.0
        else:
            tempo = float(tempo)
        
        return {
            "duration": float(duration),
            "tempo": tempo,
            "beats": beat_times
        }
    except Exception as e:
        logging.error(f"Error analyzing audio: {e}")
        # Return default values if analysis fails
        return {
            "duration": 180.0,
            "tempo": 120.0,
            "beats": []
        }

async def export_video(project_id: str):
    """Export project to MP4 video using imageio"""
    try:
        import imageio.v3 as iio
        import imageio_ffmpeg
        
        # Get ffmpeg path from imageio-ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        logging.info(f"Using FFmpeg from: {ffmpeg_path}")
        
        # Get project from database
        project_data = await db.projects.find_one({"id": project_id})
        if not project_data:
            return
        
        project = Project(**project_data)
        
        # Update status
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {"export_status": "processing", "export_progress": 0.0}}
        )
        
        # Get resolution
        target_size = get_resolution(project.settings.resolution, project.settings.format)
        fps = 30
        
        # Calculate frame counts
        total_photos = len(project.photos)
        if total_photos == 0:
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"export_status": "error"}}
            )
            return
        
        output_file = EXPORT_DIR / f"{project_id}.mp4"
        
        # Collect all frames in memory
        all_frames = []
        
        for photo_idx, photo in enumerate(sorted(project.photos, key=lambda p: p.order)):
            photo_path = PHOTOS_DIR / photo.filename
            if not photo_path.exists():
                continue
            
            # Calculate frames for this photo
            photo_frames = int(photo.duration * fps)
            
            # Create base frame with blurred background
            base_frame = create_frame_with_background(photo_path, target_size)
            
            # Generate frames with Ken Burns effect
            for frame_num in range(photo_frames):
                progress = frame_num / max(photo_frames - 1, 1)
                
                # Ken Burns effect: slight zoom
                zoom_factor = 1.0 + 0.05 * progress
                
                new_width = int(target_size[0] / zoom_factor)
                new_height = int(target_size[1] / zoom_factor)
                
                pan_x = int(10 * progress)
                pan_y = int(5 * progress)
                
                left = (target_size[0] - new_width) // 2 + pan_x
                top = (target_size[1] - new_height) // 2 + pan_y
                
                left = max(0, min(left, target_size[0] - new_width))
                top = max(0, min(top, target_size[1] - new_height))
                
                frame = base_frame.crop((left, top, left + new_width, top + new_height))
                frame = frame.resize(target_size, Image.Resampling.LANCZOS)
                
                # Convert to numpy array for imageio
                frame_array = np.array(frame)
                all_frames.append(frame_array)
            
            # Update progress
            progress_percent = (photo_idx + 1) / total_photos * 80
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"export_progress": progress_percent}}
            )
        
        # Write video using imageio
        logging.info(f"Writing {len(all_frames)} frames to video")
        
        # Write frames to video file
        iio.imwrite(
            str(output_file),
            all_frames,
            fps=fps,
            codec='libx264',
            plugin='pyav'
        )
        
        # If music exists, add it with ffmpeg
        if project.music:
            audio_path = MUSIC_DIR / project.music.filename
            if audio_path.exists():
                output_with_audio = EXPORT_DIR / f"{project_id}_audio.mp4"
                cmd = [
                    ffmpeg_path, "-y",
                    "-i", str(output_file),
                    "-i", str(audio_path),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(output_with_audio)
                ]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                if output_with_audio.exists():
                    output_file.unlink()
                    output_with_audio.rename(output_file)
        
        if output_file.exists() and output_file.stat().st_size > 0:
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {
                    "export_status": "completed",
                    "export_progress": 100.0,
                    "export_file": str(output_file.name)
                }}
            )
            logging.info(f"Export completed: {output_file}")
        else:
            logging.error("Export failed - file not created")
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"export_status": "error"}}
            )
    
    except Exception as e:
        logging.error(f"Export error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {"export_status": "error"}}
        )
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {"export_status": "error"}}
        )

# API Routes
@api_router.get("/")
async def root():
    return {"message": "PhotoSync Video Creator API"}

@api_router.post("/projects", response_model=Project)
async def create_project():
    """Create a new project"""
    project = Project()
    doc = project.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.projects.insert_one(doc)
    return project

@api_router.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str):
    """Get project by ID"""
    project_data = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(project_data.get('created_at'), str):
        project_data['created_at'] = datetime.fromisoformat(project_data['created_at'])
    return Project(**project_data)

@api_router.post("/projects/{project_id}/photos")
async def upload_photos(project_id: str, files: List[UploadFile] = File(...)):
    """Upload photos to a project"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    uploaded_photos = []
    current_order = len(project_data.get('photos', []))
    current_format = project_data.get('settings', {}).get('format', 'horizontal')
    
    for file in files:
        # Generate unique filename
        ext = Path(file.filename).suffix.lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']:
            continue
        
        photo_id = str(uuid.uuid4())
        filename = f"{photo_id}{ext}"
        file_path = PHOTOS_DIR / filename
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Get image dimensions
        with Image.open(file_path) as img:
            width, height = img.size
        
        # Create thumbnail
        thumb_filename = f"{photo_id}_thumb.jpg"
        thumb_path = THUMBNAILS_DIR / thumb_filename
        await create_thumbnail(file_path, thumb_path)
        
        # Create preview with blurred background
        preview_filename = f"{photo_id}_preview_{current_format}.jpg"
        preview_path = PREVIEW_DIR / preview_filename
        create_preview_with_blur(file_path, preview_path, current_format)
        
        # Create photo object
        photo = Photo(
            id=photo_id,
            filename=filename,
            original_name=file.filename,
            width=width,
            height=height,
            orientation=get_orientation(width, height),
            order=current_order,
            thumbnail=thumb_filename,
            preview=preview_filename
        )
        
        uploaded_photos.append(photo.model_dump())
        current_order += 1
    
    # Update project
    await db.projects.update_one(
        {"id": project_id},
        {"$push": {"photos": {"$each": uploaded_photos}}}
    )
    
    return {"uploaded": len(uploaded_photos), "photos": uploaded_photos}

@api_router.post("/projects/{project_id}/music")
async def upload_music(project_id: str, file: UploadFile = File(...)):
    """Upload music file to a project"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate file type
    ext = Path(file.filename).suffix.lower()
    if ext not in ['.mp3']:
        raise HTTPException(status_code=400, detail="Only MP3 files are supported")
    
    # Generate unique filename
    music_id = str(uuid.uuid4())
    filename = f"{music_id}{ext}"
    file_path = MUSIC_DIR / filename
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Analyze audio
    audio_info = await analyze_audio(file_path)
    
    # Create music info
    music = MusicInfo(
        id=music_id,
        filename=filename,
        original_name=file.filename,
        duration=audio_info["duration"],
        tempo=audio_info["tempo"],
        beats=audio_info["beats"]
    )
    
    # Update project
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"music": music.model_dump()}}
    )
    
    return music

@api_router.post("/projects/{project_id}/sync-to-beats")
async def sync_photos_to_beats(project_id: str):
    """Sync photo durations to music beats"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = Project(**project_data)
    
    if not project.music:
        raise HTTPException(status_code=400, detail="No music uploaded")
    
    photos = sorted(project.photos, key=lambda p: p.order)
    multiplier = project.settings.global_rhythm_multiplier
    
    if len(photos) == 0:
        return {"synced": False}
    
    # Calculate beat interval from tempo
    beat_interval = 60.0 / project.music.tempo * multiplier
    
    # Assign durations based on beats
    updated_photos = []
    for i, photo in enumerate(photos):
        photo_dict = photo.model_dump()
        photo_dict['duration'] = beat_interval
        updated_photos.append(photo_dict)
    
    # Update project
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"photos": updated_photos}}
    )
    
    return {"synced": True, "beat_interval": beat_interval}

@api_router.put("/projects/{project_id}/photos/reorder")
async def reorder_photos(project_id: str, request: PhotoReorderRequest):
    """Reorder photos in a project"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Create order map
    order_map = {pid: idx for idx, pid in enumerate(request.photo_ids)}
    
    # Update photo orders
    photos = project_data.get('photos', [])
    for photo in photos:
        if photo['id'] in order_map:
            photo['order'] = order_map[photo['id']]
    
    # Sort and update
    photos.sort(key=lambda p: p.get('order', 0))
    
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"photos": photos}}
    )
    
    return {"reordered": True}

@api_router.put("/projects/{project_id}/photos/duration")
async def update_photo_duration(project_id: str, update: PhotoDurationUpdate):
    """Update duration for a specific photo"""
    await db.projects.update_one(
        {"id": project_id, "photos.id": update.photo_id},
        {"$set": {"photos.$.duration": update.duration}}
    )
    return {"updated": True}

class AllPhotosDurationUpdate(BaseModel):
    duration: float

@api_router.put("/projects/{project_id}/photos/duration/all")
async def update_all_photos_duration(project_id: str, update: AllPhotosDurationUpdate):
    """Update duration for all photos in the project"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    photos = project_data.get('photos', [])
    for photo in photos:
        photo['duration'] = update.duration
    
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"photos": photos}}
    )
    return {"updated": True, "count": len(photos)}

@api_router.delete("/projects/{project_id}/photos/{photo_id}")
async def delete_photo(project_id: str, photo_id: str):
    """Delete a photo from the project"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Find and remove photo
    photos = project_data.get('photos', [])
    photo_to_delete = None
    for photo in photos:
        if photo['id'] == photo_id:
            photo_to_delete = photo
            break
    
    if photo_to_delete:
        # Delete files safely
        try:
            photo_path = PHOTOS_DIR / photo_to_delete['filename']
            if photo_path.exists():
                photo_path.unlink()
        except Exception as e:
            logging.error(f"Error deleting photo file: {e}")
        
        thumb_name = photo_to_delete.get('thumbnail')
        if thumb_name:
            try:
                thumb_path = THUMBNAILS_DIR / thumb_name
                if thumb_path.exists():
                    thumb_path.unlink()
            except Exception as e:
                logging.error(f"Error deleting thumbnail: {e}")
        
        preview_name = photo_to_delete.get('preview')
        if preview_name:
            try:
                preview_path = PREVIEW_DIR / preview_name
                if preview_path.exists():
                    preview_path.unlink()
            except Exception as e:
                logging.error(f"Error deleting preview: {e}")
        
        # Remove from list
        await db.projects.update_one(
            {"id": project_id},
            {"$pull": {"photos": {"id": photo_id}}}
        )
    
    return {"deleted": True}

@api_router.put("/projects/{project_id}/settings")
async def update_settings(project_id: str, settings: SettingsUpdate):
    """Update project settings"""
    update_data = {k: v for k, v in settings.model_dump().items() if v is not None}
    
    # If format changed, regenerate previews
    if 'format' in update_data:
        project_data = await db.projects.find_one({"id": project_id})
        if project_data:
            new_format = update_data['format']
            photos = project_data.get('photos', [])
            updated_photos = []
            
            for photo in photos:
                photo_path = PHOTOS_DIR / photo['filename']
                if photo_path.exists():
                    # Create new preview with new format
                    preview_filename = f"{photo['id']}_preview_{new_format}.jpg"
                    preview_path = PREVIEW_DIR / preview_filename
                    create_preview_with_blur(photo_path, preview_path, new_format)
                    photo['preview'] = preview_filename
                updated_photos.append(photo)
            
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"photos": updated_photos}}
            )
    
    if update_data:
        update_fields = {f"settings.{k}": v for k, v in update_data.items()}
        await db.projects.update_one(
            {"id": project_id},
            {"$set": update_fields}
        )
    return {"updated": True}

@api_router.post("/projects/{project_id}/export")
async def start_export(project_id: str, background_tasks: BackgroundTasks):
    """Start video export"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Reset export status
    await db.projects.update_one(
        {"id": project_id},
        {"$set": {"export_status": "processing", "export_progress": 0, "export_file": None}}
    )
    
    # Add export task to background
    background_tasks.add_task(export_video, project_id)
    
    return {"status": "started"}

@api_router.get("/projects/{project_id}/export/status")
async def get_export_status(project_id: str):
    """Get export status"""
    project_data = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {
        "status": project_data.get("export_status", "idle"),
        "progress": project_data.get("export_progress", 0),
        "file": project_data.get("export_file")
    }

@api_router.get("/projects/{project_id}/export/download")
async def download_export(project_id: str):
    """Download exported video"""
    project_data = await db.projects.find_one({"id": project_id})
    if not project_data:
        raise HTTPException(status_code=404, detail="Project not found")
    
    export_file = project_data.get("export_file")
    if not export_file:
        raise HTTPException(status_code=404, detail="No export available")
    
    file_path = EXPORT_DIR / export_file
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    
    return FileResponse(
        path=str(file_path),
        filename="photosync_video.mp4",
        media_type="video/mp4",
        headers={
            "Content-Disposition": "attachment; filename=photosync_video.mp4",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@api_router.get("/photos/{filename}")
async def get_photo(filename: str):
    """Serve photo file"""
    file_path = PHOTOS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    
    return FileResponse(path=str(file_path))

@api_router.get("/thumbnails/{filename}")
async def get_thumbnail(filename: str):
    """Serve thumbnail file"""
    file_path = THUMBNAILS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    return FileResponse(path=str(file_path))

@api_router.get("/previews/{filename}")
async def get_preview(filename: str):
    """Serve preview file with blurred background"""
    file_path = PREVIEW_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    
    return FileResponse(path=str(file_path))

@api_router.get("/music/{filename}")
async def get_music(filename: str):
    """Serve music file"""
    file_path = MUSIC_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Music not found")
    
    return FileResponse(path=str(file_path), media_type="audio/mpeg")

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
