from fastapi import APIRouter, HTTPException, Query
from backend.app.services.file_service import FileService
from pydantic import BaseModel
import os

router = APIRouter()
file_service = FileService()  # Root is ~


@router.get("/tree")
async def get_file_tree(path: str = ""):
    try:
        return file_service.list_dir(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/content")
async def get_file_content(path: str = Query(...)):
    try:
        content = file_service.read_file(path)
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class SaveFileRequest(BaseModel):
    path: str
    content: str
    force: bool = False


@router.post("/save")
async def save_file(req: SaveFileRequest):
    try:
        # 统一使用 FileService 的安全写入，避免 files.py 与 file_service 走两套校验。
        return file_service.save_file(req.path, req.content, force=req.force)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
