import os
import tempfile
import aiohttp
import aiofiles
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


async def download_audio(file_url: str) -> str:
    """Telegram dan audio faylni yuklab oladi, vaqtinchalik faylga saqlaydi."""
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            suffix = ".ogg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp_path = tmp.name
                async with aiofiles.open(tmp_path, "wb") as f:
                    await f.write(await resp.read())
    return tmp_path


async def transcribe_audio(file_path: str) -> str:
    """
    Whisper API orqali audio → matnga aylantiradi.
    O'zbek va rus tilini avtomatik taniydi.
    """
    try:
        async with aiofiles.open(file_path, "rb") as f:
            audio_data = await f.read()

        # Vaqtinchalik fayl orqali yuborish
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            transcript = await _get_client().audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=None,       # Avtomatik til aniqlash (uz/ru)
                response_format="text"
            )

        return transcript.strip()

    finally:
        # Vaqtinchalik fayllarni o'chiramiz
        try:
            os.unlink(file_path)
            os.unlink(tmp_path)
        except Exception:
            pass


async def transcribe_from_telegram(bot, file_id: str) -> str:
    """
    Telegram file_id dan to'g'ridan-to'g'ri transkripsiya qiladi.
    """
    file = await bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

    tmp_path = await download_audio(file_url)
    text = await transcribe_audio(tmp_path)

    return text
