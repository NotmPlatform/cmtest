import csv
import json
import logging
import os
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================================================
# CONFIG
# =========================================================
# Перед запуском задайте:
# export BOT_TOKEN="ВАШ_ТОКЕН"
# export ADMIN_CHAT_ID="-1001234567890"   # ID закрытой группы / чата для результатов
# export PASS_SCORE="12"                  # опционально
# export QUESTIONS_PER_TEST="15"          # опционально
#
# Логика сертификата:
# 1) После успешной сдачи бот отправляет результат в ADMIN_CHAT_ID
# 2) Админ отвечает НА ЭТО СООБЩЕНИЕ pdf-файлом сертификата
# 3) Бот отправляет этот PDF пользователю, чей результат был в сообщении

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
PASS_SCORE = int(os.getenv("PASS_SCORE", "12"))
QUESTIONS_PER_TEST = int(os.getenv("QUESTIONS_PER_TEST", "15"))

BASE_DIR = Path(__file__).resolve().parent
RESULTS_FILE = BASE_DIR / "quiz_results.csv"
ATTEMPTS_FILE = BASE_DIR / "attempts.json"
ADMIN_LINKS_FILE = BASE_DIR / "admin_message_links.json"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z\s\-']{1,58}[A-Za-z]$|^[A-Za-z]{2,60}$")
LINKEDIN_RE = re.compile(r"^https?://(www\.)?linkedin\.com/.*$", re.IGNORECASE)
LETTERS = ["A", "B", "C", "D"]

# =========================================================
# QUESTION BANK (50)
# =========================================================
QUESTION_BANK = [
    {"q": "Что в Web3 CM делает в первую очередь: просто отвечает в чате или управляет доверием?", "options": ["Просто отвечает на сообщения", "Управляет доверием и атмосферой среды", "Заменяет support", "Отвечает только по скрипту"], "correct": 1},
    {"q": "Почему обычные CM часто проваливаются в Web3?", "options": ["Потому что мало пишут сообщений", "Потому что Web3 требует скорости, ясности и понимания риска ошибок", "Потому что им не дают доступ в чат", "Потому что не умеют делать мемы"], "correct": 1},
    {"q": "Какой главный принцип из урока про 5 типов людей в чате?", "options": ["Самый громкий участник всегда самый полезный", "Нужно усиливать только тех, кто много пишет", "Важно смотреть на ценность и влияние, а не только на громкость", "Всех активных нужно делать амбассадорами"], "correct": 2},
    {"q": "Кого сильный CM должен в первую очередь стараться вырастить?", "options": ["Токсичных, но заметных людей", "Потенциальных лидеров и trusted helpers", "Только тех, у кого большой аккаунт в X", "Любого, кто пишет первым"], "correct": 1},
    {"q": "Что важнее для Telegram как платформы?", "options": ["Структура каналов и ролей", "Публичная репутация в открытом поле", "Скорость, присутствие и живое ощущение бренда", "Только длинные формальные ответы"], "correct": 2},
    {"q": "Что важнее для Discord?", "options": ["Структура, роли, навигация и порядок", "Самый быстрый ответ любой ценой", "Публичный имидж для внешней аудитории", "Ответы без правил и разделов"], "correct": 0},
    {"q": "Что важнее для X / Twitter?", "options": ["Длинные объяснения в 10 абзацев", "Публичная ясность, краткость и репутация", "Полное игнорирование негатива", "Только общение в личке"], "correct": 1},
    {"q": "Что такое сильный tone of voice бренда?", "options": ["Случайный микс мемов и шуток", "Мёртво-корпоративный стиль", "Ясный, живой, спокойный и надёжный голос", "Грубая уверенность без объяснений"], "correct": 2},
    {"q": "Что из этого ближе к сильному тону бренда?", "options": ["Читайте правила внимательнее", "Понимаем, где тут можно запутаться. Коротко объясню", "Мы уже сто раз отвечали", "Это ваши проблемы"], "correct": 1},
    {"q": "Что сильный CM делает с angry user?", "options": ["Пытается победить его в споре", "Игнорирует полностью", "Снижает напряжение, возвращает ясность и удерживает доверие", "Сразу банит без разбора"], "correct": 2},
    {"q": "Что чаще заражает чат сильнее самого angry user?", "options": ["Хороший ясный ответ", "Слабая реакция бренда", "Смайлик в сообщении", "Тишина ночью"], "correct": 1},
    {"q": "Какой минимальный продуктовый уровень нужен CM?", "options": ["Знать всё глубже product manager", "Понимать базовую механику продукта и частые точки путаницы", "Вообще не понимать продукт", "Знать только брендбук"], "correct": 1},
    {"q": "Что CM должен уметь объяснять простыми словами?", "options": ["Только мемы из комьюнити", "Spot, Futures, P2P, rewards, referral и базовую механику", "Только внутренние процессы compliance", "Только юридические документы"], "correct": 1},
    {"q": "Когда CM должен ответить сам?", "options": ["Когда вопрос типовой, публичный и безопасный", "Когда вопрос про личный баланс пользователя", "Когда вопрос про результат проверки аккаунта", "Когда вопрос про снятие ограничения"], "correct": 0},
    {"q": "Когда вопрос нужно эскалировать дальше?", "options": ["Когда это общий вопрос по FAQ", "Когда это личный кейс: аккаунт, деньги, ограничения, review", "Когда вопрос короткий", "Когда пользователь вежливый"], "correct": 1},
    {"q": "Что CM никогда не должен обещать без подтверждения?", "options": ["Что вопрос замечен", "Что команда проверяет тему", "Точный срок решения, начисление денег или результат review", "Что апдейт появится в канале"], "correct": 2},
    {"q": "Что сильный CM делает с шумом комьюнити?", "options": ["Игнорирует всё подряд", "Переводит поток сообщений в сигналы и инсайты для команд", "Сохраняет только самые негативные комментарии", "Отвечает всем одинаково"], "correct": 1},
    {"q": "Что важнее в lesson 9: единичная жалоба или повторяющийся паттерн?", "options": ["Всегда единичная жалоба", "Повторяющийся паттерн и его влияние", "Только количество эмодзи", "Только сообщения от старых участников"], "correct": 1},
    {"q": "Что делает чат живым, а не просто шумным?", "options": ["Случайный поток сообщений без смысла", "Ритм, точки входа, ощущение движения и причины возвращаться", "Постоянные капслок-сообщения", "Только конкурсы с призами"], "correct": 1},
    {"q": "Что такое engagement loop?", "options": ["Разовая акция без продолжения", "Повторяющийся цикл участия, который формирует привычку возвращаться", "Любой спам в чате", "Только AMA-сессия"], "correct": 1},
    {"q": "Что делает сильную активацию сильной?", "options": ["Только большой приз", "Понятная цель, низкий порог входа, fit с брендом и следующий шаг", "Случайный формат без смысла", "Максимально сложные условия"], "correct": 1},
    {"q": "Как сильный CM выращивает ядро комьюнити?", "options": ["Выбирает только самых громких", "Даёт титулы всем подряд", "Через признание, роль, смысл, рост и удержание", "Только через денежную награду"], "correct": 2},
    {"q": "Кто ближе к будущему local leader?", "options": ["Самый конфликтный участник", "Человек, который стабильно помогает и усиливает среду", "Любой, кто просит роль", "Тот, кто пишет ночью"], "correct": 1},
    {"q": "Что главное в приоритизации дня CM?", "options": ["Реагировать на всё самое громкое", "Отличать critical, important, monitor и noise", "Отвечать всем одинаково быстро", "Полностью избегать эскалации"], "correct": 1},
    {"q": "Что означает принцип: attention follows priority, not noise?", "options": ["Нужно реагировать только на громкие сообщения", "Внимание должно идти за важностью, а не за шумом", "Все вопросы одинаково важны", "Лучше ничего не замечать"], "correct": 1},
    {"q": "Что в ответе слабого CM встречается чаще всего?", "options": ["Ясность и следующий шаг", "Defensiveness, vagueness и пустые обещания", "Спокойствие и уважение", "Признание эмоции"], "correct": 1},
    {"q": "Что делает сильный ответ сильным?", "options": ["Уважение, ясность, следующий шаг и рост доверия", "Резкость и холодный тон", "Только скорость", "Длинный спор с пользователем"], "correct": 0},
    {"q": "Что важнее для входа в Web3 без громкого опыта?", "options": ["Ждать, пока появится крупный бренд в CV", "Показать читаемое мышление, реальные кейсы и язык роли", "Убрать весь реальный опыт из CV", "Писать только мотивационное письмо"], "correct": 1},
    {"q": "Что лучше усиливает CV новичка в Web3 CM?", "options": ["Фразы без примеров: 'коммуникабельный, ответственный'", "1–2 mini-cases с понятной логикой и результатом", "Только фото профиля", "Список любимых проектов"], "correct": 1},
    {"q": "Что сильнее в FAQ?", "options": ["Длинные сложные ответы со множеством терминов", "Короткие, ясные ответы и понятный маршрут дальше", "Юридический язык без объяснений", "Публичные догадки по личным кейсам"], "correct": 1},
    {"q": "Что должен делать хороший weekly report?", "options": ["Просто перечислять все сообщения за неделю", "Показывать темы, сигналы, риски и следующие шаги", "Содержать как можно больше воды", "Быть длиннее всех остальных документов"], "correct": 1},
    {"q": "Что должно быть в коротком community report?", "options": ["Состояние комьюнити, главные темы, сигналы и следующие шаги", "Только список всех участников", "Только позитивные сообщения", "Только реклама акций"], "correct": 0},
    {"q": "Для чего нужен ambassador tracker?", "options": ["Только для списка имён", "Чтобы видеть, кто реально усиливает комьюнити и кому давать следующую роль", "Чтобы записывать только победителей конкурсов", "Чтобы хранить мемы"], "correct": 1},
    {"q": "Что сильный CM делает в AMA, если ответа пока нет?", "options": ["Придумывает ответ на ходу", "Честно фиксирует вопрос и возвращается с подтверждённым follow-up", "Игнорирует вопрос", "Сразу удаляет сообщение"], "correct": 1},
    {"q": "Что важнее в mini-portfolio для Web3 CM?", "options": ["Количество страниц", "Понятный ход мышления и применимость к роли", "Только красивые цвета", "Случайные скриншоты"], "correct": 1},
    {"q": "Что лучше сказать вместо 'Читайте правила внимательнее'?", "options": ["Это не моя проблема", "Понимаю, где тут можно запутаться. Коротко объясню", "Мы уже отвечали", "Всё есть в посте"], "correct": 1},
    {"q": "Какой ответ сильнее при задержке бонусов?", "options": ["Скоро всё придёт", "Ждите", "Понимаю ваше раздражение. Команда проверяет статус, вернёмся с подтверждённым апдейтом", "Не спамьте в чат"], "correct": 2},
    {"q": "Что сильный CM делает с recurring issues?", "options": ["Считает их личными жалобами", "Фиксирует, структурирует и передаёт как сигнал команде", "Удаляет все сообщения", "Отвечает только смайликом"], "correct": 1},
    {"q": "Что значит brand fit в активации?", "options": ["Активация выглядит естественно для бренда и комьюнити", "Активация делается только ради охвата", "Активация должна быть дорогой", "Активация должна быть непонятной"], "correct": 0},
    {"q": "Что лучше описывает сильный short report?", "options": ["Короткий, ясный, с паттернами и действиями", "Эмоциональный и длинный", "Без выводов и next steps", "Только про позитив"], "correct": 0},
    {"q": "Что делать с личным кейсом по blocked account в общем чате?", "options": ["Публично угадывать причину", "Обещать разблокировку", "Перевести в официальный маршрут через support/compliance", "Обсуждать детали аккаунта публично"], "correct": 2},
    {"q": "Что такое low entry barrier в активации?", "options": ["Человеку легко включиться без лишней сложности", "Нужно пройти 10 шагов", "Только участники с премиум-статусом могут войти", "Нужен отдельный доступ от admin"], "correct": 0},
    {"q": "Какой подход к rules chat сильнее?", "options": ["Запрещать любую критику", "Разрешать конструктивную критику, но не токсичность и спам", "Вообще не модерировать чат", "Удалять все вопросы по продукту"], "correct": 1},
    {"q": "Что важнее в финале AMA?", "options": ["Просто закончить без follow-up", "Подвести итог и вернуть recap / follow-up по незакрытым вопросам", "Удалить чат", "Начать спор"], "correct": 1},
    {"q": "Что делает хороший FAQ полезным для команды?", "options": ["Уменьшает повторяющийся шум и помогает пользователю быстро понять маршрут", "Усложняет ответы", "Содержит максимум воды", "Заменяет всю поддержку"], "correct": 0},
    {"q": "Что важнее в CV: действие или результат?", "options": ["Только действие", "Только красивые слова", "Лучше показывать действие + результат", "Ничего не указывать"], "correct": 2},
    {"q": "Какой путь роста внутри комьюнити ближе к уроку 12?", "options": ["Active User → Trusted Helper → Local Leader", "Reader → Hater → Moderator", "Trader → Admin → Owner", "Follower → Bot → Sponsor"], "correct": 0},
    {"q": "Какой блок должен быть в конце сильного ответа на негатив?", "options": ["Следующий шаг / апдейт / маршрут", "Сарказм", "Новый конфликт", "Случайная шутка"], "correct": 0},
    {"q": "Что лучше показывает зрелость CM?", "options": ["Отвечать на всё подряд без проверки", "Понимать, где ответить, где уточнить и где эскалировать", "Отвечать только ночью", "Избегать любых сложных вопросов"], "correct": 1},
    {"q": "Что лучше описывает итог сильного курса для CM?", "options": ["Человек знает много терминов, но не умеет применять", "Человек мыслит как специалист и может войти в роль", "Человек умеет только читать посты", "Человек знает только названия бирж"], "correct": 1},
]

# =========================================================
# FILE HELPERS
# =========================================================
def ensure_results_file():
    if not RESULTS_FILE.exists():
        with RESULTS_FILE.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp",
                    "telegram_id",
                    "username",
                    "full_name_latin",
                    "linkedin",
                    "score",
                    "total",
                    "passed",
                ]
            )

def load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Could not load %s: %s", path.name, e)
        return {}

def save_json_file(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_attempt(user_id: int) -> dict:
    attempts = load_json_file(ATTEMPTS_FILE)
    return attempts.get(str(user_id), {})

def set_next_allowed_date(user_id: int, next_date: date) -> None:
    attempts = load_json_file(ATTEMPTS_FILE)
    key = str(user_id)
    attempts[key] = attempts.get(key, {})
    attempts[key]["next_allowed_date"] = next_date.isoformat()
    save_json_file(ATTEMPTS_FILE, attempts)

def clear_next_allowed_date(user_id: int) -> None:
    attempts = load_json_file(ATTEMPTS_FILE)
    key = str(user_id)
    if key in attempts and "next_allowed_date" in attempts[key]:
        attempts[key].pop("next_allowed_date", None)
        save_json_file(ATTEMPTS_FILE, attempts)

def can_start_test(user_id: int):
    attempt = get_user_attempt(user_id)
    next_allowed = attempt.get("next_allowed_date")
    if not next_allowed:
        return True, ""
    try:
        next_allowed_date = datetime.strptime(next_allowed, "%Y-%m-%d").date()
    except ValueError:
        return True, ""
    today = date.today()
    if today < next_allowed_date:
        return False, f"Сегодня повторная попытка недоступна.\nПопробуйте снова {next_allowed_date.strftime('%d.%m.%Y')}."
    return True, ""

def save_admin_message_link(admin_message_id: int, payload: dict) -> None:
    links = load_json_file(ADMIN_LINKS_FILE)
    links[str(admin_message_id)] = payload
    save_json_file(ADMIN_LINKS_FILE, links)

def get_admin_message_link(admin_message_id: int) -> dict | None:
    links = load_json_file(ADMIN_LINKS_FILE)
    return links.get(str(admin_message_id))

# =========================================================
# QUIZ HELPERS
# =========================================================
def main_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Начать тест", callback_data="start_quiz")]])

def build_question_keyboard(question_index: int):
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("A", callback_data=f"ans|{question_index}|0"),
            InlineKeyboardButton("B", callback_data=f"ans|{question_index}|1"),
            InlineKeyboardButton("C", callback_data=f"ans|{question_index}|2"),
            InlineKeyboardButton("D", callback_data=f"ans|{question_index}|3"),
        ]]
    )

def format_question(q_index: int, total: int, question: dict) -> str:
    options_text = "\n".join([f"{LETTERS[i]}. {option}" for i, option in enumerate(question["options"])])
    return f"Вопрос {q_index + 1} из {total}\n\n{question['q']}\n\n{options_text}"

async def render_question_message(query_or_message, context: ContextTypes.DEFAULT_TYPE):
    session = context.user_data.get("quiz_session")
    if not session:
        return

    idx = session["current"]
    total = len(session["questions"])
    question = session["questions"][idx]
    text = format_question(idx, total, question)
    keyboard = build_question_keyboard(idx)

    message_id = session.get("message_id")
    chat_id = session.get("chat_id")

    if message_id and chat_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
            )
            return
        except Exception as e:
            logger.warning("Could not edit question message: %s", e)

    sent = await query_or_message.message.reply_text(text, reply_markup=keyboard) if hasattr(query_or_message, "message") else await query_or_message.reply_text(text, reply_markup=keyboard)
    session["message_id"] = sent.message_id
    session["chat_id"] = sent.chat_id
    context.user_data["quiz_session"] = session

def reset_quiz(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("quiz_session", None)
    context.user_data.pop("stage", None)
    context.user_data.pop("full_name_latin", None)

async def send_result_to_admin_group(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str | None,
    full_name: str,
    linkedin: str,
    score: int,
    total: int,
):
    if not ADMIN_CHAT_ID:
        return

    text = (
        "✅ Новый успешно сданный тест\n\n"
        f"Telegram ID: {user_id}\n"
        f"Username: @{username if username else '—'}\n"
        f"Имя: {full_name}\n"
        f"LinkedIn: {linkedin}\n"
        f"Результат: {score}/{total}\n\n"
        "Чтобы отправить сертификат пользователю, ответьте НА ЭТО сообщение PDF-файлом."
    )

    try:
        sent = await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=text)
        save_admin_message_link(
            sent.message_id,
            {
                "user_id": user_id,
                "username": username or "",
                "full_name_latin": full_name,
                "linkedin": linkedin,
                "score": score,
                "total": total,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    except Exception as e:
        logger.warning("Could not send result to admin group: %s", e)

# =========================================================
# HANDLERS
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    allowed, reason = can_start_test(user.id)

    text = (
        "Привет! Это тест по курсу Web3 CM.\n\n"
        f"• В тесте будет {QUESTIONS_PER_TEST} случайных вопросов из банка 50\n"
        f"• Для успешной сдачи нужно набрать минимум {PASS_SCORE} правильных ответов\n"
        "• Если тест не пройден, повторная попытка будет доступна завтра\n"
        "• Если тест пройден, бот попросит имя и фамилию латиницей и ссылку на LinkedIn\n"
        "• После успешной сдачи данные уйдут в закрытую группу, откуда админ сможет отправить PDF-сертификат\n\n"
    )

    if not allowed:
        await update.message.reply_text(text + reason)
        return

    await update.message.reply_text(
        text + "Нажмите кнопку ниже, чтобы начать.",
        reply_markup=main_menu_keyboard(),
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    allowed, reason = can_start_test(user.id)
    if not allowed:
        await query.message.reply_text(reason)
        return

    questions = random.sample(QUESTION_BANK, QUESTIONS_PER_TEST)
    context.user_data["quiz_session"] = {
        "questions": questions,
        "current": 0,
        "score": 0,
        "total": QUESTIONS_PER_TEST,
        "message_id": None,
        "chat_id": query.message.chat_id,
    }
    context.user_data["stage"] = "quiz"

    await query.message.reply_text("Тест начался.\nВыбирайте вариант A / B / C / D.")
    await render_question_message(query, context)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if context.user_data.get("stage") != "quiz":
        await query.answer("Сначала начните тест заново через /start", show_alert=True)
        return

    session = context.user_data.get("quiz_session")
    if not session:
        await query.answer("Сессия не найдена. Нажмите /start", show_alert=True)
        return

    try:
        _, question_index_str, option_index_str = query.data.split("|")
        question_index = int(question_index_str)
        option_index = int(option_index_str)
    except Exception:
        await query.answer("Некорректный ответ", show_alert=True)
        return

    current_index = session["current"]
    if question_index != current_index:
        await query.answer("Этот вопрос уже закрыт", show_alert=True)
        return

    question = session["questions"][current_index]
    if option_index == question["correct"]:
        session["score"] += 1

    session["current"] += 1
    context.user_data["quiz_session"] = session

    if session["current"] < session["total"]:
        await render_question_message(query, context)
        return

    score = session["score"]
    total = session["total"]

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if score >= PASS_SCORE:
        context.user_data["stage"] = "await_name"
        await query.message.reply_text(
            f"✅ Тест пройден: {score}/{total}\n\n"
            "Введите имя и фамилию латиницей.\n"
            "Пример: Ivan Petrov"
        )
    else:
        tomorrow = date.today() + timedelta(days=1)
        set_next_allowed_date(query.from_user.id, tomorrow)
        reset_quiz(context)
        await query.message.reply_text(
            f"❌ Тест не пройден: {score}/{total}\n\n"
            f"Повторная попытка будет доступна завтра: {tomorrow.strftime('%d.%m.%Y')}."
        )

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stage = context.user_data.get("stage")
    text = (update.message.text or "").strip()

    if stage == "quiz":
        await update.message.reply_text("Во время теста используйте кнопки A / B / C / D под вопросом.")
        return

    if stage == "await_name":
        if not NAME_RE.fullmatch(text):
            await update.message.reply_text(
                "Введите имя и фамилию только латиницей.\nПример: Ivan Petrov"
            )
            return

        context.user_data["full_name_latin"] = text
        context.user_data["stage"] = "await_linkedin"
        await update.message.reply_text(
            "Отлично. Теперь отправьте ссылку на ваш LinkedIn.\n"
            "Пример: https://www.linkedin.com/in/your-name/"
        )
        return

    if stage == "await_linkedin":
        if not LINKEDIN_RE.fullmatch(text):
            await update.message.reply_text(
                "Нужна корректная ссылка на LinkedIn.\n"
                "Пример: https://www.linkedin.com/in/your-name/"
            )
            return

        session = context.user_data.get("quiz_session", {})
        full_name = context.user_data.get("full_name_latin", "")
        score = session.get("score", 0)
        total = session.get("total", QUESTIONS_PER_TEST)
        user = update.effective_user

        ensure_results_file()
        with RESULTS_FILE.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    user.id,
                    user.username or "",
                    full_name,
                    text,
                    score,
                    total,
                    "yes",
                ]
            )

        clear_next_allowed_date(user.id)

        await send_result_to_admin_group(
            context=context,
            user_id=user.id,
            username=user.username,
            full_name=full_name,
            linkedin=text,
            score=score,
            total=total,
        )

        reset_quiz(context)
        await update.message.reply_text(
            "✅ Данные сохранены.\n\n"
            "Результат отправлен в закрытую группу.\n"
            "После проверки админ сможет прислать вам PDF-сертификат."
        )
        return

    await update.message.reply_text("Нажмите /start, чтобы открыть тест.")

async def handle_admin_certificate_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not ADMIN_CHAT_ID:
        return

    try:
        admin_chat_id_int = int(ADMIN_CHAT_ID)
    except ValueError:
        logger.warning("ADMIN_CHAT_ID is invalid")
        return

    if message.chat_id != admin_chat_id_int:
        return

    if not message.reply_to_message:
        return

    replied_to_message_id = message.reply_to_message.message_id
    link_data = get_admin_message_link(replied_to_message_id)
    if not link_data:
        return

    document = message.document
    if not document:
        return

    is_pdf = (document.mime_type == "application/pdf") or (document.file_name and document.file_name.lower().endswith(".pdf"))
    if not is_pdf:
        await message.reply_text("Нужен PDF-файл. Ответьте на сообщение кандидата PDF-документом.")
        return

    user_id = link_data["user_id"]
    admin_caption = (message.caption or "").strip()

    caption = "✅ Ваш сертификат готов."
    if admin_caption:
        caption += f"\n\n{admin_caption}"

    try:
        await context.bot.send_document(
            chat_id=user_id,
            document=document.file_id,
            caption=caption,
        )
        await message.reply_text("Сертификат успешно отправлен пользователю.")
    except Exception as e:
        logger.warning("Could not send certificate to user %s: %s", user_id, e)
        await message.reply_text("Не удалось отправить сертификат пользователю. Возможно, он не запускал бота или заблокировал его.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_quiz(context)
    await update.message.reply_text("Текущая сессия сброшена. Нажмите /start, чтобы начать заново.")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не найден BOT_TOKEN. Задайте переменную окружения BOT_TOKEN.")

    ensure_results_file()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(start_quiz, pattern=r"^start_quiz$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^ans\|"))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_admin_certificate_reply))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
