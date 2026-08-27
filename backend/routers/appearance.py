#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application-owned wallpaper and appearance persistence."""

import base64
import json
import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from config import DATA_DIR

router = APIRouter(tags=["appearance"])

APPEARANCE_FILE = os.path.join(DATA_DIR, "appearance.json")
WALLPAPER_FILE = os.path.join(DATA_DIR, "wallpaper.jpg")
MAX_WALLPAPER_BYTES = 10 * 1024 * 1024

DEFAULTS = {
    "bgOpacity": 0.4,
    "bgBlur": 0,
    "bgBrightness": 1,
    "bgFit": "cover",
    "bgEnabled": False,
    "glassEnabled": False,
}


def _load_settings():
    try:
        with open(APPEARANCE_FILE, encoding="utf-8") as file:
            stored = json.load(file)
        return {**DEFAULTS, **{key: stored[key] for key in DEFAULTS if key in stored}}
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULTS.copy()


def _save_settings(settings):
    os.makedirs(DATA_DIR, exist_ok=True)
    temp_file = APPEARANCE_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(settings, file, ensure_ascii=False, indent=2)
    os.replace(temp_file, APPEARANCE_FILE)


def _image_url():
    if not os.path.isfile(WALLPAPER_FILE):
        return None
    version = os.stat(WALLPAPER_FILE).st_mtime_ns
    return f"/api/appearance/image?v={version}"


@router.get("/appearance")
async def get_appearance():
    return JSONResponse({"settings": _load_settings(), "imageUrl": _image_url()})


@router.get("/appearance/image")
async def get_appearance_image():
    if not os.path.isfile(WALLPAPER_FILE):
        return JSONResponse({"error": "未设置背景图片"}, status_code=404)
    return FileResponse(WALLPAPER_FILE, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.post("/appearance")
async def save_appearance(request: Request):
    try:
        payload = await request.json()
        settings = _load_settings()
        incoming = payload.get("settings", {})
        if not isinstance(incoming, dict):
            raise ValueError("settings 必须为对象")

        for key in ("bgOpacity", "bgBlur", "bgBrightness"):
            if key in incoming:
                settings[key] = float(incoming[key])
        if incoming.get("bgFit") in ("cover", "contain"):
            settings["bgFit"] = incoming["bgFit"]
        for key in ("bgEnabled", "glassEnabled"):
            if key in incoming:
                settings[key] = bool(incoming[key])

        image_data = payload.get("imageData")
        if image_data:
            if not isinstance(image_data, str) or not image_data.startswith("data:image/"):
                raise ValueError("背景图片格式无效")
            encoded = image_data.split(",", 1)[-1]
            raw = base64.b64decode(encoded, validate=True)
            if not raw or len(raw) > MAX_WALLPAPER_BYTES:
                raise ValueError("背景图片必须小于 10MB")
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(WALLPAPER_FILE, "wb") as file:
                file.write(raw)
            settings["bgEnabled"] = True

        if payload.get("clearImage"):
            try:
                os.remove(WALLPAPER_FILE)
            except FileNotFoundError:
                pass
            settings["bgEnabled"] = False

        _save_settings(settings)
        return JSONResponse({"ok": True, "settings": settings, "imageUrl": _image_url()})
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
