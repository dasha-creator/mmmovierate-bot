from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from datetime import datetime
import hashlib

from database import async_session, User, UserMovie, Recommendation
from tmdb import search_multi, get_details, format_media_type
from keyboards import (
    main_menu_kb, search_results_kb, movie_action_kb,
    rating_kb, watchlist_item_kb, watched_item_kb,
    recommendation_kb
)
from config import TMDB_IMAGE_BASE

router = Router()


class SearchState(StatesGroup):
    waiting_for_query = State()
    last_results = State()
    recommend_tmdb_id = State()
    recommend_media_type = State()
    recommend_title = State()
    recommend_poster = State()


# ─── helpers ───────────────────────────────────────────────

async def get_or_create_user(telegram_id: int, username: str, first_name: str, invited_by: int = None):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                invited_by=invited_by,
            )
            session.add(user)
            await session.commit()
        return user


async def get_user_movie(user_id: int, tmdb_id: int, media_type: str):
    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == user_id,
                UserMovie.tmdb_id == tmdb_id,
                UserMovie.media_type == media_type,
            )
        )
        return result.scalar_one_or_none()


def rating_to_emoji(rating: int) -> str:
    emojis = {1: "💀", 2: "😤", 3: "😑", 4: "😐", 5: "🙂",
               6: "👍", 7: "😊", 8: "🔥", 9: "⭐", 10: "💎"}
    return emojis.get(rating, "⭐")


def format_card_text(details: dict) -> str:
    title = details["title"]
    original = details["original_title"]
    year = details["year"]
    rating = details["vote_average"]
    overview = details["overview"]
    genres = ", ".join(details.get("genres", [])[:3]) if details.get("genres") else ""
    media = format_media_type(details["media_type"])

    stars = "⭐" * min(int(rating / 2), 5) if rating else ""
    rating_str = f"{rating:.1f}/10 {stars}" if rating else "нет оценки"

    text = f"<b>{title}</b>"
    if original and original != title:
        text += f"\n<i>{original}</i>"
    if year:
        text += f" · {year}"
    text += f"\n{media}"
    if genres:
        text += f" · {genres}"
    text += f"\n\n⭐ TMDB: {rating_str}"
    if overview:
        short = overview[:300] + "..." if len(overview) > 300 else overview
        text += f"\n\n{short}"

    return text


# ─── /start ────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    args = message.text.split()
    invited_by = None
    if len(args) > 1 and args[1].startswith("inv_"):
        try:
            invited_by = int(args[1][4:])
        except ValueError:
            pass

    await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        invited_by=invited_by,
    )

    name = message.from_user.first_name or "друг"
    await message.answer(
        f"🎬 Привет, <b>{name}</b>!\n\n"
        "Я помогу тебе следить за фильмами, сериалами и аниме.\n"
        "Ищи, добавляй в список, ставь оценки и советуй друзьям 🍿",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


# ─── SEARCH ────────────────────────────────────────────────

@router.message(F.text == "🔍 Найти")
async def ask_search(message: Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer("Введи название фильма, сериала или аниме 👇", reply_markup=main_menu_kb())


@router.message(SearchState.waiting_for_query)
async def do_search(message: Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        return

    await state.clear()
    msg = await message.answer("🔍 Ищу...")

    data = await search_multi(query)
    results = data["results"]

    if not results:
        await msg.edit_text("Ничего не нашла 😔 Попробуй другой запрос")
        return

    await state.update_data(last_results=results)
    await msg.edit_text(
        f"Нашла <b>{len(results)}</b> вариантов по запросу «{query}»\nВыбирай 👇",
        reply_markup=search_results_kb(results),
        parse_mode="HTML",
    )


# ─── DETAIL ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("detail:"))
async def show_detail(callback: CallbackQuery, state: FSMContext):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)

    await callback.answer()
    await callback.message.answer("⏳ Загружаю...")

    details = await get_details(tmdb_id, media_type)
    user_movie = await get_user_movie(callback.from_user.id, tmdb_id, media_type)

    is_watched = user_movie and user_movie.status == "watched"
    is_in_watchlist = user_movie and user_movie.status == "watchlist"

    text = format_card_text(details)

    kb = movie_action_kb(tmdb_id, media_type, is_in_watchlist=is_in_watchlist, is_watched=is_watched)

    if details["poster_url"]:
        await callback.message.answer_photo(
            photo=details["poster_url"],
            caption=text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── WATCHLIST ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("watchlist:"))
async def add_to_watchlist(callback: CallbackQuery, state: FSMContext):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)

    details = await get_details(tmdb_id, media_type)

    async with async_session() as session:
        existing = await get_user_movie(callback.from_user.id, tmdb_id, media_type)
        if existing:
            if existing.status == "watchlist":
                await callback.answer("Уже в списке желаний!")
                return
            existing.status = "watchlist"
            existing.rating = None
        else:
            movie = UserMovie(
                user_telegram_id=callback.from_user.id,
                tmdb_id=tmdb_id,
                media_type=media_type,
                title=details["title"],
                poster_path=details["poster_path"],
                status="watchlist",
            )
            session.add(movie)
        await session.commit()

    await callback.answer("❤️ Добавлено в список желаний!")


# ─── WATCHED ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("watched:"))
async def mark_watched(callback: CallbackQuery, state: FSMContext):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)

    details = await get_details(tmdb_id, media_type)

    async with async_session() as session:
        existing = await get_user_movie(callback.from_user.id, tmdb_id, media_type)
        if existing:
            existing.status = "watched"
            existing.watched_at = datetime.utcnow()
        else:
            movie = UserMovie(
                user_telegram_id=callback.from_user.id,
                tmdb_id=tmdb_id,
                media_type=media_type,
                title=details["title"],
                poster_path=details["poster_path"],
                status="watched",
                watched_at=datetime.utcnow(),
            )
            session.add(movie)
        await session.commit()

    await callback.answer("✅ Отмечено как просмотренное!")
    await callback.message.answer(
        f"Отлично! Как оцениваешь <b>{details['title']}</b>?",
        reply_markup=rating_kb(tmdb_id, media_type),
        parse_mode="HTML",
    )


# ─── RATING ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rate:"))
async def ask_rating(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    await callback.answer()
    await callback.message.answer(
        "Поставь оценку 👇",
        reply_markup=rating_kb(int(tmdb_id), media_type),
    )


@router.callback_query(F.data.startswith("setrating:"))
async def set_rating(callback: CallbackQuery):
    _, media_type, tmdb_id, score = callback.data.split(":")
    tmdb_id = int(tmdb_id)
    score = int(score)

    emoji = rating_to_emoji(score)

    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == callback.from_user.id,
                UserMovie.tmdb_id == tmdb_id,
                UserMovie.media_type == media_type,
            )
        )
        movie = result.scalar_one_or_none()
        if movie:
            movie.rating = score
            movie.status = "watched"
            if not movie.watched_at:
                movie.watched_at = datetime.utcnow()
            await session.commit()

    await callback.answer(f"{emoji} Оценка {score}/10 сохранена!")
    await callback.message.edit_text(
        f"Твоя оценка: {emoji} <b>{score}/10</b>",
        parse_mode="HTML",
    )


# ─── MY LISTS ──────────────────────────────────────────────

@router.message(F.text == "📋 Хочу посмотреть")
async def show_watchlist(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == message.from_user.id,
                UserMovie.status == "watchlist",
            ).order_by(UserMovie.added_at.desc())
        )
        movies = result.scalars().all()

    if not movies:
        await message.answer("Список пуст 😴 Найди что-нибудь через 🔍")
        return

    await message.answer(f"📋 <b>Хочу посмотреть</b> — {len(movies)} шт.\n\nВот твой список:", parse_mode="HTML")

    for m in movies[:15]:
        icon = "🎬" if m.media_type == "movie" else "📺"
        text = f"{icon} <b>{m.title}</b>"
        if m.recommended_by:
            text += "\n👤 <i>Кто-то посоветовал</i>"

        if m.poster_path:
            await message.answer_photo(
                photo=f"{TMDB_IMAGE_BASE}{m.poster_path}",
                caption=text,
                reply_markup=watchlist_item_kb(m.tmdb_id, m.media_type),
                parse_mode="HTML",
            )
        else:
            await message.answer(text, reply_markup=watchlist_item_kb(m.tmdb_id, m.media_type), parse_mode="HTML")


@router.message(F.text == "✅ Смотрел(а)")
async def show_watched(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == message.from_user.id,
                UserMovie.status == "watched",
            ).order_by(UserMovie.watched_at.desc())
        )
        movies = result.scalars().all()

    if not movies:
        await message.answer("Ты ещё ничего не отметил(а) как просмотренное 🎬")
        return

    await message.answer(f"✅ <b>Уже смотрел(а)</b> — {len(movies)} шт.", parse_mode="HTML")

    for m in movies[:15]:
        icon = "🎬" if m.media_type == "movie" else "📺"
        rating_str = f"{rating_to_emoji(m.rating)} {m.rating}/10" if m.rating else "без оценки"
        text = f"{icon} <b>{m.title}</b>\nОценка: {rating_str}"

        if m.poster_path:
            await message.answer_photo(
                photo=f"{TMDB_IMAGE_BASE}{m.poster_path}",
                caption=text,
                reply_markup=watched_item_kb(m.tmdb_id, m.media_type),
                parse_mode="HTML",
            )
        else:
            await message.answer(text, reply_markup=watched_item_kb(m.tmdb_id, m.media_type), parse_mode="HTML")


# ─── REMOVE ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("remove:"))
async def remove_movie(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)

    async with async_session() as session:
        await session.execute(
            delete(UserMovie).where(
                UserMovie.user_telegram_id == callback.from_user.id,
                UserMovie.tmdb_id == tmdb_id,
                UserMovie.media_type == media_type,
            )
        )
        await session.commit()

    await callback.answer("🗑 Удалено!")
    try:
        await callback.message.delete()
    except Exception:
        pass


# ─── RECOMMEND ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("recommend:"))
async def start_recommend(callback: CallbackQuery, state: FSMContext):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)

    details = await get_details(tmdb_id, media_type)

    await state.update_data(
        recommend_tmdb_id=tmdb_id,
        recommend_media_type=media_type,
        recommend_title=details["title"],
        recommend_poster=details["poster_path"],
    )

    await callback.answer()
    await callback.message.answer(
        f"📤 Хочешь посоветовать <b>{details['title']}</b> другу?\n\n"
        "Перешли любое сообщение от друга, которому хочешь посоветовать — "
        "или попроси его написать боту /start и поделись ссылкой ниже.",
        parse_mode="HTML",
    )

    bot_info = await callback.bot.get_me()
    user_id = callback.from_user.id
    invite_link = f"https://t.me/{bot_info.username}?start=inv_{user_id}"
    await callback.message.answer(
        f"🔗 Твоя ссылка-приглашение:\n{invite_link}\n\n"
        "Когда друг зарегистрируется — найди фильм снова и советуй через кнопку 📤"
    )


# ─── INBOX ─────────────────────────────────────────────────

@router.message(F.text == "📬 Мне советуют")
async def show_inbox(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(Recommendation).where(
                Recommendation.to_telegram_id == message.from_user.id,
            ).order_by(Recommendation.sent_at.desc())
        )
        recs = result.scalars().all()

    if not recs:
        await message.answer("Тебе пока ничего не советовали 📭\nПригласи друзей!")
        return

    new = [r for r in recs if not r.seen]
    old = [r for r in recs if r.seen]

    await message.answer(
        f"📬 <b>Советы от друзей</b>\n\n"
        f"🆕 Новые: {len(new)}\n"
        f"📖 Прочитанные: {len(old)}",
        parse_mode="HTML",
    )

    for rec in recs[:10]:
        icon = "🎬" if rec.media_type == "movie" else "📺"
        seen_mark = "" if not rec.seen else "✓ "
        text = f"{seen_mark}{icon} <b>{rec.title}</b>"
        if rec.message:
            text += f"\n💬 «{rec.message}»"

        async with async_session() as session2:
            sender_result = await session2.execute(
                select(User).where(User.telegram_id == rec.from_telegram_id)
            )
            sender = sender_result.scalar_one_or_none()
            if sender:
                sender_name = sender.first_name or sender.username or "Друг"
                text += f"\n👤 от {sender_name}"

        if rec.poster_path:
            await message.answer_photo(
                photo=f"{TMDB_IMAGE_BASE}{rec.poster_path}",
                caption=text,
                reply_markup=recommendation_kb(rec.tmdb_id, rec.media_type, rec.id),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                text,
                reply_markup=recommendation_kb(rec.tmdb_id, rec.media_type, rec.id),
                parse_mode="HTML",
            )


@router.callback_query(F.data.startswith("seen_rec:"))
async def mark_rec_seen(callback: CallbackQuery):
    rec_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        result = await session.execute(select(Recommendation).where(Recommendation.id == rec_id))
        rec = result.scalar_one_or_none()
        if rec:
            rec.seen = 1
            await session.commit()
    await callback.answer("✔️ Отмечено!")


# ─── PROFILE ───────────────────────────────────────────────

@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id

    async with async_session() as session:
        watched_result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == user_id,
                UserMovie.status == "watched",
            )
        )
        watched = watched_result.scalars().all()

        watchlist_result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == user_id,
                UserMovie.status == "watchlist",
            )
        )
        watchlist = watchlist_result.scalars().all()

        recs_sent_result = await session.execute(
            select(Recommendation).where(Recommendation.from_telegram_id == user_id)
        )
        recs_sent = recs_sent_result.scalars().all()

    rated = [m for m in watched if m.rating]
    avg_rating = round(sum(m.rating for m in rated) / len(rated), 1) if rated else None

    name = message.from_user.first_name or "Аноним"
    username = f"@{message.from_user.username}" if message.from_user.username else ""

    text = (
        f"👤 <b>{name}</b> {username}\n\n"
        f"✅ Посмотрел(а): <b>{len(watched)}</b>\n"
        f"📋 Хочу посмотреть: <b>{len(watchlist)}</b>\n"
        f"📤 Советов отдал(а): <b>{len(recs_sent)}</b>\n"
    )
    if avg_rating:
        text += f"⭐ Средняя оценка: <b>{avg_rating}/10</b>\n"

    if rated:
        text += "\n🏆 <b>Топ оценок:</b>\n"
        top = sorted(rated, key=lambda x: x.rating, reverse=True)[:5]
        for m in top:
            text += f"{rating_to_emoji(m.rating)} {m.title}\n"

    await message.answer(text, parse_mode="HTML")


# ─── INVITE ────────────────────────────────────────────────

@router.message(F.text == "🔗 Пригласить друга")
async def invite_friend(message: Message):
    bot_info = await message.bot.get_me()
    user_id = message.from_user.id
    invite_link = f"https://t.me/{bot_info.username}?start=inv_{user_id}"

    await message.answer(
        f"🔗 Поделись этой ссылкой с другом:\n\n"
        f"<code>{invite_link}</code>\n\n"
        "Когда он зайдёт в бота — вы сможете советовать друг другу фильмы 🍿",
        parse_mode="HTML",
    )


# ─── NOOP / CANCEL ─────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery):
    await callback.answer("Отменено")


@router.callback_query(F.data == "back_to_search")
async def back_to_search(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Введи новый запрос для поиска 🔍", reply_markup=main_menu_kb())
