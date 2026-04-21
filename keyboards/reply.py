from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Member uchun asosiy menyu."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📋 Vazifalarim"),
        KeyboardButton(text="➕ Yangi vazifa"),
    )
    builder.row(
        KeyboardButton(text="📊 Statistika"),
        KeyboardButton(text="📖 Yordam"),
    )
    return builder.as_markup(resize_keyboard=True)


def admin_menu_kb() -> ReplyKeyboardMarkup:
    """Admin / PM / AD uchun kengaytirilgan menyu."""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📋 Vazifalarim"),
        KeyboardButton(text="📊 Barcha vazifalar"),
    )
    builder.row(
        KeyboardButton(text="➕ Yangi vazifa"),
        KeyboardButton(text="🎬 Loyihalar"),
    )
    builder.row(
        KeyboardButton(text="📊 Statistika"),
        KeyboardButton(text="👥 Jamoa"),
    )
    builder.row(
        KeyboardButton(text="🎙️ Yig'ilish"),
        KeyboardButton(text="📖 Yordam"),
    )
    builder.row(
        KeyboardButton(text="🚀 Nashr paneli"),
        KeyboardButton(text="🗄 Arxiv"),
    )
    builder.row(
        KeyboardButton(text="📋 Shablonlar"),
    )
    return builder.as_markup(resize_keyboard=True)
