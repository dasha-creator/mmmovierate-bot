from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from datetime import datetime
import random
import aiohttp

from database import async_session, User, UserMovie, Recommendation
from tmdb import search_multi, get_details, format_media_type, get_popular
from keyboards import (
    main_menu_kb, back_menu_kb, remove_kb,
    search_results_kb, movie_action_kb, rating_kb,
    mylist_tabs_kb, watchlist_item_kb, watched_item_kb,
    friends_list_kb, recommendation_kb,
)
from config import TMDB_IMAGE_BASE

router = Router()

# Все тексты кнопок главного меню — чтобы не попадали в поиск
MENU_BUTTONS = {
    "🔍 Найти", "🎲 Рандомный", "📋 Мой список",
    "📬 Мне советуют", "👤 Профиль", "🔗 Пригласить друга",
    "🏠 Главное меню",
}


# ─── helpers ───────────────────────────────────────────────

async def get_or_create_user(telegram_id, username, first_name, invited_by=None):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username,
                        first_name=first_name, invited_by=invited_by)
            session.add(user)
            await session.commit()
        return user


async def get_user_movie(user_id, tmdb_id, media_type):
    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == user_id,
                UserMovie.tmdb_id == tmdb_id,
                UserMovie.media_type == media_type,
            )
        )
        return result.scalar_one_or_none()


async def get_friends(user_id: int) -> list:
    friend_ids = set()
    async with async_session() as session:
        # Те кого пригласил я
        res = await session.execute(select(User).where(User.invited_by == user_id))
        for u in res.scalars().all():
            friend_ids.add(u.telegram_id)

        # Тот кто пригласил меня
        me = await session.execute(select(User).where(User.telegram_id == user_id))
        me_user = me.scalar_one_or_none()
        if me_user and me_user.invited_by:
            friend_ids.add(me_user.invited_by)

        # Те кому я советовал
        sent = await session.execute(
            select(Recommendation.to_telegram_id).where(Recommendation.from_telegram_id == user_id)
        )
        for tid in sent.scalars().all():
            friend_ids.add(tid)

        # Те кто советовал мне
        received = await session.execute(
            select(Recommendation.from_telegram_id).where(Recommendation.to_telegram_id == user_id)
        )
        for tid in received.scalars().all():
            friend_ids.add(tid)

        friend_ids.discard(user_id)

        friends = []
        for fid in friend_ids:
            res = await session.execute(select(User).where(User.telegram_id == fid))
            u = res.scalar_one_or_none()
            if u:
                friends.append(u)
    return friends


def rating_to_emoji(rating):
    return {1:"💀",2:"😤",3:"😑",4:"😐",5:"🙂",6:"👍",7:"😊",8:"🔥",9:"⭐",10:"💎"}.get(rating, "⭐")


def format_card_text(details):
    title = details["title"]
    original = details["original_title"]
    year = details["year"]
    rating = details["vote_average"]
    overview = details["overview"]
    genres = ", ".join(details.get("genres", [])[:3])
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
        short = overview[:300] + ("..." if len(overview) > 300 else "")
        text += f"\n\n{short}"
    return text


# ─── /start ────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    invited_by = None
    if len(args) > 1 and args[1].startswith("inv_"):
        try:
            invited_by = int(args[1][4:])
        except ValueError:
            pass

    await get_or_create_user(
        message.from_user.id, message.from_user.username,
        message.from_user.first_name, invited_by
    )
    name = message.from_user.first_name or "друг"
    await message.answer(
        f"🎬 Привет, <b>{name}</b>!\n\n"
        "Ищи фильмы, добавляй в список, ставь оценки и советуй друзьям 🍿",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


# ─── ГЛАВНОЕ МЕНЮ — возврат ────────────────────────────────

@router.message(F.text == "🏠 Главное меню")
async def go_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню 👇", reply_markup=main_menu_kb())


# ─── ПОИСК ─────────────────────────────────────────────────

@router.message(F.text == "🔍 Найти")
async def ask_search(message: Message):
    await message.answer("Введи название фильма, сериала или аниме 👇", reply_markup=back_menu_kb())


@router.message(F.text.func(lambda t: t not in MENU_BUTTONS and len(t) >= 2))
async def auto_search(message: Message, state: FSMContext):
    query = message.text.strip()
    msg = await message.answer("🔍 Ищу...", reply_markup=back_menu_kb())
    data = await search_multi(query)
    results = data["results"]

    if not results:
        await msg.edit_text("Ничего не нашла 😔 Попробуй другой запрос")
        return

    await state.update_data(last_results=results)
    await msg.edit_text(
        f"Нашла <b>{len(results)}</b> вариантов — выбирай 👇",
        reply_markup=search_results_kb(results),
        parse_mode="HTML",
    )


# ─── КАРТОЧКА ФИЛЬМА ───────────────────────────────────────

@router.callback_query(F.data.startswith("detail:"))
async def show_detail(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)
    await callback.answer()

    details = await get_details(tmdb_id, media_type)
    user_movie = await get_user_movie(callback.from_user.id, tmdb_id, media_type)
    is_watched = user_movie and user_movie.status == "watched"
    is_in_watchlist = user_movie and user_movie.status == "watchlist"

    text = format_card_text(details)
    kb = movie_action_kb(tmdb_id, media_type, is_in_watchlist, is_watched)

    if details["poster_url"]:
        await callback.message.answer_photo(photo=details["poster_url"], caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── WATCHLIST ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("watchlist:"))
async def add_to_watchlist(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)
    details = await get_details(tmdb_id, media_type)

    async with async_session() as session:
        existing = await get_user_movie(callback.from_user.id, tmdb_id, media_type)
        if existing:
            if existing.status == "watchlist":
                await callback.answer("Уже в списке!")
                return
            existing.status = "watchlist"
            existing.rating = None
            await session.merge(existing)
        else:
            session.add(UserMovie(
                user_telegram_id=callback.from_user.id, tmdb_id=tmdb_id,
                media_type=media_type, title=details["title"],
                poster_path=details["poster_path"], status="watchlist",
            ))
        await session.commit()
    await callback.answer("❤️ Добавлено в список!")


# ─── WATCHED ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("watched:"))
async def mark_watched(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)
    details = await get_details(tmdb_id, media_type)

    async with async_session() as session:
        existing = await get_user_movie(callback.from_user.id, tmdb_id, media_type)
        if existing:
            existing.status = "watched"
            existing.watched_at = datetime.utcnow()
            await session.merge(existing)
        else:
            session.add(UserMovie(
                user_telegram_id=callback.from_user.id, tmdb_id=tmdb_id,
                media_type=media_type, title=details["title"],
                poster_path=details["poster_path"], status="watched",
                watched_at=datetime.utcnow(),
            ))
        await session.commit()

    await callback.answer("✅ Отмечено!")
    await callback.message.answer(
        f"Как оцениваешь <b>{details['title']}</b>?",
        reply_markup=rating_kb(tmdb_id, media_type),
        parse_mode="HTML",
    )


# ─── RATING ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rate:"))
async def ask_rating(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    await callback.answer()
    await callback.message.answer("Поставь оценку 👇", reply_markup=rating_kb(int(tmdb_id), media_type))


@router.callback_query(F.data.startswith("setrating:"))
async def set_rating(callback: CallbackQuery):
    _, media_type, tmdb_id, score = callback.data.split(":")
    tmdb_id, score = int(tmdb_id), int(score)
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

    await callback.answer(f"{emoji} {score}/10 сохранено!")
    await callback.message.edit_text(f"Твоя оценка: {emoji} <b>{score}/10</b>", parse_mode="HTML")
    await callback.message.answer("Что дальше?", reply_markup=main_menu_kb())


# ─── МОЙ СПИСОК ────────────────────────────────────────────

@router.message(F.text == "📋 Мой список")
async def show_mylist(message: Message):
    await _show_list(message, "watchlist")


@router.callback_query(F.data.startswith("mylist:"))
async def switch_list_tab(callback: CallbackQuery):
    tab = callback.data.split(":")[1]
    await callback.answer()
    await _show_list(callback.message, tab, edit=False)


async def _show_list(target, tab: str, edit: bool = False):
    user_id = target.from_user.id if hasattr(target, 'from_user') else target.chat.id

    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == user_id,
                UserMovie.status == tab,
            ).order_by(UserMovie.added_at.desc() if tab == "watchlist" else UserMovie.watched_at.desc())
        )
        movies = result.scalars().all()

    tabs_kb = mylist_tabs_kb(tab)

    if not movies:
        empty_text = "📋 Список пуст — найди что-нибудь!" if tab == "watchlist" else "✅ Ты ещё ничего не смотрел(а)"
        if isinstance(target, Message):
            await target.answer(empty_text, reply_markup=back_menu_kb())
            await target.answer("Переключить:", reply_markup=tabs_kb)
        else:
            await target.answer(empty_text, reply_markup=tabs_kb)
        return

    label = "📋 Хочу посмотреть" if tab == "watchlist" else "✅ Уже смотрел(а)"
    if isinstance(target, Message):
        await target.answer(f"{label} — <b>{len(movies)}</b> шт.", reply_markup=back_menu_kb(), parse_mode="HTML")
        await target.answer("Переключить:", reply_markup=tabs_kb)
    else:
        await target.answer(f"{label} — <b>{len(movies)}</b> шт.", reply_markup=tabs_kb, parse_mode="HTML")

    for m in movies[:10]:
        icon = "🎬" if m.media_type == "movie" else "📺"
        if tab == "watchlist":
            text = f"{icon} <b>{m.title}</b>"
            kb = watchlist_item_kb(m.tmdb_id, m.media_type)
        else:
            rating_str = f"{rating_to_emoji(m.rating)} {m.rating}/10" if m.rating else "без оценки"
            text = f"{icon} <b>{m.title}</b>\n{rating_str}"
            kb = watched_item_kb(m.tmdb_id, m.media_type)

        send = target if isinstance(target, Message) else target
        if m.poster_path:
            await send.answer_photo(photo=f"{TMDB_IMAGE_BASE}{m.poster_path}", caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await send.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── RANDOM ────────────────────────────────────────────────

@router.message(F.text == "🎲 Рандомный")
async def random_movie(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(UserMovie).where(
                UserMovie.user_telegram_id == message.from_user.id,
                UserMovie.status == "watchlist",
            )
        )
        watchlist = result.scalars().all()

    if watchlist:
        pick = random.choice(watchlist)
        details = await get_details(pick.tmdb_id, pick.media_type)
        text = "🎲 <b>Сегодня смотришь:</b>\n\n" + format_card_text(details)
        kb = movie_action_kb(pick.tmdb_id, pick.media_type, is_in_watchlist=True)
    else:
        # Если вишлист пустой — берём популярное с TMDB
        popular = await get_popular()
        if not popular:
            await message.answer("Не удалось получить фильмы 😔")
            return
        pick = random.choice(popular[:10])
        details = await get_details(pick["tmdb_id"], pick["media_type"])
        text = "🎲 <b>Попробуй посмотреть:</b>\n\n" + format_card_text(details)
        kb = movie_action_kb(pick["tmdb_id"], pick["media_type"])

    if details["poster_url"]:
        await message.answer_photo(photo=details["poster_url"], caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ─── REMOVE ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("remove:"))
async def remove_movie(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    async with async_session() as session:
        await session.execute(
            delete(UserMovie).where(
                UserMovie.user_telegram_id == callback.from_user.id,
                UserMovie.tmdb_id == int(tmdb_id),
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
async def start_recommend(callback: CallbackQuery):
    _, media_type, tmdb_id = callback.data.split(":")
    tmdb_id = int(tmdb_id)
    friends = await get_friends(callback.from_user.id)
    await callback.answer()

    if not friends:
        bot_info = await callback.bot.get_me()
        invite_link = f"https://t.me/{bot_info.username}?start=inv_{callback.from_user.id}"
        await callback.message.answer(
            "У тебя пока нет друзей в боте 😔\n\n"
            "Поделись ссылкой — когда друг зайдёт, сможешь советовать:\n\n"
            f"<code>{invite_link}</code>",
            parse_mode="HTML",
        )
        return

    details = await get_details(tmdb_id, media_type)
    await callback.message.answer(
        f"Кому посоветовать <b>{details['title']}</b>? 👇",
        reply_markup=friends_list_kb(friends, tmdb_id, media_type),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("send_rec:"))
async def send_recommendation(callback: CallbackQuery):
    parts = callback.data.split(":")
    media_type, tmdb_id, to_user_id = parts[1], int(parts[2]), int(parts[3])
    details = await get_details(tmdb_id, media_type)

    async with async_session() as session:
        rec = Recommendation(
            from_telegram_id=callback.from_user.id, to_telegram_id=to_user_id,
            tmdb_id=tmdb_id, media_type=media_type, title=details["title"],
            poster_path=details["poster_path"],
        )
        session.add(rec)
        await session.commit()
        rec_id = rec.id

    from_name = callback.from_user.first_name or "Кто-то"
    try:
        text = f"📬 <b>{from_name}</b> советует:\n\n<b>{details['title']}</b>"
        kb = recommendation_kb(tmdb_id, media_type, rec_id)
        if details["poster_url"]:
            await callback.bot.send_photo(chat_id=to_user_id, photo=details["poster_url"],
                                           caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.bot.send_message(chat_id=to_user_id, text=text,
                                             reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass

    await callback.answer("📤 Отправлено!")
    await callback.message.edit_text("✅ Совет отправлен!")


# ─── INBOX ─────────────────────────────────────────────────

@router.message(F.text == "📬 Мне советуют")
async def show_inbox(message: Message):
    async with async_session() as session:
        result = await session.execute(
            select(Recommendation).where(
                Recommendation.to_telegram_id == message.from_user.id
            ).order_by(Recommendation.sent_at.desc())
        )
        recs = result.scalars().all()

    if not recs:
        await message.answer("Тебе пока ничего не советовали 📭\nПригласи друзей!", reply_markup=main_menu_kb())
        return

    new_count = len([r for r in recs if not r.seen])
    await message.answer(
        f"📬 <b>Советы от друзей</b> — {len(recs)} шт., 🆕 новых: {new_count}",
        reply_markup=back_menu_kb(),
        parse_mode="HTML",
    )

    for rec in recs[:10]:
        icon = "🎬" if rec.media_type == "movie" else "📺"
        seen_mark = "" if not rec.seen else "✓ "
        async with async_session() as s:
            sender = (await s.execute(select(User).where(User.telegram_id == rec.from_telegram_id))).scalar_one_or_none()
        sender_name = (sender.first_name if sender else None) or "Друг"
        text = f"{seen_mark}{icon} <b>{rec.title}</b>\n👤 от {sender_name}"
        kb = recommendation_kb(rec.tmdb_id, rec.media_type, rec.id)

        if rec.poster_path:
            await message.answer_photo(photo=f"{TMDB_IMAGE_BASE}{rec.poster_path}",
                                        caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")


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


# ─── ПРОФИЛЬ ───────────────────────────────────────────────

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    async with async_session() as session:
        watched = (await session.execute(
            select(UserMovie).where(UserMovie.user_telegram_id == user_id, UserMovie.status == "watched")
        )).scalars().all()
        watchlist = (await session.execute(
            select(UserMovie).where(UserMovie.user_telegram_id == user_id, UserMovie.status == "watchlist")
        )).scalars().all()
        recs_sent = (await session.execute(
            select(Recommendation).where(Recommendation.from_telegram_id == user_id)
        )).scalars().all()

    friends = await get_friends(user_id)
    rated = [m for m in watched if m.rating]
    avg = round(sum(m.rating for m in rated) / len(rated), 1) if rated else None

    name = message.from_user.first_name or "Аноним"
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    text = (
        f"👤 <b>{name}</b> {username}\n\n"
        f"✅ Посмотрел(а): <b>{len(watched)}</b>\n"
        f"📋 Хочу посмотреть: <b>{len(watchlist)}</b>\n"
        f"👥 Друзей в боте: <b>{len(friends)}</b>\n"
        f"📤 Советов отдал(а): <b>{len(recs_sent)}</b>\n"
    )
    if avg:
        text += f"⭐ Средняя оценка: <b>{avg}/10</b>\n"
    if rated:
        text += "\n🏆 <b>Топ оценок:</b>\n"
        for m in sorted(rated, key=lambda x: x.rating, reverse=True)[:5]:
            text += f"{rating_to_emoji(m.rating)} {m.title}\n"

    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


# ─── ПРИГЛАСИТЬ ────────────────────────────────────────────

@router.message(F.text == "🔗 Пригласить друга")
async def invite_friend(message: Message):
    bot_info = await message.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=inv_{message.from_user.id}"
    await message.answer(
        f"🔗 Твоя ссылка-приглашение:\n\n<code>{link}</code>\n\n"
        "Когда друг зайдёт — сможешь советовать ему фильмы 🍿",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


# ─── NOOP / CANCEL ─────────────────────────────────────────

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "cancel")
async def cancel_cb(callback: CallbackQuery):
    await callback.answer("Отменено")
    try:
        await callback.message.delete()
    except Exception:
        pass
