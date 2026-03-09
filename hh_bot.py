from config import MAX_APPLICATIONS, IGNORED_EMPLOYERS
from bot.vacancy import Vacancy
from bot.filters import vacancy_passes_filters
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import os
from datetime import datetime

# ==========================================
# НАСТРОЙКИ
# ==========================================

CHROMEDRIVER_PATH = os.path.expanduser("~/hh_bot/chromedriver")
LOG_FILE = os.path.expanduser("~/hh_bot/log.txt")

# ==========================================

# ==========================================
# ЛОГИРОВАНИЕ
# ==========================================

session_start = datetime.now()
session_stats = {
    "applied": 0,
    "skipped_ignored": 0,
    "skipped_letter": 0,
    "skipped_no_button": 0,
    "skipped_already": 0,
    "errors": 0,
}

def log(message, to_console=True):
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    line = "[" + timestamp + "] " + message
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    if to_console:
        print(message)

def log_session_start():
    log("=" * 60, to_console=False)
    log("🚀 СЕССИЯ НАЧАТА", to_console=False)
    log("Дата/время: " + session_start.strftime("%d.%m.%Y %H:%M:%S"), to_console=False)
    log("Цель откликов: " + str(MAX_APPLICATIONS), to_console=False)
    log("Игнорируем: " + str(IGNORED_EMPLOYERS), to_console=False)
    log("=" * 60, to_console=False)

def log_session_end(applied_count, stop_reason=""):
    duration = datetime.now() - session_start
    minutes = int(duration.total_seconds() // 60)
    seconds = int(duration.total_seconds() % 60)
    log("=" * 60, to_console=False)
    log("🏁 СЕССИЯ ЗАВЕРШЕНА", to_console=False)
    log("Длительность: " + str(minutes) + " мин " + str(seconds) + " сек", to_console=False)
    log("✅ Откликов отправлено: " + str(session_stats["applied"]), to_console=False)
    log("🚫 Пропущено (игнор. работодатель): " + str(session_stats["skipped_ignored"]), to_console=False)
    log("📝 Пропущено (нужно письмо/тест): " + str(session_stats["skipped_letter"]), to_console=False)
    log("🔘 Пропущено (нет кнопки): " + str(session_stats["skipped_no_button"]), to_console=False)
    log("♻️  Уже откликался: " + str(session_stats["skipped_already"]), to_console=False)
    log("❌ Ошибок: " + str(session_stats["errors"]), to_console=False)
    log("⛔ Причина остановки: " + stop_reason, to_console=False)
    log("=" * 60, to_console=False)

# ==========================================

def rp(a=1, b=3):
    t = random.uniform(a, b)
    print("  ⏳ Пауза " + str(round(t, 1)) + " сек...")
    time.sleep(t)

def rp_short():
    time.sleep(random.uniform(0.5, 1.5))

def slow_scroll_to_element(driver, element):
    location = element.location["y"]
    current = driver.execute_script("return window.pageYOffset")
    distance = location - current - 300
    steps = 10
    step_size = distance / steps
    for i in range(steps):
        driver.execute_script("window.scrollBy(0, " + str(step_size) + ")")
        time.sleep(random.uniform(0.03, 0.08))
    time.sleep(random.uniform(0.5, 1))

def create_driver():
    print("🔧 Подготавливаем браузер (Яндекс)...")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService

    service = ChromeService(executable_path=os.path.expanduser("~/hh_bot/yandexdriver"))

    options = webdriver.ChromeOptions()
    options.binary_location = "/Applications/Yandex.app/Contents/MacOS/Yandex"
    options.add_argument("--user-data-dir=" + os.path.expanduser("~/hh_bot/yandex_profile"))
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.set_capability("browserVersion", "142")

    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def wait_for_element(driver, selector, timeout=180):
    for i in range(timeout // 5):
        try:
            els = driver.find_elements(By.CSS_SELECTOR, selector)
            if len(els) > 0:
                return els
        except:
            pass
        if i % 12 == 0 and i > 0:
            print("⏳ Всё ещё жду... (" + str(i * 5) + " сек)")
        time.sleep(5)
    return []

def click_show_all_vacancies(driver):
    print("🔍 Ищу кнопку 'Посмотреть вакансии'...")
    for i in range(8):
        driver.execute_script("window.scrollBy(0, 400)")
        time.sleep(random.uniform(0.3, 0.8))
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "[data-qa='applicant-index-search-all-results-button']")
            print("✅ Кнопка найдена!")
            slow_scroll_to_element(driver, btn)
            rp_short()
            btn.click()
            rp(2, 3)
            print("📋 Перешёл на страницу со всеми вакансиями")
            return True
        except:
            continue
    print("❌ Кнопка не найдена")
    return False

def is_ignored_employer(employer_name):
    employer_lower = employer_name.lower()
    for ignored in IGNORED_EMPLOYERS:
        if ignored.lower() in employer_lower:
            return True
    return False

def get_vacancy_cards(driver):
    results = []
    print("👀 Просматриваю список вакансий...")

    for i in range(6):
        driver.execute_script("window.scrollBy(0, 300)")
        time.sleep(random.uniform(0.5, 1))

    driver.execute_script("window.scrollTo(0, 0)")
    time.sleep(1)

    cards = driver.find_elements(By.CSS_SELECTOR, "[data-qa='vacancy-serp__vacancy']")
    print("📊 Карточек вакансий на странице: " + str(len(cards)))

    for card in cards:
        try:
            try:
                title = card.find_element(By.CSS_SELECTOR, "h2").text.strip()
            except:
                title = "Без названия"

            try:
                employer = card.find_element(
                    By.CSS_SELECTOR,
                    "[data-qa='vacancy-serp__vacancy-employer'], [data-qa='vacancy-serp__vacancy-employer-text']"
                ).text.strip()
            except:
                employer = ""

            btn = card.find_element(By.CSS_SELECTOR, "[data-qa='vacancy-serp__vacancy_response']")
            href = btn.get_attribute("href")

            if not href:
                continue

            vacancy = Vacancy(
                title=title,
                employer=employer,
                href=href,
                element=card,
            )

            passed, reason = vacancy_passes_filters(vacancy)

            if not passed:
                print("  🚫 Пропуск: " + reason + " — " + title + " | " + employer)
                log("🚫 ПРОПУЩЕНО (" + reason + "): " + title + " | " + employer, to_console=False)

                if reason == "ignored employer":
                    session_stats["skipped_ignored"] += 1

                continue

            results.append({
                "title": vacancy.title,
                "employer": vacancy.employer,
                "href": vacancy.href,
                "element": vacancy.element
            })

        except:
            continue

    return results

def has_extra_requirements(driver):
    letter1 = driver.find_elements(By.CSS_SELECTOR, "textarea[name='text'][required], textarea[name='text'][aria-required='true']")
    if len(letter1) > 0:
        return True
    letter2 = driver.find_elements(By.CSS_SELECTOR, "textarea[data-qa='vacancy-response-letter-text'][required], textarea[data-qa='vacancy-response-letter-text'][aria-required='true']")
    if len(letter2) > 0:
        return True
    test = driver.find_elements(By.CSS_SELECTOR, "[data-qa='test-question'], [data-qa='task-question']")
    if len(test) > 0:
        return True
    return False

def apply_in_new_tab(driver, href, title, employer):
    main_tab = driver.current_window_handle
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", href)
        rp(1, 2)
        new_tab = [t for t in driver.window_handles if t != main_tab][0]
        driver.switch_to.window(new_tab)
        rp(1, 3)

        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(1)
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()

        if "вы откликнулись" in page_text or "резюме доставлено" in page_text:
            print("  ✅ Отклик уже отправлен: " + title + " | " + employer)
            log("♻️  УЖЕ ОТКЛИКАЛСЯ: " + title + " | " + employer, to_console=False)
            session_stats["skipped_already"] += 1
            rp(1, 2)
            driver.close()
            driver.switch_to.window(main_tab)
            rp_short()
            return True

        if has_extra_requirements(driver):
            print("  ⚠️  Требуется письмо или тест, пропускаем...")
            log("📝 ПРОПУЩЕНО (письмо/тест): " + title + " | " + employer, to_console=False)
            session_stats["skipped_letter"] += 1
            driver.close()
            driver.switch_to.window(main_tab)
            rp_short()
            return False

        wait = WebDriverWait(driver, 10)
        clicked = False
        for selector in [
            "button[data-qa='vacancy-response-submit-popup']",
            "button[data-qa='vacancy-response-letter-submit']",
            "button[data-qa='vacancy-response-link-top']",
            "a[data-qa='vacancy-response-link-top']"
        ]:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                rp_short()
                btn.click()
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0)")
                clicked = True
                break
            except:
                continue

        if not clicked:
            print("  ❌ Кнопка откликнуться не найдена, пропускаем")
            log("🔘 ПРОПУЩЕНО (нет кнопки): " + title + " | " + employer, to_console=False)
            session_stats["skipped_no_button"] += 1
            driver.close()
            driver.switch_to.window(main_tab)
            rp_short()
            return False

        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0)")
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()

        if "вы откликнулись" in page_text or "резюме доставлено" in page_text or "отклик отправлен" in page_text:
            print("  ✅ Отклик отправлен: " + title + " | " + employer)
            log("✅ ОТКЛИК: " + title + " | " + employer + " | " + href, to_console=False)
            session_stats["applied"] += 1
            rp(1, 2)
            driver.close()
            driver.switch_to.window(main_tab)
            rp_short()
            return True
        else:
            print("  ❌ Не удалось подтвердить отклик, пропускаем")
            log("❌ НЕ ПОДТВЕРЖДЕНО: " + title + " | " + employer, to_console=False)
            session_stats["errors"] += 1
            driver.close()
            driver.switch_to.window(main_tab)
            rp_short()
            return False

    except Exception as e:
        print("  ❌ Ошибка: " + str(e))
        log("❌ ОШИБКА: " + title + " | " + employer + " | " + str(e), to_console=False)
        session_stats["errors"] += 1
        try:
            for tab in driver.window_handles:
                if tab != main_tab:
                    driver.switch_to.window(tab)
                    driver.close()
            driver.switch_to.window(main_tab)
        except:
            pass
        return False

def go_to_next_page(driver, page):
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        next_pages = driver.find_elements(By.CSS_SELECTOR, "[data-qa='pager-page']")
        for p in next_pages:
            if p.text.strip() == str(page + 1):
                print("➡️  Перехожу на страницу " + str(page + 1) + "...")
                log("📄 Переход на страницу " + str(page + 1), to_console=False)
                slow_scroll_to_element(driver, p)
                rp_short()
                p.click()
                rp(2, 3)
                return True
        print("🏁 Следующая страница не найдена, останавливаемся")
        return False
    except Exception as e:
        print("❌ Ошибка при переходе на страницу: " + str(e))
        return False

def run_bot():
    print("🤖 Бот запущен: " + datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    print("🚫 Игнорируем: " + str(IGNORED_EMPLOYERS))
    print("🎯 Цель: " + str(MAX_APPLICATIONS) + " откликов")
    print("=" * 50)

    log_session_start()

    driver = create_driver()
    applied_count = 0
    stop_reason = "Неизвестно"

    try:
        print("🌐 Открываем HH.ru...")
        driver.get("https://hh.ru/?hhtmFrom=resume_list")
        rp(2, 3)

        print("👤 Войди в аккаунт если нужно (жду 3 минуты)...")
        found = wait_for_element(driver, "[data-qa='applicant-index-search-all-results-button']")
        if not found:
            stop_reason = "Кнопка 'Посмотреть вакансии' не появилась за 3 минуты — не удалось войти в аккаунт"
            print("❌ " + stop_reason)
            return

        if not click_show_all_vacancies(driver):
            stop_reason = "Не удалось нажать кнопку 'Посмотреть вакансии'"
            print("❌ " + stop_reason)
            return

        print("⏳ Жду загрузки вакансий...")
        loaded = wait_for_element(driver, "[data-qa='vacancy-serp__vacancy_response']", timeout=30)
        if not loaded:
            stop_reason = "Вакансии не загрузились за 30 секунд"
            print("❌ " + stop_reason)
            return

        page = 1
        while applied_count < MAX_APPLICATIONS:
            print("\n📄 Страница " + str(page) + ":")
            vacancies = get_vacancy_cards(driver)

            if not vacancies:
                stop_reason = "На странице " + str(page) + " не найдено подходящих вакансий"
                print("❌ " + stop_reason)
                break

            for vacancy in vacancies:
                if applied_count >= MAX_APPLICATIONS:
                    stop_reason = "Достигнута цель: " + str(MAX_APPLICATIONS) + " откликов"
                    break
                print("\n➡️  " + vacancy["title"] + " | " + vacancy["employer"])
                try:
                    slow_scroll_to_element(driver, vacancy["element"])
                    rp(1, 2)
                except:
                    pass
                success = apply_in_new_tab(driver, vacancy["href"], vacancy["title"], vacancy["employer"])
                if success:
                    applied_count += 1
                    print("  📊 Прогресс: " + str(applied_count) + "/" + str(MAX_APPLICATIONS))
                rp(1, 3)

            if applied_count >= MAX_APPLICATIONS:
                stop_reason = "Достигнута цель: " + str(MAX_APPLICATIONS) + " откликов"
                break

            if not go_to_next_page(driver, page):
                stop_reason = "Страница " + str(page + 1) + " не найдена — вакансии закончились"
                break

            page += 1

    except Exception as e:
        stop_reason = "Критическая ошибка: " + str(e)
        print("❌ Неожиданная ошибка: " + str(e))
        log("❌ КРИТИЧЕСКАЯ ОШИБКА: " + str(e), to_console=False)

    finally:
        print("\n" + "=" * 50)
        print("🏁 Готово! Отправлено: " + str(applied_count) + " из " + str(MAX_APPLICATIONS))
        print("⛔ Причина остановки: " + stop_reason)
        log_session_end(applied_count, stop_reason)
        driver.quit()
        print("🔒 Браузер закрыт")
        print("📋 Лог сохранён: ~/hh_bot/log.txt")

if __name__ == "__main__":
    print("🚀 HH.ru Auto Apply Bot")
    print("=" * 50)
    run_bot()