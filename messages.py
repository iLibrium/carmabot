# messages.py
"""Common text messages for the Telegram bot."""

MAIN_MENU = "Главное меню:"
REQUEST_CONTACT = "Чтобы двигаться дальше, поделитесь, пожалуйста, своим контактом 📱"
NOT_REGISTERED = "❌ Вы не зарегистрированы."
REGISTRATION_SUCCESS = "✅ Регистрация успешна!"

ENTER_ISSUE_TITLE = "📋 Введите заголовок задачи:"
TITLE_EMPTY = "❌ Заголовок не может быть пустым. Повторите ввод:"
ENTER_ISSUE_DESCRIPTION = "📝 Введите описание задачи (или отправьте /skip):"
ASK_FOR_ATTACHMENTS = "📎 Прикрепите фото или нажмите 📤 Создать задачу:"
UNSUPPORTED_FILE = "❌ Поддерживаются только фото или документы."
FILES_UPLOADED = "📎 Загружено файлов: {count}. Добавьте ещё или нажмите 📤 Создать задачу."
TELEGRAM_DOWNLOAD_FAILED = "❌ Не удалось получить файл из Telegram. Попробуйте снова."
FILE_UPLOAD_FAILED = "❌ Не удалось загрузить файл. Попробуйте ещё раз…"
ALBUM_FILE_FAILED = "❌ Не удалось загрузить одно из фото. Отправьте альбом снова."

ISSUE_CREATED = (
    "✅ Задача {key} (https://tracker.yandex.ru/{key}) успешно создана!\n"
    "<b>Наименование:</b> {title}"
)
ISSUE_CREATION_ERROR = "❌ Ошибка при создании задачи. Попробуйте позже."

COMMENT_PROMPT = "📝 Напишите комментарий или прикрепите файл…"
NO_ISSUE_SELECTED = "❌ Сначала выберите задачу в списке."
COMMENT_ADDED = (
    "✅ Комментарий добавлен к задаче - <a href='https://tracker.yandex.ru/{issue_key}'>{summary}</a>"
)

NO_ISSUES = "📭 У вас нет задач."
ISSUES_LIST = "📂 Ваши задачи:"

TELEGRAM_ERROR = "⚠️ Ошибка связи с Telegram. Попробуйте ещё раз."

WEBHOOK_COMMENT = (
    "💬 Добавлен комментарий - <a href='https://tracker.yandex.ru/{issue_key}'>{issue_summary}</a>\n\n"
    "<blockquote>{text}</blockquote>\n\n"
    "<b>👤 Автор комментария:</b> {author}"
)
WEBHOOK_STATUS = (
    "🔄 Статус задачи - <a href='https://tracker.yandex.ru/{issue_key}'>{issue_summary}</a>\n\n"
    "<b>Новый статус:</b> {status_name}\n"
    "<b>Кто изменил:</b> {changed_by}"
)
