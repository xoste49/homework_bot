import json
import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv
from telegram import Bot, error

load_dotenv()

PRAKTIKUM_TOKEN = os.getenv("PRAKTIKUM_TOKEN")
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

time_sleep_error = 30  # Время ожидания после ошибки
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)


class PraktikumException(Exception):
    pass


def timeout_and_logging(message: str = None, level_error=logging.error):
    """
    Таймаут между после ошибки увеличивающийся в 2 раза после каждой ошибки
    """
    if message:
        level_error(message)  # Запись в лог
    global time_sleep_error
    logging.debug(f'Timeout: {time_sleep_error}с')
    time.sleep(time_sleep_error)
    time_sleep_error *= 2
    if time_sleep_error >= 51200:
        time_sleep_error = 30
        logging.critical(
            'Очень много ошибок или проблемы в работе программы. '
        )


def parse_homework_status(homework):
    """
    Парсим домашнее задание

    :param homework: Задание
    :return: Результат выполнения домашней работы
    """
    logging.debug(f"Парсим домашнее задание: {homework}")
    if 'homework_name' not in homework:
        raise PraktikumException(
            "Отсутствует имя в домашнем задании!"
        )
    homework_name = homework['homework_name']
    if 'status' in homework:
        homework_status = homework['status']
    else:
        logging.error("Статус домашней работы пуст!")

    statuses = {
        'reviewing': 'Взята в ревью.',
        'approved': 'Ревьюеру всё понравилось, можно приступать к '
                    'следующему уроку.',
        'rejected': 'К сожалению в работе нашлись ошибки.',
    }

    if homework_status in statuses:
        verdict = statuses[homework_status]
    else:
        raise PraktikumException(
            "Обнаружен новый статус, отсутствующий в списке!"
        )

    return f'У вас проверили работу "{homework_name}"!\n\n{verdict}'


def get_homework_statuses(current_timestamp):
    """
    Получение списка домашних работы от заданного времени.

    :param current_timestamp: Время в формате timestamp
    :return: Статус домашней работы
    """
    logging.debug("Получение списка домашних работы")
    try:
        homework_statuses = requests.get(
            "https://praktikum.yandex.ru/api/user_api/homework_statuses/",
            headers={'Authorization': f'OAuth {PRAKTIKUM_TOKEN}'},
            params={'from_date': current_timestamp}
        )
    except requests.exceptions.RequestException as e:
        raise PraktikumException(
            "При обработке вашего запроса возникла неоднозначная "
            f"исключительная ситуация: {e}"
        )
    except ValueError as e:
        raise PraktikumException(f"Ошибка в значении {e}")
    except TypeError as e:
        raise PraktikumException(f"Не корректный тип данных {e}")

    if homework_statuses.status_code != 200:
        raise PraktikumException(f"Ошибка {homework_statuses.status_code} сайт praktikum.yandex.ru недоступен")

    try:
        homework_statuses_json = homework_statuses.json()
    except json.JSONDecodeError:
        raise PraktikumException(
            "Ответ от сервера должен быть в формате JSON"
        )

    if 'error' in homework_statuses_json:
        if 'error' in homework_statuses_json['error']:
            raise PraktikumException(
                f"{homework_statuses_json['error']['error']}"
            )

    if 'code' in homework_statuses_json:
        raise PraktikumException(
            f"{homework_statuses_json['message']}"
        )
    logging.debug("Список домашних работ получен")

    return homework_statuses_json


def send_message(message, bot_client):
    """
    Отправка сообщения в телеграм

    :param message: Сообщение
    :param bot_client: Экземпляр бота телеграм
    :return: Результат отправки сообщения
    """
    log = message.replace('\n', '')
    logging.info(f"Отправка сообщения в телеграм: {log}")
    try:
        return bot_client.send_message(chat_id=CHAT_ID, text=message)
    except error.Unauthorized:
        timeout_and_logging(
            'Телеграм API: Не авторизован, проверьте TOKEN и CHAT_ID'
        )
    except error.BadRequest as e:
        timeout_and_logging(f'Ошибка работы с Телеграм: {e}')
    except error.TelegramError as e:
        timeout_and_logging(f'Ошибка работы с Телеграм: {e}')


def main():
    logging.debug('Бот запущен!')
    current_timestamp = int(time.time())  # начальное значение timestamp
    bot = Bot(token=TELEGRAM_TOKEN)

    while True:
        try:
            new_homework = get_homework_statuses(current_timestamp)
            homeworks = new_homework.get('homeworks')
            if ((type(homeworks) is list)
                    and (len(homeworks) > 0)
                    and homeworks):
                send_message(parse_homework_status(homeworks[0]), bot)
            else:
                logging.info("Задания не обнаружены")
            current_timestamp = new_homework.get(
                'current_date', current_timestamp
            )
            # опрашивать раз в десять минут
            time.sleep(600)

        except PraktikumException as e:
            #send_message(f'Ошибка: praktikum.yandex.ru: {e}', bot)
            timeout_and_logging(f'praktikum.yandex.ru: {e}')
        except Exception as e:
            timeout_and_logging(
                f'Бот столкнулся с ошибкой: {e}',
                logging.critical
            )
        else:
            global time_sleep_error
            time_sleep_error = 30


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Выход из программы')
        sys.exit(0)
