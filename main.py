# Импортируем необходимые классы.
import datetime
import json
import random

import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, filters, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, \
    ConversationHandler

from data import db_session
from data.category import Category
from data.users import User
from data.words import Word, OwnWord
from reword_token import TOKEN

# Константы
CHOICE, TYPING_REPLY, REMEMBER, CALLBACK, RECEIVE_IMAGE = range(5)

INTERVALS = {0: 0,
             1: 20 * 60,  # 20 minutes
             2: 60 * 60,  # 1 hour
             3: 6 * 60 * 60,  # 6 hours
             4: 24 * 60 * 60,  # 1 day
             5: 7 * 24 * 60 * 60,  # 1 week
             6: 3 * 7 * 24 * 60 * 60  # 3 weeks
             }

TIME_STORAGE_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'


def add_user_if_not_added(user_name, chat_id):
    '''Добавление пользователя в базу данных, если его там ещё нету'''
    db_sess = db_session.create_session()
    if not db_sess.query(User).filter(User.chat_id == chat_id).first():
        new_user = User()
        new_user.name = user_name
        new_user.chat_id = chat_id
        db_sess.add(new_user)
        db_sess.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Начало работы бота'''
    add_user_if_not_added(update.message.from_user['first_name'], update.effective_chat.id)
    await update.message.reply_photo('static/img/reword_logo.png',
                                     caption=f'Добро пожаловать в reword, {update.message.from_user["first_name"]}!')
    await menu(update, context)


def make_reply_markup(markup_id, **kwargs) -> ReplyKeyboardMarkup:
    '''Функция для создания ReplyKeyboardMarkup'''
    if markup_id == 1:  # menu markup
        reply_keyboard = [['Учить 🎓'], ['Словарь 📚'], ['Переводчик 💬']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                   input_field_placeholder="Выберите пункт меню")
    elif markup_id == 2:  # learn section markup
        reply_keyboard = [[f'Изменить изучаемые категории 📝️({kwargs["category_text"]})'],
                          ['Учить новые слова 🆕', 'Повторить слова 🔁'],
                          ['Вернуться 🔙']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, input_field_placeholder='Выберите опцию')
    elif markup_id == 3:  # learn words markup
        reply_keyboard = [['Я уже знаю это слово', 'Начать учить это слово'],
                          ['Закончить']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                   input_field_placeholder='Выберите действие над словом')
    elif markup_id == 4:  # repeat words markup
        reply_keyboard = [['Написать ✏️', 'Выбрать из вариантов 🔢'], ['Показать перевод 👀'], ['Закончить']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                   input_field_placeholder='Выберите действие над словом')
    elif markup_id == 5:  # remember markup
        reply_keyboard = [['Я вспомнил это слово', 'Я не вспомнил это слово']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                   input_field_placeholder='Вспомнили ли вы это слово?')
    elif markup_id == 6:  # dictionary section markup
        reply_keyboard = [['Все категории 📄'], ['Добавить своё слово ➕'], ['Вернуться 🔙']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, input_field_placeholder='Выберите опцию')
    elif markup_id == 7:  # add word markup
        reply_keyboard = [['Слово на английском', 'Перевод'], ['Добавить картинку-ассоциацию 🖼'],
                          ['Сохранить слово 💾', 'Отмена ❌']]
        return ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                   input_field_placeholder='Добавьте или измените данные')
    elif markup_id == 8:  # translater markup
        phase = kwargs['phase']
        phases = {0: '🇷🇺 -> 🇬🇧', 1: '🇬🇧 -> 🇷🇺'}
        reply_keyboard = [['Ввести текст 📝'], [f'Переключить направление 🔄(Cейчас {phases[phase]})'],
                          ['Вернуться 🔙']]
        return ReplyKeyboardMarkup(reply_keyboard)


def make_inline_markup(markup_id, **kwargs) -> InlineKeyboardMarkup:
    '''Функция для создания InlineKeyboardMarkup'''
    if markup_id == 1:  # change categories markup
        chat_id = kwargs['chat_id']
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.chat_id == chat_id).first()
        all_categories = sorted(list(db_sess.query(Category)), key=lambda x: x.name)
        inline_keyboard = []
        for category in all_categories:
            symbol = '✅' if category in list(user.categories_studied) else '☑️'
            button_text = symbol + ' ' + category.name
            inline_keyboard.append(
                [InlineKeyboardButton(button_text, callback_data=f'change_categories {category.id}')])
        if user.own_words_studied:
            inline_keyboard.insert(0,
                                   [InlineKeyboardButton('✅ Мои слова 📖', callback_data='change_categories OwnWords')])
        else:
            inline_keyboard.insert(0,
                                   [InlineKeyboardButton('☑️ Мои слова 📖',
                                                         callback_data='change_categories OwnWords')])
        inline_keyboard.append([InlineKeyboardButton('Подтвердить ✔️', callback_data='change_categories OK')])
        return InlineKeyboardMarkup(inline_keyboard)
    elif markup_id == 2:  # repeat quiz markup
        main_word = kwargs['main_word']
        db_sess = db_session.create_session()
        if type(main_word) is Word:
            options = random.sample(list(db_sess.query(Word).filter(Word.id != main_word.id)), k=3)
        else:
            options = random.sample(list(db_sess.query(Word).all()), k=3)
        main_word_correct_id = random.randint(0, 3)
        options.insert(main_word_correct_id, main_word)
        inline_keyboard = []
        for i in range(2):
            row = []
            for j in range(2):
                if 2 * i + j == main_word_correct_id:
                    row.append(InlineKeyboardButton(main_word.word, callback_data='repeat_quiz CORRECT'))
                else:
                    row.append(InlineKeyboardButton(options[2 * i + j].word,
                                                    callback_data=f'repeat_quiz {options[2 * i + j].word} WRONG'))
            inline_keyboard.append(row)
        return InlineKeyboardMarkup(inline_keyboard)
    elif markup_id == 3:
        db_sess = db_session.create_session()
        inline_keyboard = []
        all_categories = sorted(db_sess.query(Category).all(), key=lambda category: category.name)
        if len(all_categories) % 2:
            inline_keyboard.append([InlineKeyboardButton('Мои слова 📖', callback_data='open_category OwnWords'),
                                    InlineKeyboardButton(all_categories[0].name,
                                                         callback_data=f'open_category {all_categories[0].id}')])
            for i in range(len(all_categories) // 2):
                row = []
                for j in range(1, 3):
                    row.append(InlineKeyboardButton(all_categories[2 * i + j].name,
                                                    callback_data=f'open_category {all_categories[2 * i + j].id}'))
                inline_keyboard.append(row)
        else:
            inline_keyboard.append([InlineKeyboardButton('Мои слова 📖', callback_data='open_category OwnWords')])
            for i in range(len(all_categories) // 2):
                row = []
                for j in range(2):
                    row.append(InlineKeyboardButton(all_categories[2 * i + j].name,
                                                    callback_data=f'open_category {all_categories[2 * i + j].id}'))
                inline_keyboard.append(row)
        inline_keyboard.append([InlineKeyboardButton('Вернуться 🔙', callback_data='back_to_dictionary_section')])
        return InlineKeyboardMarkup(inline_keyboard)
    elif markup_id == 4:
        inline_keyboard = [[InlineKeyboardButton('Вернуться 🔙', callback_data='back_to_categories_section')]]
        return InlineKeyboardMarkup(inline_keyboard)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработчик команды /menu'''
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Выберите пункт меню',
                                   reply_markup=make_reply_markup(1))


async def learn_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области для изучения/повторения слов'''
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
    categoties_count = len(user.categories_studied)
    categoties_count += 1 if user.own_words_studied else 0
    categories_texts = {0: 'Выбрано xxx категорий',
                        1: 'Выбрана xxx категория',
                        2: 'Выбрано xxx категории',
                        3: 'Выбрано xxx категории',
                        4: 'Выбрано xxx категории',
                        5: 'Выбрано xxx категорий',
                        6: 'Выбрано xxx категорий',
                        7: 'Выбрано xxx категорий',
                        8: 'Выбрано xxx категорий',
                        9: 'Выбрано xxx категорий'}
    if categoties_count in range(11, 20):
        category_text = categories_texts[0].replace('xxx', str(categoties_count))
    else:
        category_text = categories_texts[categoties_count % 10].replace('xxx', str(categoties_count))
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Выберите опцию',
                                   reply_markup=make_reply_markup(2, category_text=category_text))


async def cc_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):  # change categories callback handler
    '''Обработчик callback для изменения изучаемых категорий'''
    query = update.callback_query
    if query.data.split()[1] == 'OK':
        await query.answer('Изменения сохранены')
        await query.delete_message()
        await learn_section(update, context)
    else:
        db_sess = db_session.create_session()
        user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
        if query.data.split()[1] == 'OwnWords':
            if user.own_words_studied:
                user.own_words_studied = False
                await query.answer(f'Категория Мои слова 📖 была удалена из ваших категорий')
            else:
                user.own_words_studied = True
                await query.answer(f'Категория Мои слова 📖 была добавлена в ваши категории')
        else:
            category_id = int(query.data.split()[1])
            category = db_sess.query(Category).filter(Category.id == category_id).first()
            if category in user.categories_studied:
                user.categories_studied.remove(category)
                await query.answer(f'Категория {category.name} была удалена из ваших категорий')
            else:
                user.categories_studied.append(category)
                await query.answer(f'Категория {category.name} была добавлена в ваши категории')
        db_sess.commit()
        await query.edit_message_reply_markup(make_inline_markup(1, chat_id=update.effective_chat.id))


async def change_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области для изменения изучаемых категорий'''
    await update.message.reply_text("Выберите категории",
                                    reply_markup=make_inline_markup(1, chat_id=update.effective_chat.id))


async def learn_new_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области для изучения новых слов'''
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
    if not user.categories_studied and not user.categories_studied:
        await update.message.reply_text('<b>У тебя выбрано 0 категорий для изучения 🫢</b>', parse_mode=ParseMode.HTML)
        await change_categories(update, context)
        return ConversationHandler.END
    else:
        if await new_word(update, context) == CHOICE:
            return CHOICE
        await update.message.reply_text('<b>У тебя закончились слова для изучения 🫢</b>',
                                        parse_mode=ParseMode.HTML)
        await learn_section(update, context)
        return ConversationHandler.END


async def new_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Новое слово для изучения'''
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
    words_for_studying = []
    for category in user.categories_studied:
        for word in category.words:
            if str(update.effective_chat.id) not in json.loads(word.progress):
                words_for_studying.append(word)
    if user.own_words_studied:
        words_for_studying.extend([word for word in user.own_words if json.loads(word.progress) == [None, None]])
    if words_for_studying:
        word = random.choice(words_for_studying)
        context.user_data['last_word_data'] = (word.id, type(word))
        text = f'Новое слово:\n<b>{word.word}</b> - <b>{word.translation}</b>'
        if type(word) is Word and json.loads(word.examples):
            text += '\n\nПримеры:'
            for en_ex, ru_ex in json.loads(word.examples):
                text += f'\n-<b>{en_ex}</b>\n {ru_ex}'
        if word.image:
            await update.message.reply_photo(word.image, caption=text, reply_markup=make_reply_markup(3),
                                             parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, reply_markup=make_reply_markup(3), parse_mode=ParseMode.HTML)
        return CHOICE
    return ConversationHandler.END


async def already_known(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Если пользователь уже знает это слово, то оно не попадётся ему при повторении'''
    word_id, word_type = context.user_data['last_word_data']
    db_sess = db_session.create_session()
    if word_type is OwnWord:
        word = db_sess.query(OwnWord).filter(OwnWord.id == word_id).first()
        word.progress = [-1, None]
    else:
        word = db_sess.query(Word).filter(Word.id == word_id).first()
        progress = json.loads(word.progress)
        progress[str(update.effective_chat.id)] = [-1, None]
        word.progress = json.dumps(progress)
    db_sess.commit()
    if await new_word(update, context) == CHOICE:
        return CHOICE
    await update.message.reply_text('<b>У тебя закончились слова для изучения 🫢</b>',
                                    parse_mode=ParseMode.HTML)
    await learn_section(update, context)
    return ConversationHandler.END


async def start_learn_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Если пользователь не знает это слово, оно попадётся ему при повторении'''
    word_id, word_type = context.user_data['last_word_data']
    db_sess = db_session.create_session()
    if word_type is OwnWord:
        word = db_sess.query(OwnWord).filter(OwnWord.id == word_id).first()
        start_time = datetime.datetime.now().strftime(TIME_STORAGE_FORMAT)  # Время добавления слова в изучаемые
        word.progress = json.dumps([0, start_time])
    else:
        word = db_sess.query(Word).filter(Word.id == word_id).first()
        progress = json.loads(word.progress)
        start_time = datetime.datetime.now().strftime(TIME_STORAGE_FORMAT)  # Время добавления слова в изучаемые
        progress[str(update.effective_chat.id)] = [0, start_time]
        word.progress = json.dumps(progress)
    db_sess.commit()
    if await new_word(update, context) == CHOICE:
        return CHOICE
    await update.message.reply_text('<b>У тебя закончились слова для изучения 🫢</b>',
                                    parse_mode=ParseMode.HTML)
    await learn_section(update, context)
    return ConversationHandler.END


async def stop_learning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Выход из области изучения слов'''
    if 'last_word_data' in context.user_data:
        del context.user_data['last_word_data']
    await update.message.reply_text('Не забудь повторить эти слова!', reply_markup=ReplyKeyboardRemove())
    await learn_section(update, context)
    return ConversationHandler.END


def get_words_for_repeating(chat_id) -> list:
    '''Функция получения слов для повторения'''
    db_sess = db_session.create_session()
    words_for_repeating = []
    for word in db_sess.query(Word).all():
        progress_data = json.loads(word.progress).get(str(chat_id), [None, None])
        if progress_data[0] not in range(7):
            continue
        last_repeat = datetime.datetime.strptime(progress_data[1], TIME_STORAGE_FORMAT)
        delta = datetime.timedelta(seconds=INTERVALS[progress_data[0]])
        if last_repeat + delta <= datetime.datetime.now():
            words_for_repeating.append(word)
    user = db_sess.query(User).filter(User.chat_id == chat_id).first()
    for word in user.own_words:
        progress_data = json.loads(word.progress)
        if progress_data[0] not in range(7):
            continue
        last_repeat = datetime.datetime.strptime(progress_data[1], TIME_STORAGE_FORMAT)
        delta = datetime.timedelta(seconds=INTERVALS[progress_data[0]])
        if last_repeat + delta <= datetime.datetime.now():
            words_for_repeating.append(word)
    return words_for_repeating


async def do_you_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Функция, добавляющая прогресс слову, если пользователь его вспомнил'''
    if update.message.text == 'Я вспомнил это слово':
        word_id, word_type = context.user_data['last_word_data']
        db_sess = db_session.create_session()
        if word_type is OwnWord:
            word = db_sess.query(OwnWord).filter(OwnWord.id == word_id).first()
            progress_value, last_repeat = json.loads(word.progress)
            progress_value += 1
            last_repeat = datetime.datetime.now().strftime(TIME_STORAGE_FORMAT)
            word.progress = json.dumps([progress_value, last_repeat])
            db_sess.commit()
        else:
            word = db_sess.query(Word).filter(Word.id == word_id).first()
            progress = json.loads(word.progress)
            progress_value, last_repeat = progress[str(update.effective_chat.id)]
            progress_value += 1
            last_repeat = datetime.datetime.now().strftime(TIME_STORAGE_FORMAT)
            progress[str(update.effective_chat.id)] = [progress_value, last_repeat]
            word.progress = json.dumps(progress)
            db_sess.commit()
    else:  # Если пользователь не вспомнил слово, то ничего не должно произойти
        pass
    if await word_for_repeat(update, context) == CHOICE:
        return CHOICE
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='<b>У тебя закончились доступные слова для повторения 🫢</b>',
                                   parse_mode=ParseMode.HTML)
    await learn_section(update, context)
    return ConversationHandler.END


async def word_for_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Слово для повторения'''
    words_for_repeating = get_words_for_repeating(update.effective_chat.id)
    if words_for_repeating:
        word = random.choice(words_for_repeating)
        context.user_data['last_word_data'] = (word.id, type(word))
        text = f'Слово на русском: <b>{word.translation}</b>'
        if word.image:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=word.image, caption=text,
                                         reply_markup=make_reply_markup(4), parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                           reply_markup=make_reply_markup(4), parse_mode=ParseMode.HTML)
        return CHOICE
    else:
        return ConversationHandler.END


async def repeat_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие секции для повторения слов'''
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
    if not get_words_for_repeating(user.chat_id):
        await update.message.reply_text('<b>У тебя нету доступных слов для повторения 🫢</b>',
                                        parse_mode=ParseMode.HTML)
        await learn_section(update, context)
        return ConversationHandler.END
    else:
        return await word_for_repeat(update, context)


async def enter_translation_during_repeating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработка введённого пользователем перевода'''
    user_en_translation = update.message.text
    db_sess = db_session.create_session()
    word_id, word_type = context.user_data['last_word_data']
    if word_type is OwnWord:
        word = db_sess.query(OwnWord).filter(OwnWord.id == word_id).first()
        if ' '.join(' '.join(word.word.split()).split('-')).removeprefix('to ') == ' '.join(
                ' '.join(user_en_translation.split()).split('-')).removeprefix('to '):
            await update.message.reply_text(f'✅ Правильно!', reply_markup=make_reply_markup(5))
        else:
            await update.message.reply_text(f'❌ Упс..\nПравильный перевод: {word.word}',
                                            reply_markup=make_reply_markup(5))
    else:
        word = db_sess.query(Word).filter(Word.id == word_id).first()
        if ' '.join(' '.join(word.word.split()).split('-')).removeprefix('to ') == ' '.join(
                ' '.join(user_en_translation.split()).split('-')).removeprefix('to '):
            await update.message.reply_text(f'✅ Правильно!', reply_markup=make_reply_markup(5))
        else:
            await update.message.reply_text(f'❌ Упс..\nПравильный перевод: {word.word}',
                                            reply_markup=make_reply_markup(5))
    return REMEMBER


async def choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработчик способа повторения слова'''
    if update.message.text == 'Написать ✏️':
        await update.message.reply_text('Напишите перевод слова:')
        return TYPING_REPLY
    elif update.message.text == 'Выбрать из вариантов 🔢':
        db_sess = db_session.create_session()
        main_word_id, main_word_type = context.user_data['last_word_data']
        if main_word_type is OwnWord:
            main_word = db_sess.query(OwnWord).filter(OwnWord.id == main_word_id).first()
        else:
            main_word = db_sess.query(Word).filter(Word.id == main_word_id).first()
        await update.message.reply_text('Выбери правильный перевод из предложенных:',
                                        reply_markup=make_inline_markup(2, main_word=main_word))
        return CALLBACK
    elif update.message.text == 'Показать перевод 👀':
        db_sess = db_session.create_session()
        word_id, word_type = context.user_data['last_word_data']
        if word_type is OwnWord:
            word = db_sess.query(OwnWord).filter(OwnWord.id == word_id).first()
        else:
            word = db_sess.query(Word).filter(Word.id == word_id).first()
        text = f'Слово:\n<b>{word.word}</b> - <b>{word.translation}</b>'
        if word_type is Word and json.loads(word.examples):
            text += '\n\nПримеры:'
            for en_ex, ru_ex in json.loads(word.examples):
                text += f'\n-<b>{en_ex}</b>\n {ru_ex}'
        await update.message.reply_text(text, reply_markup=make_reply_markup(5), parse_mode=ParseMode.HTML)
        return REMEMBER


async def repeat_quiz_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработчик callback для способа повторения с вариантами ответа'''
    query = update.callback_query
    if query.data.split()[-1] == 'CORRECT':
        await query.answer('✅')
        await context.bot.send_message(chat_id=update.effective_chat.id, text='✅ Правильно!',
                                       reply_markup=make_reply_markup(5))
    else:
        db_sess = db_session.create_session()
        word_id, word_type = context.user_data['last_word_data']
        if word_type is OwnWord:
            word = db_sess.query(OwnWord).filter(OwnWord.id == word_id).first()
        else:
            word = db_sess.query(Word).filter(Word.id == word_id).first()
        await query.answer('❌')
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=f'❌ Упс..\nТвой выбор: {query.data.split()[1]}\nПравильный перевод: {word.word}',
                                       reply_markup=make_reply_markup(5))
    await query.delete_message()
    return REMEMBER


async def stop_repeating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Выход из области повторения слов'''
    if 'last_word_data' in context.user_data:
        del context.user_data['last_word_data']
    await update.message.reply_text('Не забудь учить новые слова!', reply_markup=ReplyKeyboardRemove())
    await learn_section(update, context)
    return ConversationHandler.END


async def dictionary_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области для добавления/просмотра слов(словарной области)'''
    await context.bot.send_message(chat_id=update.effective_chat.id, text='Выберите опцию',
                                   reply_markup=make_reply_markup(6, chat_id=update.effective_chat.id))


async def categories_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области для просмотра всех категорий'''
    await update.message.reply_text('Выбери категорию, чтобы посмотреть слова в ней:',
                                    reply_markup=make_inline_markup(3, chat_id=update.effective_chat.id))
    return CALLBACK


async def open_category_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработчик callback для откытия категории и просмотра слов'''
    query = update.callback_query
    await query.answer()
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
    if query.data.split()[-1] == 'OwnWords':
        text = 'Слова в категории Мои слова 📖:'
        for word in user.own_words:
            text += f'\n<b>{word.word}</b> - <b>{word.translation}</b>'
        if not user.own_words:
            text += '\nТут пусто 🕸'
        max_len = len(max(text.split('\n'), key=lambda string: len(string)))
        text = ('\n' + min(int(max_len // 2), 28) * '—' + '\n').join(text.split('\n'))
        await query.edit_message_text(text, reply_markup=make_inline_markup(4), parse_mode=ParseMode.HTML)
    else:
        category_id = int(query.data.split()[-1])
        category = db_sess.query(Category).filter(Category.id == category_id).first()
        text = f'Слова в категории {category.name}:'
        for i in range(len(category.words)):
            text += '($#$)'  # ($#$) - метка, куда нужно вставить разделительную линию
            word = category.words[i]
            text += f'<b>{word.word}</b> - <b>{word.translation}</b>'
            if json.loads(word.examples):
                text += '\nПримеры:'
                for en_ex, ru_ex in json.loads(word.examples):
                    text += f'\n-<b>{en_ex}</b>\n {ru_ex}'
        if not category.words:
            text += '($#$)Тут пусто 🕸'
        max_len = len(max(text.split('($#$)'), key=lambda string: len(string)))
        text = ('\n' + min(int(max_len // 2), 28) * '—' + '\n').join(text.split('($#$)'))
        await query.edit_message_text(text, reply_markup=make_inline_markup(4), parse_mode=ParseMode.HTML)


async def back_to_categories_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Выход из области просмотра слов в категории и переход в область просмотра категорий'''
    query = update.callback_query
    await query.answer()
    await query.edit_message_text('Выбери категорию, чтобы посмотреть слова в ней:',
                                  reply_markup=make_inline_markup(3, chat_id=update.effective_chat.id))
    return CALLBACK


async def back_to_dictionary_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Выход из области просмотра категорий и переход в меню словарной области'''
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    await dictionary_section(update, context)
    return ConversationHandler.END


async def add_word_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области для добавления своего слова'''
    await update.message.reply_text('Добавьте или измените данные', reply_markup=make_reply_markup(7))
    return CHOICE


async def regular_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработчик способа для введения данных, которые пользователь хочет ввести'''
    section = update.message.text
    if section == 'Слово на английском':
        context.user_data['info'] = 'EN'
        if context.user_data.get('EN', False):
            await update.message.reply_text(
                f'Ранее было введено: {context.user_data.get("EN")}\nВведите слово на английском(можно будет изменить):',
                reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text('Введите слово на английском(можно будет изменить):',
                                            reply_markup=ReplyKeyboardRemove())
        return TYPING_REPLY
    elif section == 'Перевод':
        context.user_data['info'] = 'RU'
        if context.user_data.get('RU', False):
            await update.message.reply_text(
                f'Ранее было введено: {context.user_data.get("RU")}\nВведите перевод на русском(можно будет изменить):',
                reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text('Введите перевод на русском(можно будет изменить):',
                                            reply_markup=ReplyKeyboardRemove())
        return TYPING_REPLY
    elif section == 'Добавить картинку-ассоциацию 🖼':
        await update.message.reply_text(
            'Отправьте картинку-ассоциацию(будет показываться при изучении/повторении слова):',
            reply_markup=ReplyKeyboardRemove())
        return RECEIVE_IMAGE


async def receive_information(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Получение информации и запись её в словарь context.user_data для хранения до сохранения слова'''
    context.user_data[context.user_data['info']] = update.message.text.lower().strip()
    await update.message.reply_text('Изменения сохранены✅')
    return await add_word_section(update, context)


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Получение картинки и запись файла в словарь context.user_data для хранения до сохранения слова'''
    file_id = update.message.photo[-1].file_id
    new_file = await context.bot.get_file(file_id)
    context.user_data['image'] = new_file
    await update.message.reply_text('Изменения сохранены✅')
    return await add_word_section(update, context)


async def save_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Сохранение слова'''
    if not (context.user_data.get('RU', False) and context.user_data.get('EN', False)):
        await update.message.reply_text('<b>НЕ ЗАПОЛНЕНО ОБЯЗАТЕЛЬНОЕ ПОЛЕ</b>', reply_markup=make_reply_markup(7),
                                        parse_mode=ParseMode.HTML)
        return CHOICE
    db_sess = db_session.create_session()
    user = db_sess.query(User).filter(User.chat_id == update.effective_chat.id).first()
    new_own_word = OwnWord()
    new_own_word.word = context.user_data['EN']
    new_own_word.translation = context.user_data['RU']
    new_own_word.user_id = user.id
    if context.user_data.get('image', False):
        filename = f'{update.effective_chat.id}_{datetime.datetime.now().strftime("%H%M%S%j%Y")}.jpg'
        path = f'static/users_img/{filename}'
        try:
            await context.user_data['image'].download_to_drive(path)
            new_own_word.image = path
            await update.message.reply_text('Слово <b>успешно</b> сохранено в категорию Мои слова 📖',
                                            parse_mode=ParseMode.HTML)
        except Exception:
            await update.message.reply_text(
                '::Возникла проблема с сохранением картинки\n::'
                'Слово сохранено <b>без картинки</b> в категорию Мои слова 📖',
                parse_mode=ParseMode.HTML)
    user.own_words.append(new_own_word)
    db_sess.add(new_own_word)
    db_sess.commit()
    await dictionary_section(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Выход из области добавления своего слова без сохранения'''
    context.user_data.pop('EN', 0)
    context.user_data.pop('RU', 0)
    context.user_data.pop('photo', 0)
    await dictionary_section(update, context)
    return ConversationHandler.END


async def translater_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Открытие области с переводчиком'''
    context.user_data['phase'] = 0
    await update.message.reply_text('Выберите опцию:', reply_markup=make_reply_markup(8, phase=0))
    return CHOICE


async def translate_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Обработчик следующего действия'''
    section = update.message.text
    if section == 'Ввести текст 📝':
        phase = context.user_data['phase']
        phases = {0: '🇷🇺 -> 🇬🇧', 1: '🇬🇧 -> 🇷🇺'}
        await update.message.reply_text(f'Введите текст для перевода({phases[phase]})',
                                        reply_markup=ReplyKeyboardRemove())
        return TYPING_REPLY
    elif 'Переключить направление 🔄' in section:
        context.user_data['phase'] += 1
        context.user_data['phase'] %= 2
        phase = context.user_data['phase']
        phases = {0: '🇷🇺 -> 🇬🇧', 1: '🇬🇧 -> 🇷🇺'}
        await update.message.reply_text(f'Направление изменено на {phases[phase]}',
                                        reply_markup=make_reply_markup(8, phase=phase))
        return CHOICE


async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Отправка и получение запроса перевода с помощью API https://ftapi.pythonanywhere.com'''
    text = update.message.text
    if context.user_data['phase']:
        request = f'https://ftapi.pythonanywhere.com/translate?sl=en&dl=ru&text={text}'
    else:
        request = f'https://ftapi.pythonanywhere.com/translate?sl=ru&dl=en&text={text}'
    try:
        response = requests.get(request)
    except Exception:
        await update.message.reply_text('Упс.. Какая-то ошибка‼️',
                                        reply_markup=make_reply_markup(8, phase=context.user_data['phase']))
        return CHOICE
    if not response:
        await update.message.reply_text('Упс.. Какая-то ошибка‼️',
                                        reply_markup=make_reply_markup(8, phase=context.user_data['phase']))
        return CHOICE
    await update.message.reply_text(f'Перевод:\n\n{response.json()["destination-text"]}',
                                    reply_markup=make_reply_markup(8, phase=context.user_data['phase']))
    return CHOICE


async def leave_translater_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''Выход из области переводчика'''
    context.user_data.pop('phase', 0)
    await menu(update, context)
    return ConversationHandler.END


async def helping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    '''/help'''
    await update.message.reply_text('/menu - меню бота')


def main():
    db_session.global_init('db/database.db')
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', helping))
    application.add_handler(CommandHandler('menu', menu))
    application.add_handler(MessageHandler(filters.Regex('^(Учить 🎓)$'), learn_section))
    learn_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(Учить новые слова 🆕)$'), learn_new_words)],
        states={CHOICE: [MessageHandler(filters.Regex('^(Я уже знаю это слово)$'), already_known),
                         MessageHandler(filters.Regex('^(Начать учить это слово)$'), start_learn_word)]},
        fallbacks=[MessageHandler(filters.Regex('^(Закончить)$'), stop_learning)])
    application.add_handler(learn_conv)
    # Здесь может вылезти ошибка, но это не ошибка, просто предупреждение, что CallbackQueryHandler
    # не будет принимать callback'и извне диалога, никак не влияет на работу
    repeat_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(Повторить слова 🔁)$'), repeat_words)],
        states={
            CHOICE: [
                MessageHandler(filters.Regex('^(Написать ✏|Выбрать из вариантов 🔢|Показать перевод 👀)'), choice)],
            TYPING_REPLY: [
                MessageHandler(
                    filters.TEXT & ~(filters.COMMAND | filters.Regex("^(Закончить)$")),
                    enter_translation_during_repeating)],
            REMEMBER: [
                MessageHandler(filters.Regex('^(Я вспомнил это слово|Я не вспомнил это слово)'), do_you_remember)],
            CALLBACK: [CallbackQueryHandler(repeat_quiz_callback_handler, '^(repeat_quiz)')]},
        fallbacks=[MessageHandler(filters.Regex('^(Закончить)$'), stop_repeating)]
    )
    application.add_handler(repeat_conv)
    # Здесь может вылезти ошибка, но это не ошибка, просто предупреждение, что CallbackQueryHandler
    # не будет принимать callback'и извне диалога, никак не влияет на работу
    categories_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(Все категории 📄)$'), categories_section)],
        states={CALLBACK: [CallbackQueryHandler(open_category_callback_handler, '^(open_category)'),
                           CallbackQueryHandler(back_to_categories_section, '^(back_to_categories_section)$')]},
        fallbacks=[CallbackQueryHandler(back_to_dictionary_section, '^(back_to_dictionary_section)$')]
    )
    application.add_handler(categories_conv)
    add_word_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(Добавить своё слово ➕)$'), add_word_section)],
        states={
            CHOICE: [MessageHandler(filters.Regex('^(Слово на английском|Перевод|Добавить картинку-ассоциацию 🖼)$'),
                                    regular_choice)],
            TYPING_REPLY: [
                MessageHandler(filters.TEXT & ~(filters.COMMAND | filters.Regex("^(Сохранить слово 💾|Отмена ❌)$")),
                               receive_information)],
            RECEIVE_IMAGE: [MessageHandler(filters.PHOTO, receive_image)]},
        fallbacks=[MessageHandler(filters.Regex('^(Отмена ❌)$'), cancel),
                   MessageHandler(filters.Regex('^(Сохранить слово 💾)$'), save_word)])
    application.add_handler(add_word_conv)
    translater_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(Переводчик 💬)$'), translater_section)],
        states={
            CHOICE: [MessageHandler(filters.Regex('^(Ввести текст 📝|Переключить направление 🔄)'), translate_choice)],
            TYPING_REPLY: [MessageHandler(
                filters.TEXT & ~(filters.COMMAND | filters.Regex("^(Вернуться 🔙)$")),
                translate)]},
        fallbacks=[MessageHandler(filters.Regex("^(Вернуться 🔙)$"), leave_translater_section)]
    )
    application.add_handler(translater_conv)
    application.add_handler(MessageHandler(filters.Regex('^(Словарь 📚)$'), dictionary_section))
    application.add_handler(MessageHandler(filters.Regex('^(Вернуться 🔙)$'), menu))
    application.add_handler(MessageHandler(filters.Regex('^(Изменить изучаемые категории 📝)'), change_categories))
    application.add_handler(CallbackQueryHandler(cc_callback_handler, '^(change_categories)'))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


# Запускаем функцию main() в случае запуска скрипта.
if __name__ == '__main__':
    main()
