import asyncio
import logging
import os
import tempfile
from pathlib import Path

import aiohttp
import aiofiles
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
HEADERS = {"authorization": ASSEMBLYAI_API_KEY}

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_POLL_ATTEMPTS = 60   # 60 × 2s = 2 daqiqa maksimum
POLL_INTERVAL = 2        # sekund


class TranscriptionTimeoutError(Exception):
    pass


async def download_audio(file_url: str) -> str:
    ext = Path(file_url).suffix or ".ogg"
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        async with session.get(file_url) as resp:
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp_path = tmp.name
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(await resp.read())
    return tmp_path


async def _upload_file(file_path: str) -> str:
    async with aiofiles.open(file_path, "rb") as f:
        data = await f.read()
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        async with session.post(
            "https://api.assemblyai.com/v2/upload",
            headers=HEADERS,
            data=data,
        ) as resp:
            resp.raise_for_status()
            result = await resp.json()
            upload_url = result.get("upload_url")
            if not upload_url:
                raise ValueError(f"AssemblyAI upload URL qaytmadi: {result}")
            return upload_url


async def _create_transcript(audio_url: str) -> str:
    payload = {
        "audio_url": audio_url,
        "speech_model": "universal",
        "language_code": "uz",
    }
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        async with session.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=HEADERS,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            result = await resp.json()
            transcript_id = result.get("id")
            if not transcript_id:
                raise ValueError(f"AssemblyAI transcript ID qaytmadi: {result}")
            return transcript_id


async def _poll_transcript(transcript_id: str) -> str:
    url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
    for _ in range(MAX_POLL_ATTEMPTS):
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(url, headers=HEADERS) as resp:
                resp.raise_for_status()
                result = await resp.json()
        status = result.get("status")
        if status == "completed":
            return (result.get("text") or "").strip()
        if status == "error":
            raise Exception(f"AssemblyAI xato: {result.get('error')}")
        await asyncio.sleep(POLL_INTERVAL)

    raise TranscriptionTimeoutError(
        f"Transkriptsiya {MAX_POLL_ATTEMPTS * POLL_INTERVAL} sekundda tugamadi"
    )


async def transcribe_audio(file_path: str) -> str:
    try:
        upload_url = await _upload_file(file_path)
        transcript_id = await _create_transcript(upload_url)
        return await _poll_transcript(transcript_id)
    finally:
        try:
            os.unlink(file_path)
        except OSError:
            pass


async def transcribe_from_telegram(bot, file_id: str) -> str:
    file = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    tmp_path = await download_audio(file_url)
    return await transcribe_audio(tmp_path)
