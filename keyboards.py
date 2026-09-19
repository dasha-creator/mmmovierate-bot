from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти"), KeyboardButton(text="🎲 Рандомный")],
            [KeyboardButton(text="📋 Мой список"), KeyboardButton(text="📬 Мне советуют")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🔗 Пригласить друга")],
        ],
        resize_keyboard=True,
    )


def back_menu_kb() -> ReplyKeyboardMarkup:
    """Минимальная клавиатура когда внутри списка/карточки"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Главное меню")]],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def search_results_kb(results: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in results:
        icon = "🎬" if item["media_type"] == "movie" else "📺"
        year = f" ({item['year']})" if item["year"] else ""
        label = f"{icon} {item['title']}{year}"
        if len(label) > 60:
            label = label[:57] + "..."
        builder.button(text=label, callback_data=f"detail:{item['media_type']}:{item['tmdb_id']}")
    builder.adjust(1)
    return builder.as_markup()


def movie_action_kb(tmdb_id: int, media_type: str, is_in_watchlist: bool = False, is_watched: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_watched:
        builder.button(text="✅ Уже смотрел(а)", callback_data="noop")
        builder.button(text="✏️ Изменить оценку", callback_data=f"rate:{media_type}:{tmdb_id}")
    elif is_in_watchlist:
        builder.button(text="📋 В списке желаний", callback_data="noop")
        builder.button(text="✅ Отметить как просмотрено", callback_data=f"watched:{media_type}:{tmdb_id}")
    else:
        builder.button(text="❤️ Хочу посмотреть", callback_data=f"watchlist:{media_type}:{tmdb_id}")
        builder.button(text="✅ Уже смотрел(а)", callback_data=f"watched:{media_type}:{tmdb_id}")

    builder.button(text="📤 Посоветовать другу", callback_data=f"recommend:{media_type}:{tmdb_id}")
    builder.adjust(1)
    return builder.as_markup()


def rating_kb(tmdb_id: int, media_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    items = [("💀", 1), ("😤", 2), ("😑", 3), ("😐", 4), ("🙂", 5),
             ("👍", 6), ("😊", 7), ("🔥", 8), ("⭐", 9), ("💎", 10)]
    for emoji, score in items:
        builder.button(text=f"{emoji} {score}", callback_data=f"setrating:{media_type}:{tmdb_id}:{score}")
    builder.adjust(5)
    return builder.as_markup()


def mylist_tabs_kb(active: str) -> InlineKeyboardMarkup:
    """Переключатель вкладок в моём списке"""
    builder = InlineKeyboardBuilder()
    watchlist_mark = "● " if active == "watchlist" else ""
    watched_mark = "● " if active == "watched" else ""
    builder.button(text=f"{watchlist_mark}📋 Хочу посмотреть", callback_data="mylist:watchlist")
    builder.button(text=f"{watched_mark}✅ Смотрел(а)", callback_data="mylist:watched")
    builder.adjust(2)
    return builder.as_markup()


def watchlist_item_kb(tmdb_id: int, media_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Посмотрел(а)!", callback_data=f"watched:{media_type}:{tmdb_id}")
    builder.button(text="📤 Посоветовать", callback_data=f"recommend:{media_type}:{tmdb_id}")
    builder.button(text="🗑 Удалить", callback_data=f"remove:{media_type}:{tmdb_id}")
    builder.adjust(1)
    return builder.as_markup()


def watched_item_kb(tmdb_id: int, media_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить оценку", callback_data=f"rate:{media_type}:{tmdb_id}")
    builder.button(text="📤 Посоветовать", callback_data=f"recommend:{media_type}:{tmdb_id}")
    builder.button(text="🗑 Удалить", callback_data=f"remove:{media_type}:{tmdb_id}")
    builder.adjust(1)
    return builder.as_markup()


def friends_list_kb(friends: list, tmdb_id: int, media_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for friend in friends:
        name = friend.first_name or "Аноним"
        username = f" (@{friend.username})" if friend.username else ""
        builder.button(
            text=f"👤 {name}{username}",
            callback_data=f"send_rec:{media_type}:{tmdb_id}:{friend.telegram_id}"
        )
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(1)
    return builder.as_markup()


def recommendation_kb(tmdb_id: int, media_type: str, rec_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Хочу посмотреть", callback_data=f"watchlist:{media_type}:{tmdb_id}")
    builder.button(text="✅ Уже смотрел(а)", callback_data=f"watched:{media_type}:{tmdb_id}")
    builder.button(text="✔️ Прочитано", callback_data=f"seen_rec:{rec_id}")
    builder.adjust(1)
    return builder.as_markup()
