from aiogram import Router, types
from aiogram.filters import Command

from app.bot import texts
from app.bot.keyboards import MAIN_KEYBOARD

router = Router(name="help")


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(texts.HELP, reply_markup=MAIN_KEYBOARD, parse_mode="HTML")
