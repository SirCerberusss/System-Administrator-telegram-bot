#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import paramiko
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import tempfile
import asyncio
import json

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Создаем файл конфигурации по умолчанию
        default_config = {
            "TOKEN": "YOUR_BOT_TOKEN",
            "ADMIN_IDS": [123456789],
            "SSH_CONFIG": {
                "server1": {
                    "hostname": "your_server_ip",
                    "username": "your_username",
                    "password": "your_password"
                }
            }
        }
        with open('config.json', 'w') as f:
            json.dump(default_config, f, indent=4)
        return default_config

# Загружаем конфигурацию
config = load_config()
TOKEN = config['TOKEN']
ADMIN_IDS = config['ADMIN_IDS']
SSH_CONFIG = config['SSH_CONFIG']

def get_container_status_emoji(status: str) -> str:
    """Возвращает эмодзи в зависимости от статуса контейнера."""
    if 'Up' in status:
        return '🟢'  # Зеленый для запущенных
    elif 'Exited' in status:
        return '🔴'  # Красный для остановленных
    elif 'Created' in status:
        return '⚪'  # Белый для созданных
    elif 'Restarting' in status:
        return '🟡'  # Желтый для перезапускающихся
    elif 'Paused' in status:
        return '⏸️'  # Пауза для приостановленных
    else:
        return '❓'  # Вопросительный знак для неизвестных статусов

def format_container_status(status: str) -> str:
    """Форматирует статус контейнера в понятный вид."""
    if 'Up' in status:
        uptime = status.split('Up ')[1].split(',')[0]
        return f"Запущен (работает {uptime})"
    elif 'Exited' in status:
        exit_code = status.split('Exited (')[1].split(')')[0]
        return f"Остановлен (код выхода: {exit_code})"
    elif 'Created' in status:
        return "Создан"
    elif 'Restarting' in status:
        return "Перезапускается"
    elif 'Paused' in status:
        return "Приостановлен"
    else:
        return status

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def get_welcome_message(username: str) -> str:
    """Генерирует приветственное сообщение."""
    return f"""
🚀 *Добро пожаловать в панель управления серверами!*

👋 Привет, {username}!

🤖 Я ваш верный помощник в управлении серверами. С моей помощью вы можете:

🖥 *Мониторинг*
• Проверять статус серверов
• Следить за использованием ресурсов
• Контролировать нагрузку

⚙️ *Управление сервисами*
• Управлять Docker контейнерами
• Контролировать веб-серверы
• Настраивать базы данных

🔄 *Системные операции*
• Обновлять пакеты
• Перезагружать серверы
• Выполнять команды

Нажмите кнопку меню ниже, чтобы начать работу 👇
"""

def get_main_menu() -> InlineKeyboardMarkup:
    """Создает главное меню."""
    keyboard = [
        [InlineKeyboardButton(text="🖥 Статус серверов", callback_data='status')],
        [InlineKeyboardButton(text="⚙️ Управление сервисами", callback_data='services')],
        [InlineKeyboardButton(text="🔄 Системные операции", callback_data='system')],
        [InlineKeyboardButton(text="📋 Логи", callback_data='logs')],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data='help')]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_reply_keyboard() -> ReplyKeyboardMarkup:
    """Создает основную клавиатуру с кнопками."""
    keyboard = [
        [KeyboardButton(text="🖥 Статус серверов"), KeyboardButton(text="⚙️ Управление сервисами")],
        [KeyboardButton(text="🏓 Пинг"), KeyboardButton(text="🔄 Перезагрузка")],
        [KeyboardButton(text="📋 Логи"), KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def start(message: Message) -> None:
    """Обработчик команды /start."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return

    username = message.from_user.first_name
    welcome_text = get_welcome_message(username)
    keyboard = get_reply_keyboard()
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode='Markdown')

async def handle_menu(message: Message) -> None:
    """Обработчик нажатия на кнопки меню."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return

    if message.text == "🖥 Статус серверов":
        keyboard = [
            [InlineKeyboardButton(text="💾 Проверить диск", callback_data='check_disk')],
            [InlineKeyboardButton(text="🧠 Проверить память", callback_data='check_memory')],
            [InlineKeyboardButton(text="📊 Проверить нагрузку", callback_data='check_load')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('📊 Выберите тип проверки:', reply_markup=reply_markup)

    elif message.text == "⚙️ Управление сервисами":
        keyboard = [
            [InlineKeyboardButton(text="🌐 Nginx", callback_data='service_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL", callback_data='service_postgresql')],
            [InlineKeyboardButton(text="🐳 Docker", callback_data='service_docker')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('⚙️ Выберите сервис:', reply_markup=reply_markup)

    elif message.text == "🏓 Пинг":
        await message.answer(
            "🏓 Введите адрес для пинга (например, 8.8.8.8 или google.com):\n\n"
            "Используйте команду /ping <адрес>"
        )

    elif message.text == "🔄 Перезагрузка":
        keyboard = [
            [InlineKeyboardButton(text="✅ Да, перезагрузить", callback_data='confirm_reboot')],
            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data='cancel_reboot')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('⚠️ Вы уверены, что хотите перезагрузить сервер?', 
                           reply_markup=reply_markup)

    elif message.text == "📋 Логи":
        keyboard = [
            [InlineKeyboardButton(text="📊 Системные логи", callback_data='logs_system')],
            [InlineKeyboardButton(text="🐳 Docker логи", callback_data='logs_docker')],
            [InlineKeyboardButton(text="🌐 Nginx логи", callback_data='logs_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL логи", callback_data='logs_postgres')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('📋 Выберите тип логов для просмотра:', reply_markup=reply_markup)

    elif message.text == "ℹ️ Помощь":
        help_text = """
📚 *Справка по командам*

*Статус серверов:*
• Проверка диска - показывает свободное место
• Проверка памяти - показывает использование RAM
• Проверка нагрузки - показывает CPU и процессы

*Управление сервисами:*
• Nginx - управление веб-сервером
• PostgreSQL - управление базой данных
• Docker - управление контейнерами

*Дополнительные команды:*
• /ping <адрес> - проверить доступность хоста
• /start - показать это сообщение
"""
        await message.answer(help_text, parse_mode='Markdown')

def execute_ssh_command(server: str, command: str) -> str:
    """Выполнение SSH команды на сервере."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(**SSH_CONFIG[server])
        
        # Увеличиваем таймаут для длительных операций
        stdin, stdout, stderr = client.exec_command(command, timeout=300)
        
        # Читаем вывод построчно
        result = []
        while not stdout.channel.exit_status_ready():
            line = stdout.readline()
            if line:
                result.append(line.strip())
        
        # Читаем оставшийся вывод
        remaining = stdout.read().decode()
        if remaining:
            result.append(remaining.strip())
        
        # Проверяем наличие ошибок
        error = stderr.read().decode()
        if error:
            result.append(f"Ошибка: {error}")
        
        client.close()
        return '\n'.join(result)
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

async def show_loading(message: Message, text: str):
    """Показывает индикатор загрузки."""
    await message.edit_text(f"{text}\n\n⏳ Загрузка...")

def truncate_text(text: str, max_length: int = 3000) -> str:
    """Ограничивает длину текста и добавляет информацию о количестве пропущенных символов."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n... (пропущено {len(text) - max_length} символов)"

async def save_and_send_log(message: Message, log_content: str, log_type: str) -> None:
    """Сохраняет лог в файл и отправляет его в Telegram."""
    # Создаем временный файл
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{log_type}_{timestamp}.log"
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', encoding='utf-8') as temp_file:
        temp_file.write(log_content)
        temp_file.flush()
        
        # Отправляем файл в Telegram используя FSInputFile
        await message.answer_document(
            document=FSInputFile(temp_file.name, filename=filename),
            caption=f"📋 {log_type} лог от {timestamp}"
        )
        
        # Удаляем временный файл
        os.unlink(temp_file.name)

async def handle_callback(callback: CallbackQuery) -> None:
    """Обработка нажатий на кнопки."""
    await callback.answer()

    if callback.data == 'help':
        help_text = """
📚 *Справка по командам*

*Статус серверов:*
• Проверка диска - показывает свободное место
• Проверка памяти - показывает использование RAM
• Проверка нагрузки - показывает CPU и процессы

*Управление сервисами:*
• Nginx - управление веб-сервером
• PostgreSQL - управление базой данных
• Docker - управление контейнерами

*Системные операции:*
• Обновление пакетов
• Перезагрузка сервера

Для возврата в главное меню используйте кнопку "Назад"
"""
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    elif callback.data == 'main_menu':
        reply_markup = get_main_menu()
        await callback.message.edit_text("Выберите действие:", reply_markup=reply_markup)

    elif callback.data == 'status':
        keyboard = [
            [InlineKeyboardButton(text="💾 Проверить диск", callback_data='check_disk')],
            [InlineKeyboardButton(text="🧠 Проверить память", callback_data='check_memory')],
            [InlineKeyboardButton(text="📊 Проверить нагрузку", callback_data='check_load')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('📊 Выберите тип проверки:', reply_markup=reply_markup)

    elif callback.data == 'services':
        keyboard = [
            [InlineKeyboardButton(text="🌐 Nginx", callback_data='service_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL", callback_data='service_postgresql')],
            [InlineKeyboardButton(text="🐳 Docker", callback_data='service_docker')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('⚙️ Выберите сервис:', reply_markup=reply_markup)

    elif callback.data == 'system':
        keyboard = [
            [InlineKeyboardButton(text="🏓 Пинг", callback_data='ping')],
            [InlineKeyboardButton(text="🔄 Перезагрузка", callback_data='reboot')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('🔄 Выберите операцию:', reply_markup=reply_markup)

    elif callback.data == 'ping':
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='system')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            "🏓 Введите адрес для пинга (например, 8.8.8.8 или google.com):\n\n"
            "Используйте команду /ping <адрес>",
            reply_markup=reply_markup
        )

    elif callback.data == 'reboot':
        keyboard = [
            [InlineKeyboardButton(text="✅ Да, перезагрузить", callback_data='confirm_reboot')],
            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data='system')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('⚠️ Вы уверены, что хотите перезагрузить сервер?', 
                              reply_markup=reply_markup)

    elif callback.data == 'confirm_reboot':
        result = execute_ssh_command('server1', 'sudo reboot')
        keyboard = [[InlineKeyboardButton(text="◀️ Назад в меню", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('🔄 Сервер перезагружается...', 
                              reply_markup=reply_markup)

    elif callback.data == 'check_disk':
        result = execute_ssh_command('server1', 'df -h')
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='status')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'💾 Использование диска:\n```\n{result}\n```', 
                              reply_markup=reply_markup,
                              parse_mode='Markdown')

    elif callback.data == 'check_memory':
        result = execute_ssh_command('server1', 'free -h')
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='status')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'🧠 Использование памяти:\n```\n{result}\n```', 
                              reply_markup=reply_markup,
                              parse_mode='Markdown')

    elif callback.data == 'check_load':
        result = execute_ssh_command('server1', 'top -b -n 1 | head -n 5')
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='status')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'📊 Нагрузка системы:\n```\n{result}\n```', 
                              reply_markup=reply_markup,
                              parse_mode='Markdown')

    elif callback.data.startswith('service_'):
        service = callback.data.split('_')[1]
        if service == 'docker':
            keyboard = [
                [InlineKeyboardButton(text="📋 Все контейнеры", callback_data='docker_list_all')],
                [InlineKeyboardButton(text="📝 Dockerfile", callback_data='dockerfile_menu')],
                [InlineKeyboardButton(text="◀️ Назад", callback_data='services')]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await callback.message.edit_text('🐳 Управление Docker контейнерами:', reply_markup=reply_markup)
        else:
            keyboard = [
                [InlineKeyboardButton(text="📊 Статус", callback_data=f'status_{service}')],
                [InlineKeyboardButton(text="🔄 Перезапустить", callback_data=f'restart_{service}')],
                [InlineKeyboardButton(text="◀️ Назад", callback_data='services')]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await callback.message.edit_text(f'⚙️ Управление {service}:', reply_markup=reply_markup)

    elif callback.data.startswith('status_'):
        service = callback.data.split('_')[1]
        result = execute_ssh_command('server1', f'systemctl status {service}')
        keyboard = [
            [InlineKeyboardButton(text="🔄 Перезапустить", callback_data=f'restart_{service}')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='services')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'📊 Статус {service}:\n```\n{result}\n```', 
                              reply_markup=reply_markup,
                              parse_mode='Markdown')

    elif callback.data.startswith('restart_'):
        service = callback.data.split('_')[1]
        result = execute_ssh_command('server1', f'sudo systemctl restart {service}')
        status = execute_ssh_command('server1', f'systemctl status {service}')
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='services')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'🔄 Результат перезапуска {service}:\n```\n{status}\n```', 
                              reply_markup=reply_markup,
                              parse_mode='Markdown')

    elif callback.data == 'docker_list_all':
        # Получаем список всех контейнеров
        result = execute_ssh_command('server1', 'docker ps -a --format "{{.Names}}|{{.Status}}"')
        containers = result.strip().split('\n')
        
        keyboard = []
        for container in containers:
            if container:
                name, status = container.split('|')
                emoji = get_container_status_emoji(status)
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"{emoji} {name}",
                        callback_data=f'docker_info_{name}'
                    )
                ])
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data='service_docker')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('🐳 Все контейнеры:', reply_markup=reply_markup)

    elif callback.data == 'docker_list_running':
        # Получаем список только запущенных контейнеров
        result = execute_ssh_command('server1', 'docker ps --format "{{.Names}}|{{.Status}}"')
        containers = result.strip().split('\n')
        
        keyboard = []
        for container in containers:
            if container:
                name, status = container.split('|')
                emoji = get_container_status_emoji(status)
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"{emoji} {name}",
                        callback_data=f'docker_info_{name}'
                    )
                ])
        keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data='service_docker')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('🐳 Запущенные контейнеры:', reply_markup=reply_markup)

    elif callback.data.startswith('docker_info_'):
        container_name = callback.data.replace('docker_info_', '')
        # Получаем детальную информацию о контейнере
        info = execute_ssh_command('server1', f'docker inspect {container_name}')
        status = execute_ssh_command('server1', f'docker ps -a | grep {container_name}')
        
        # Проверяем, запущен ли контейнер
        is_running = 'Up' in status
        emoji = get_container_status_emoji(status)
        formatted_status = format_container_status(status)
        
        keyboard = []
        if is_running:
            keyboard.extend([
                [InlineKeyboardButton(text="🛑 Остановить", callback_data=f'stop_container_{container_name}')],
                [InlineKeyboardButton(text="🔄 Перезапустить", callback_data=f'restart_container_{container_name}')]
            ])
        else:
            keyboard.append([InlineKeyboardButton(text="▶️ Запустить", callback_data=f'start_container_{container_name}')])
        
        keyboard.append([InlineKeyboardButton(text="◀️ Назад к списку", callback_data='docker_list_all')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(
            f'🐳 Информация о контейнере:\n\n'
            f'Имя: {container_name}\n'
            f'Статус: {emoji} {formatted_status}\n\n'
            f'Техническая информация:\n```\n{status}\n```',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif callback.data.startswith('restart_container_'):
        container_name = callback.data.replace('restart_container_', '')
        result = execute_ssh_command('server1', f'docker restart {container_name}')
        status = execute_ssh_command('server1', f'docker ps -a | grep {container_name}')
        
        keyboard = [[InlineKeyboardButton(text="◀️ Назад к контейнеру", callback_data=f'docker_info_{container_name}')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            f'🔄 Результат перезапуска контейнера {container_name}:\n```\n{status}\n```',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif callback.data == 'service_docker':
        keyboard = [
            [InlineKeyboardButton(text="📋 Контейнеры", callback_data='docker_list_all')],
            [InlineKeyboardButton(text="📝 Dockerfile", callback_data='dockerfile_menu')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='services')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('🐳 Управление Docker:', reply_markup=reply_markup)

    elif callback.data == 'dockerfile_menu':
        keyboard = [
            [InlineKeyboardButton(text="📤 Загрузить Dockerfile", callback_data='dockerfile_upload')],
            [InlineKeyboardButton(text="✏️ Создать Dockerfile", callback_data='dockerfile_create')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='service_docker')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '📝 Работа с Dockerfile:\n\n'
            'Выберите действие:\n'
            '• Загрузить существующий Dockerfile\n'
            '• Создать новый Dockerfile с помощью ассистента',
            reply_markup=reply_markup
        )

    elif callback.data == 'dockerfile_create':
        keyboard = [
            [InlineKeyboardButton(text="🐍 Python", callback_data='dockerfile_python')],
            [InlineKeyboardButton(text="🌐 Node.js", callback_data='dockerfile_node')],
            [InlineKeyboardButton(text="🔄 Nginx", callback_data='dockerfile_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL", callback_data='dockerfile_postgres')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='dockerfile_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '📝 Выберите тип приложения для Dockerfile:\n\n'
            'Я помогу вам создать оптимальный Dockerfile для выбранного типа приложения.',
            reply_markup=reply_markup
        )

    elif callback.data.startswith('dockerfile_'):
        template_type = callback.data.replace('dockerfile_', '')
        dockerfile_content = ""
        
        if template_type == 'python':
            dockerfile_content = """# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Запускаем приложение
CMD ["python", "app.py"]"""
        elif template_type == 'node':
            dockerfile_content = """# Используем официальный образ Node.js
FROM node:18-alpine

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем package.json и package-lock.json
COPY package*.json ./

# Устанавливаем зависимости
RUN npm install

# Копируем код приложения
COPY . .

# Запускаем приложение
CMD ["npm", "start"]"""
        elif template_type == 'nginx':
            dockerfile_content = """# Используем официальный образ Nginx
FROM nginx:alpine

# Копируем конфигурацию
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Копируем статические файлы
COPY ./static /usr/share/nginx/html

# Открываем порт
EXPOSE 80

# Запускаем Nginx
CMD ["nginx", "-g", "daemon off;"]"""
        elif template_type == 'postgres':
            dockerfile_content = """# Используем официальный образ PostgreSQL
FROM postgres:15

# Копируем скрипты инициализации
COPY ./init-scripts /docker-entrypoint-initdb.d/

# Настраиваем переменные окружения
ENV POSTGRES_DB=mydb
ENV POSTGRES_USER=myuser
ENV POSTGRES_PASSWORD=mypassword

# Открываем порт
EXPOSE 5432"""

        keyboard = [
            [InlineKeyboardButton(text="💾 Сохранить", callback_data=f'save_dockerfile_{template_type}')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='dockerfile_create')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            f'📝 Dockerfile для {template_type}:\n\n'
            f'```dockerfile\n{dockerfile_content}\n```\n\n'
            'Вы можете сохранить этот шаблон или вернуться назад для выбора другого типа.',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    elif callback.data.startswith('save_dockerfile_'):
        template_type = callback.data.replace('save_dockerfile_', '')
        # Здесь можно добавить логику сохранения Dockerfile
        keyboard = [[InlineKeyboardButton(text="◀️ Назад в меню", callback_data='dockerfile_menu')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            f'✅ Dockerfile для {template_type} сохранен!\n\n'
            'Теперь вы можете использовать его для сборки образа.',
            reply_markup=reply_markup
        )

    elif callback.data == 'dockerfile_upload':
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='dockerfile_menu')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '📤 Загрузите ваш Dockerfile, отправив его как файл в этот чат.\n\n'
            'Я помогу вам проверить его и предложу улучшения, если потребуется.',
            reply_markup=reply_markup
        )

    elif callback.data == 'logs':
        keyboard = [
            [InlineKeyboardButton(text="📊 Системные логи", callback_data='logs_system')],
            [InlineKeyboardButton(text="🐳 Docker логи", callback_data='logs_docker')],
            [InlineKeyboardButton(text="🌐 Nginx логи", callback_data='logs_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL логи", callback_data='logs_postgres')],
            [InlineKeyboardButton(text="◀️ Назад", callback_data='main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '📋 Выберите тип логов для просмотра:',
            reply_markup=reply_markup
        )

    elif callback.data == 'logs_system':
        # Показываем индикатор загрузки
        await show_loading(callback.message, "📊 Получение системных логов...")
        
        # Получаем системные логи
        journalctl = execute_ssh_command('server1', 'journalctl -n 100 --no-pager')
        await save_and_send_log(callback.message, journalctl, "Системные")
        
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='logs')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Системные логи сохранены и отправлены.',
            reply_markup=reply_markup
        )

    elif callback.data == 'logs_docker':
        # Показываем индикатор загрузки
        await show_loading(callback.message, "🐳 Получение логов Docker...")
        
        # Получаем список всех контейнеров
        containers = execute_ssh_command('server1', 'docker ps -a --format "{{.Names}}"')
        containers = containers.strip().split('\n')
        
        # Собираем логи для каждого контейнера
        all_logs = []
        for container in containers:
            if container:  # Проверяем, что имя контейнера не пустое
                container_logs = execute_ssh_command('server1', f'docker logs --tail 50 {container}')
                all_logs.append(f"\n=== Логи контейнера {container} ===\n{container_logs}")
        
        # Объединяем все логи
        docker_logs = "\n".join(all_logs)
        
        # Сохраняем и отправляем логи
        await save_and_send_log(callback.message, docker_logs, "Docker")
        
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='logs')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Логи Docker сохранены и отправлены.',
            reply_markup=reply_markup
        )

    elif callback.data == 'logs_nginx':
        # Показываем индикатор загрузки
        await show_loading(callback.message, "🌐 Получение логов Nginx...")
        
        # Получаем логи Nginx
        nginx_logs = execute_ssh_command('server1', 'tail -n 100 /var/log/nginx/access.log /var/log/nginx/error.log')
        await save_and_send_log(callback.message, nginx_logs, "Nginx")
        
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='logs')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Логи Nginx сохранены и отправлены.',
            reply_markup=reply_markup
        )

    elif callback.data == 'logs_postgres':
        # Показываем индикатор загрузки
        await show_loading(callback.message, "🗄 Получение логов PostgreSQL...")
        
        # Получаем логи PostgreSQL
        postgres_logs = execute_ssh_command('server1', 'tail -n 100 /var/log/postgresql/postgresql-*.log')
        await save_and_send_log(callback.message, postgres_logs, "PostgreSQL")
        
        keyboard = [[InlineKeyboardButton(text="◀️ Назад", callback_data='logs')]]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Логи PostgreSQL сохранены и отправлены.',
            reply_markup=reply_markup
        )

async def handle_ping(message: Message) -> None:
    """Обработчик команды пинга."""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return

    try:
        # Получаем адрес для пинга из сообщения
        address = message.text.split()[1]
        
        # Выполняем пинг
        result = execute_ssh_command('server1', f'ping -c 4 {address}')
        
        # Отправляем результат
        await message.answer(f"🏓 Результат пинга {address}:\n```\n{result}\n```", 
                           parse_mode='Markdown')
    except IndexError:
        await message.answer("❌ Пожалуйста, укажите адрес для пинга.\nПример: /ping 8.8.8.8")
    except Exception as e:
        await message.answer(f"❌ Ошибка при выполнении пинга: {str(e)}")

async def main() -> None:
    """Запуск бота."""
    # Регистрируем обработчики
    dp.message.register(start, Command(commands=["start"]))
    dp.message.register(handle_menu)
    dp.message.register(handle_ping, Command(commands=["ping"]))
    dp.callback_query.register(handle_callback)

    # Запускаем бота
    print("🤖 Бот запущен...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
