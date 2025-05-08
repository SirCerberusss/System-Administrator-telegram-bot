#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import paramiko
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from datetime import datetime
import tempfile
import asyncio
import json
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   level=logging.INFO)
logger = logging.getLogger(__name__)

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
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

config = load_config()
TOKEN = config['TOKEN']
ADMIN_IDS = config['ADMIN_IDS']
SSH_CONFIG = config['SSH_CONFIG']

def get_container_status_emoji(status: str) -> str:
    if 'Up' in status:
        return '🟢'
    elif 'Exited' in status:
        return '🔴'
    elif 'Created' in status:
        return '⚪'
    elif 'Restarting' in status:
        return '🟡'
    elif 'Paused' in status:
        return '⏸️'
    else:
        return '❓'

def format_container_status(status: str) -> str:
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

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

def get_welcome_message(username: str) -> str:
    return f"""
🚀 *Панель управления сервером*

*Функционал бота:*

🖥 *Мониторинг сервера*
• Проверять статус системы
• Следить за использованием ресурсов
• Контролировать нагрузку

⚙️ *Управление сервисами*
• Управлять Docker контейнерами
• Контролировать веб-сервер
• Настраивать базу данных

🔄 *Системные операции*
• Обновлять пакеты
• Перезагружать сервер
• Выполнять команды

Используйте кнопки ниже для управления 👇
"""

def get_reply_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="⚙️ Сервисы")],
        [KeyboardButton(text="🖥 Статус"), KeyboardButton(text="🏓 Пинг")],
        [KeyboardButton(text="📋 Логи"), KeyboardButton(text="🔄 Перезагрузка")],
        [KeyboardButton(text="🏠 На главную")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

async def start(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return

    username = message.from_user.first_name
    welcome_text = get_welcome_message(username)
    keyboard = get_reply_keyboard()
    
    await message.answer_photo(
        photo="https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=1000&auto=format&fit=crop",
        caption=welcome_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

def execute_ssh_command(server: str, command: str) -> str:
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(**SSH_CONFIG[server])
        
        stdin, stdout, stderr = client.exec_command(command, timeout=300)
        
        result = []
        while not stdout.channel.exit_status_ready():
            line = stdout.readline()
            if line:
                result.append(line.strip())
        
        remaining = stdout.read().decode()
        if remaining:
            result.append(remaining.strip())
        
        error = stderr.read().decode()
        if error:
            result.append(f"Ошибка: {error}")
        
        client.close()
        return '\n'.join(result)
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

async def show_loading(message: Message, text: str):
    await message.edit_text(f"{text}\n\n⏳ Загрузка...")

async def save_and_send_log(message: Message, log_content: str, log_type: str) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{log_type}_{timestamp}.log"
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log', encoding='utf-8') as temp_file:
        temp_file.write(log_content)
        temp_file.flush()
        
        await message.answer_document(
            document=FSInputFile(temp_file.name, filename=filename),
            caption=f"📋 {log_type} лог от {timestamp}"
        )
        
        os.unlink(temp_file.name)

class PingState(StatesGroup):
    waiting_for_address = State()

async def handle_menu(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return
    
    keyboard = get_reply_keyboard()
    
    if message.text == "🏠 На главную":
        await state.clear()
        welcome_text = get_welcome_message(message.from_user.first_name)
        await message.answer_photo(
            photo="https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=1000&auto=format&fit=crop",
            caption=welcome_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return
    elif message.text == "🏓 Пинг":
        await state.set_state(PingState.waiting_for_address)
        await message.answer(
            "🏓 Введите адрес для пинга:\n\n"
            "Примеры адресов:\n"
            "• 8.8.8.8\n"
            "• google.com\n"
            "• ya.ru",
            reply_markup=keyboard
        )
        return
    elif message.text == "🖥 Статус":
        await state.clear()
        keyboard = [
            [InlineKeyboardButton(text="💾 Проверить диск", callback_data='check_disk')],
            [InlineKeyboardButton(text="🧠 Проверить память", callback_data='check_memory')],
            [InlineKeyboardButton(text="📊 Проверить нагрузку", callback_data='check_load')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('📊 Выберите тип проверки:', reply_markup=inline_markup)
        return
    elif message.text == "⚙️ Сервисы":
        await state.clear()
        keyboard = [
            [InlineKeyboardButton(text="🌐 Nginx", callback_data='service_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL", callback_data='service_postgresql')],
            [InlineKeyboardButton(text="🐳 Docker", callback_data='service_docker')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('⚙️ Выберите сервис:', reply_markup=inline_markup)
        return
    elif message.text == "📋 Логи":
        await state.clear()
        keyboard = [
            [InlineKeyboardButton(text="📊 Системные логи", callback_data='logs_system')],
            [InlineKeyboardButton(text="🐳 Docker логи", callback_data='logs_docker')],
            [InlineKeyboardButton(text="🌐 Nginx логи", callback_data='logs_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL логи", callback_data='logs_postgres')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('📋 Выберите тип логов для просмотра:', reply_markup=inline_markup)
        return
    elif message.text == "🔄 Перезагрузка":
        await state.clear()
        keyboard = [
            [InlineKeyboardButton(text="✅ Да, перезагрузить", callback_data='confirm_reboot')],
            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data='main_menu')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await message.answer('⚠️ Вы уверены, что хотите перезагрузить сервер?', 
                           reply_markup=inline_markup)
        return

    await state.clear()
    welcome_text = get_welcome_message(message.from_user.first_name)
    await message.answer_photo(
        photo="https://images.unsplash.com/photo-1558494949-ef010cbdcc31?q=80&w=1000&auto=format&fit=crop",
        caption=welcome_text,
        parse_mode='Markdown',
        reply_markup=keyboard
    )

async def handle_callback(callback: CallbackQuery) -> None:
    await callback.answer()

    if callback.data == 'status':
        keyboard = [
            [InlineKeyboardButton(text="💾 Проверить диск", callback_data='check_disk')],
            [InlineKeyboardButton(text="🧠 Проверить память", callback_data='check_memory')],
            [InlineKeyboardButton(text="📊 Проверить нагрузку", callback_data='check_load')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('📊 Выберите тип проверки:', reply_markup=inline_markup)

    elif callback.data == 'services':
        keyboard = [
            [InlineKeyboardButton(text="🌐 Nginx", callback_data='service_nginx')],
            [InlineKeyboardButton(text="🗄 PostgreSQL", callback_data='service_postgresql')],
            [InlineKeyboardButton(text="🐳 Docker", callback_data='service_docker')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('⚙️ Выберите сервис:', reply_markup=inline_markup)

    elif callback.data == 'main_menu':
        keyboard = [
            [InlineKeyboardButton(text="🖥 Статус серверов", callback_data='status')],
            [InlineKeyboardButton(text="⚙️ Управление сервисами", callback_data='services')],
            [InlineKeyboardButton(text="📋 Логи", callback_data='logs')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text('🤖 Главное меню:', reply_markup=inline_markup)

    elif callback.data.startswith('service_'):
        service = callback.data.split('_')[1]
        if service == 'docker':
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
            inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await callback.message.edit_text('🐳 Все контейнеры:', reply_markup=inline_markup)
        else:
            keyboard = [
                [InlineKeyboardButton(text="📊 Статус", callback_data=f'status_{service}')],
                [InlineKeyboardButton(text="🔄 Перезапустить", callback_data=f'restart_{service}')]
            ]
            inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            await callback.message.edit_text(f'⚙️ Управление {service}:', reply_markup=inline_markup)

    elif callback.data.startswith('status_'):
        service = callback.data.split('_')[1]
        result = execute_ssh_command('server1', f'systemctl status {service}')
        keyboard = [
            [InlineKeyboardButton(text="🔄 Перезапустить", callback_data=f'restart_{service}')]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'📊 Статус {service}:\n```\n{result}\n```', 
                              reply_markup=inline_markup,
                              parse_mode='Markdown')

    elif callback.data.startswith('restart_'):
        service = callback.data.split('_')[1]
        result = execute_ssh_command('server1', f'sudo systemctl restart {service}')
        status = execute_ssh_command('server1', f'systemctl status {service}')
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'🔄 Результат перезапуска {service}:\n```\n{status}\n```', 
                              reply_markup=inline_markup,
                              parse_mode='Markdown')

    elif callback.data.startswith('docker_info_'):
        container_name = callback.data.replace('docker_info_', '')
        info = execute_ssh_command('server1', f'docker inspect {container_name}')
        status = execute_ssh_command('server1', f'docker ps -a | grep {container_name}')
        
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
        
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text(
            f'🐳 Информация о контейнере:\n\n'
            f'Имя: {container_name}\n'
            f'Статус: {emoji} {formatted_status}\n\n'
            f'Техническая информация:\n```\n{status}\n```',
            reply_markup=inline_markup,
            parse_mode='Markdown'
        )

    elif callback.data == 'logs_system':
        await show_loading(callback.message, "📊 Получение системных логов...")
        journalctl = execute_ssh_command('server1', 'journalctl -n 100 --no-pager')
        await save_and_send_log(callback.message, journalctl, "Системные")
        
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Системные логи сохранены и отправлены.',
            reply_markup=inline_markup
        )

    elif callback.data == 'logs_docker':
        await show_loading(callback.message, "🐳 Получение логов Docker...")
        containers = execute_ssh_command('server1', 'docker ps -a --format "{{.Names}}"')
        containers = containers.strip().split('\n')
        
        all_logs = []
        for container in containers:
            if container:
                container_logs = execute_ssh_command('server1', f'docker logs --tail 50 {container}')
                all_logs.append(f"\n=== Логи контейнера {container} ===\n{container_logs}")
        
        docker_logs = "\n".join(all_logs)
        await save_and_send_log(callback.message, docker_logs, "Docker")
        
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Логи Docker сохранены и отправлены.',
            reply_markup=inline_markup
        )

    elif callback.data == 'logs_nginx':
        await show_loading(callback.message, "🌐 Получение логов Nginx...")
        nginx_logs = execute_ssh_command('server1', 'tail -n 100 /var/log/nginx/access.log /var/log/nginx/error.log')
        await save_and_send_log(callback.message, nginx_logs, "Nginx")
        
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Логи Nginx сохранены и отправлены.',
            reply_markup=inline_markup
        )

    elif callback.data == 'logs_postgres':
        await show_loading(callback.message, "🗄 Получение логов PostgreSQL...")
        postgres_logs = execute_ssh_command('server1', 'tail -n 100 /var/log/postgresql/postgresql-*.log')
        await save_and_send_log(callback.message, postgres_logs, "PostgreSQL")
        
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(
            '✅ Логи PostgreSQL сохранены и отправлены.',
            reply_markup=inline_markup
        )

    elif callback.data == 'check_disk':
        result = execute_ssh_command('server1', 'df -h')
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'💾 Использование диска:\n```\n{result}\n```', 
                              reply_markup=inline_markup,
                              parse_mode='Markdown')

    elif callback.data == 'check_memory':
        result = execute_ssh_command('server1', 'free -h')
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'🧠 Использование памяти:\n```\n{result}\n```', 
                              reply_markup=inline_markup,
                              parse_mode='Markdown')

    elif callback.data == 'check_load':
        result = execute_ssh_command('server1', 'top -b -n 1 | head -n 5')
        keyboard = []
        inline_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        await callback.message.edit_text(f'📊 Нагрузка системы:\n```\n{result}\n```', 
                              reply_markup=inline_markup,
                              parse_mode='Markdown')

async def handle_ping(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return
    
    keyboard = get_reply_keyboard()
    
    try:
        result = execute_ssh_command('server1', f'ping -c 4 {message.text}')
        await message.answer(f"🏓 Результат пинга {message.text}:\n```\n{result}\n```", 
                           parse_mode='Markdown',
                           reply_markup=keyboard)
    except Exception as e:
        await message.answer(f"❌ Ошибка при выполнении пинга: {str(e)}", reply_markup=keyboard)
    finally:
        await state.clear()

async def handle_text(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        await message.answer('⛔ У вас нет доступа к этому боту.')
        return
    
    keyboard = [[KeyboardButton(text="🏠 На главную")]]
    reply_markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    await message.answer("Введите команду /ping и адрес:", reply_markup=reply_markup)

async def main() -> None:
    dp.message.register(start, Command(commands=["start"]))
    dp.message.register(handle_ping, StateFilter(PingState.waiting_for_address))
    dp.message.register(handle_menu)
    dp.callback_query.register(handle_callback)

    print("🤖 Бот запущен...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
