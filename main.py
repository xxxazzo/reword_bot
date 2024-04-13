# Импортируем необходимые классы.
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, filters, ContextTypes, CommandHandler, CallbackQueryHandler


# Определяем функцию-обработчик сообщений.
# У неё два параметра, updater, принявший сообщение и контекст - дополнительная информация о сообщении.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [[InlineKeyboardButton('Зарегистрироваться®️', callback_data='registration'),
                       InlineKeyboardButton('Войти✅', callback_data='login')],
                      [InlineKeyboardButton('Продолжить без регистрации👤', callback_data='without-registration')]]
    markup = InlineKeyboardMarkup(reply_keyboard)
    await update.message.reply_text(f'Добро пожаловать, {update.message.from_user['first_name']}!',
                                    reply_markup=markup)


async def cont(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.from_user['first_name'])


async def buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'without-registration':
        await query.edit_message_text(text=f"Неавторизированным пользователям доступен тол")


def main():
    # Создаём объект Application.
    # Вместо слова "TOKEN" надо разместить полученный от @BotFather токен
    print('main')
    application = Application.builder().token('7101164525:AAElPNjWnAgEbsF_h5WgpI3Rq825DGvKusQ').build()
    print('app')

    # Создаём обработчик сообщений типа filters.TEXT
    # из описанной выше асинхронной функции echo()
    # После регистрации обработчика в приложении
    # эта асинхронная функция будет вызываться при получении сообщения
    # с типом "текст", т. е. текстовых сообщений.

    # Регистрируем обработчик в приложении.
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('context', cont))
    application.add_handler(CallbackQueryHandler(buttons_handler))
    print('polling')
    # Запускаем приложение.
    application.run_polling()


# Запускаем функцию main() в случае запуска скрипта.
if __name__ == '__main__':
    main()
