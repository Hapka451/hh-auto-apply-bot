from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import time
import random
import os
import re
import stat
import json
import shutil
import zipfile
import tarfile
import platform
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

# ==========================================
# НАСТРОЙКИ
# ==========================================

MAX_APPLICATIONS = 197
IGNORED_EMPLOYERS = ["сбер", "sber"]
LOG_FILE = os.path.expanduser("~/hh_bot/log.txt")

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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================


def rp(a=1, b=3):
    t = random.uniform(a, b)
    print("  ⏳ Пауза " + str(round(t, 1)) + " сек...")
    time.sleep(t)


def rp_short():
    time.sleep(random.uniform(0.4, 1.0))


def wait_small(a=0.15, b=0.45):
    time.sleep(random.uniform(a, b))


def slow_scroll_to_element(driver, element):
    location = element.location["y"]
    current = driver.execute_script("return window.pageYOffset")
    distance = location - current - 300
    steps = 10
    step_size = distance / steps if steps else distance
    for _ in range(steps):
        driver.execute_script("window.scrollBy(0, arguments[0])", step_size)
        time.sleep(random.uniform(0.03, 0.08))
    time.sleep(random.uniform(0.4, 0.8))


def get_yandex_binary_path():
    candidates = [
        os.path.expanduser("/Applications/Yandex.app/Contents/MacOS/Yandex"),
        os.path.expanduser("~/Applications/Yandex.app/Contents/MacOS/Yandex"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise RuntimeError(
        "Не найден Yandex Browser. Ожидаемый путь: /Applications/Yandex.app/Contents/MacOS/Yandex"
    )


def get_yandex_browser_versions(binary_path):
    try:
        output = subprocess.check_output([binary_path, "--version"], stderr=subprocess.STDOUT, text=True).strip()
    except Exception as e:
        raise RuntimeError("Не удалось получить версию Яндекс Браузера: " + str(e)) from e

    chromium_match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
    chromium_version = chromium_match.group(1) if chromium_match else ""

    yandex_match = re.search(r"(\d+\.\d+\.\d+)\.\d+", output)
    yandex_release = yandex_match.group(1) if yandex_match else ""

    if not yandex_release:
        # Фолбэк: если в выводе только Chromium-версия, берём первые 3 части.
        parts = chromium_version.split(".") if chromium_version else []
        if len(parts) >= 3:
            yandex_release = ".".join(parts[:3])

    if not chromium_version or not yandex_release:
        raise RuntimeError("Не удалось распознать версию браузера из строки: " + output)

    return {
        "raw": output,
        "chromium": chromium_version,
        "yandex_release": yandex_release,
        "release_tag": f"v{yandex_release}-stable",
    }


def get_driver_version_string(driver_path):
    try:
        output = subprocess.check_output([driver_path, "--version"], stderr=subprocess.STDOUT, text=True).strip()
        return output
    except Exception:
        return ""


def looks_like_matching_driver(driver_path, browser_info):
    if not os.path.exists(driver_path):
        return False
    version_output = get_driver_version_string(driver_path)
    if not version_output:
        return False
    return browser_info["yandex_release"] in version_output or browser_info["chromium"].split(".")[0] in version_output


def github_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "hh-bot/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def pick_yandexdriver_asset(assets):
    system_name = platform.system().lower()
    machine = platform.machine().lower()

    if system_name == "darwin":
        os_tokens = ["mac", "darwin", "osx"]
    elif system_name == "windows":
        os_tokens = ["win", "windows"]
    else:
        os_tokens = ["linux"]

    if machine in ("arm64", "aarch64"):
        arch_good = ["arm64", "aarch64", "m1"]
        arch_bad = ["x64", "amd64", "x86_64", "64"]
    else:
        arch_good = ["x64", "amd64", "x86_64", "mac64", "linux64", "win64"]
        arch_bad = ["arm64", "aarch64", "m1"]

    scored = []
    for asset in assets:
        name = asset.get("name", "").lower()
        score = 0
        if any(token in name for token in os_tokens):
            score += 10
        if any(token in name for token in arch_good):
            score += 6
        if any(token in name for token in arch_bad):
            score -= 8
        if name.endswith(".zip") or name.endswith(".tar.gz") or name.endswith(".tgz"):
            score += 2
        if "driver" in name:
            score += 2
        scored.append((score, asset))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        raise RuntimeError("Не удалось подобрать asset YandexDriver под текущую ОС")
    return scored[0][1]


def extract_driver_archive(archive_path, target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted_paths = []

    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(target_dir)
            extracted_paths = [target_dir / name for name in zf.namelist()]
    elif archive_path.name.endswith(".tar.gz") or archive_path.name.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(target_dir)
            extracted_paths = [target_dir / member.name for member in tf.getmembers()]
    else:
        direct_target = target_dir / archive_path.name
        shutil.copy2(archive_path, direct_target)
        extracted_paths = [direct_target]

    for path in extracted_paths:
        if path.is_dir():
            candidate = path / "yandexdriver"
            if candidate.exists():
                path = candidate
        if path.exists() and path.is_file() and path.name == "yandexdriver":
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return str(path)

    for path in target_dir.rglob("yandexdriver"):
        if path.is_file():
            mode = path.stat().st_mode
            path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return str(path)

    raise RuntimeError("Архив драйвера скачался, но исполняемый файл yandexdriver внутри не найден")


def download_matching_yandexdriver(browser_info):
    release_tag = browser_info["release_tag"]
    print("🌐 Скачиваю подходящий YandexDriver для " + release_tag + " ...")

    release_url = f"https://api.github.com/repos/yandex/YandexDriver/releases/tags/{release_tag}"
    release_data = github_json(release_url)
    assets = release_data.get("assets", [])
    if not assets:
        raise RuntimeError("GitHub release найден, но у него нет assets: " + release_tag)

    asset = pick_yandexdriver_asset(assets)
    asset_name = asset.get("name", "driver_archive")
    download_url = asset.get("browser_download_url")
    if not download_url:
        raise RuntimeError("У выбранного asset нет ссылки на скачивание")

    drivers_root = Path(os.path.expanduser("~/hh_bot/drivers"))
    version_dir = drivers_root / release_tag
    version_dir.mkdir(parents=True, exist_ok=True)

    archive_path = version_dir / asset_name
    if not archive_path.exists():
        req = urllib.request.Request(download_url, headers={"User-Agent": "hh-bot/1.0"})
        with urllib.request.urlopen(req, timeout=120) as response, open(archive_path, "wb") as f:
            shutil.copyfileobj(response, f)

    driver_path = extract_driver_archive(archive_path, version_dir)

    legacy_driver_path = Path(os.path.expanduser("~/hh_bot/yandexdriver"))
    try:
        shutil.copy2(driver_path, legacy_driver_path)
        legacy_driver_path.chmod(legacy_driver_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    print("✅ Скачан драйвер: " + asset_name)
    return driver_path


def build_chrome_options(yandex_binary):
    options = webdriver.ChromeOptions()
    options.binary_location = yandex_binary
    options.add_argument("--user-data-dir=" + os.path.expanduser("~/hh_bot/yandex_profile"))
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--homepage=about:blank")
    options.add_argument("--new-window")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "session.restore_on_startup": 5,
        "session.startup_urls": [],
    })
    return options


def start_chrome_with_driver(driver_path, options):
    from selenium.webdriver.chrome.service import Service as ChromeService

    service = ChromeService(executable_path=driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def create_driver():
    print("🔧 Подготавливаем браузер (Яндекс)...")
    yandex_binary = get_yandex_binary_path()
    browser_info = get_yandex_browser_versions(yandex_binary)
    print("🧭 Версия браузера: " + browser_info["raw"])

    local_driver_path = os.path.expanduser("~/hh_bot/yandexdriver")
    options = build_chrome_options(yandex_binary)
    errors = []

    if looks_like_matching_driver(local_driver_path, browser_info):
        try:
            print("🔩 Пробую локальный yandexdriver...")
            driver = start_chrome_with_driver(local_driver_path, options)
            print("✅ Локальный драйвер подошёл")
            return driver
        except Exception as e:
            errors.append("локальный драйвер: " + str(e))
            print("⚠️  Локальный yandexdriver не запустился, попробую скачать свежий")
    else:
        if os.path.exists(local_driver_path):
            print("⚠️  Локальный yandexdriver не совпадает с версией браузера, скачиваю свежий")
        else:
            print("ℹ️  Локальный yandexdriver не найден, скачиваю свежий")

    try:
        downloaded_driver_path = download_matching_yandexdriver(browser_info)
        driver = start_chrome_with_driver(downloaded_driver_path, options)
        print("✅ Браузер запущен со скачанным драйвером")
        return driver
    except Exception as e:
        errors.append("автозагрузка драйвера: " + str(e))
        raise RuntimeError(
            "Не удалось запустить Яндекс Браузер. "
            + " | ".join(errors)
            + ". Проверь доступ к GitHub и попробуй снова."
        ) from e

def wait_for_element(driver, selector, timeout=180):
    for i in range(timeout // 5):
        try:
            els = driver.find_elements(By.CSS_SELECTOR, selector)
            if len(els) > 0:
                return els
        except Exception:
            pass
        if i % 12 == 0 and i > 0:
            print("⏳ Всё ещё жду... (" + str(i * 5) + " сек)")
        time.sleep(5)
    return []


def click_show_all_vacancies(driver):
    print("🔍 Ищу кнопку 'Посмотреть вакансии'...")
    for _ in range(8):
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
        except Exception:
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
    for _ in range(6):
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
            except Exception:
                title = "Без названия"
            try:
                employer = card.find_element(
                    By.CSS_SELECTOR,
                    "[data-qa='vacancy-serp__vacancy-employer'], [data-qa='vacancy-serp__vacancy-employer-text']"
                ).text.strip()
            except Exception:
                employer = ""
            if is_ignored_employer(employer):
                print("  🚫 Игнорирую: " + employer + " — " + title)
                log("🚫 ПРОПУЩЕНО (игнор): " + employer + " — " + title, to_console=False)
                session_stats["skipped_ignored"] += 1
                continue
            href = ""
            for selector in [
                "h2 a",
                "[data-qa='serp-item__title']",
                "a[data-qa='vacancy-serp__vacancy-title']",
            ]:
                try:
                    link = card.find_element(By.CSS_SELECTOR, selector)
                    href = link.get_attribute("href")
                    if href:
                        break
                except Exception:
                    continue
            if href:
                results.append({"title": title, "href": href, "employer": employer, "element": card})
        except Exception:
            continue
    return results


def detect_extra_requirements(driver):
    response_textareas = driver.find_elements(
        By.CSS_SELECTOR,
        "textarea[data-qa='vacancy-response-popup-form-letter-input'], "
        "textarea[data-qa='vacancy-response-letter-text'], "
        "textarea[name='text']"
    )
    if len(response_textareas) > 0:
        return True, "text question or cover letter"

    question_blocks = driver.find_elements(
        By.CSS_SELECTOR,
        "[data-qa='test-question'], "
        "[data-qa='task-question'], "
        "[data-qa='vacancy-response-popup-form']"
    )
    if len(question_blocks) > 0:
        return True, "test or question form"

    salary_inputs = driver.find_elements(
        By.CSS_SELECTOR,
        "input[data-qa='vacancy-response-popup-form-salary-input'], "
        "input[name='salary']"
    )
    if len(salary_inputs) > 0:
        return True, "salary input detected"

    return False, ""


def is_already_applied(page_text):
    normalized = page_text.lower()
    exact_phrases = [
        "вы уже откликнулись",
        "отклик отправлен ранее",
        "на эту вакансию вы уже откликались",
        "вы откликались на эту вакансию",
    ]
    for phrase in exact_phrases:
        if phrase in normalized:
            return True
    return False


def find_clickable_response_button(driver, timeout=4.0):
    selectors = [
        "a[data-qa='vacancy-response-link-top']",
        "button[data-qa='vacancy-response-link-top']",
        "button[data-qa='vacancy-response-submit-popup']",
        "button[data-qa='vacancy-response-letter-submit']",
        "a[data-qa='vacancy-response-link-bottom']",
        "button[data-qa='vacancy-response-link-bottom']",
    ]

    deadline = time.time() + timeout
    last_error = ""

    while time.time() < deadline:
        for selector in selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    if not btn.is_displayed() or not btn.is_enabled():
                        continue
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    except Exception:
                        pass
                    return btn, selector
            except StaleElementReferenceException:
                last_error = "stale element"
                continue
            except Exception as e:
                last_error = str(e)
                continue
        wait_small(0.15, 0.35)

    return None, last_error


def click_response_button(driver):
    btn, selector_or_error = find_clickable_response_button(driver, timeout=4.0)
    if not btn:
        return False, selector_or_error

    wait_small(0.15, 0.35)
    try:
        btn.click()
        print("  🖱️ Нажал кнопку отклика: " + selector_or_error)
        return True, selector_or_error
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", btn)
            print("  🖱️ Нажал кнопку отклика через JS: " + selector_or_error)
            return True, selector_or_error
        except Exception as e:
            return False, str(e)


def close_extra_tabs_and_return(driver, main_tab):
    try:
        current_tabs = list(driver.window_handles)
        for tab in current_tabs:
            if tab != main_tab:
                driver.switch_to.window(tab)
                driver.close()
        driver.switch_to.window(main_tab)
    except Exception:
        pass




def ensure_single_clean_tab(driver):
    tabs = list(driver.window_handles)
    if not tabs:
        driver.execute_script("window.open('about:blank', '_blank');")
        tabs = list(driver.window_handles)

    main_tab = tabs[0]
    try:
        driver.switch_to.window(main_tab)
    except Exception:
        main_tab = driver.window_handles[0]
        driver.switch_to.window(main_tab)

    for tab in list(driver.window_handles)[1:]:
        try:
            driver.switch_to.window(tab)
            driver.close()
        except Exception:
            pass

    driver.switch_to.window(main_tab)

    try:
        driver.get("about:blank")
    except Exception:
        pass

    return main_tab


def clear_browser_cache_preserve_login(driver):
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})
    except Exception:
        pass


def cleanup_browser_state_preserve_login(driver, stage_text=""):
    prefix = "🧹 "
    if stage_text:
        print(prefix + stage_text)

    try:
        ensure_single_clean_tab(driver)
    except Exception:
        pass

    try:
        clear_browser_cache_preserve_login(driver)
    except Exception:
        pass

    try:
        driver.execute_script("window.sessionStorage.clear();")
    except Exception:
        pass

    try:
        driver.execute_script("window.localStorage.clear();")
    except Exception:
        pass

    try:
        driver.get("about:blank")
    except Exception:
        pass

def apply_in_new_tab(driver, href, title, employer):
    main_tab = driver.current_window_handle
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", href)
        rp(1, 2)

        new_tab = None
        for _ in range(20):
            extra_tabs = [t for t in driver.window_handles if t != main_tab]
            if extra_tabs:
                new_tab = extra_tabs[-1]
                break
            time.sleep(0.1)

        if not new_tab:
            raise Exception("Не удалось открыть новую вкладку")

        driver.switch_to.window(new_tab)
        wait_small(0.4, 0.8)

        try:
            WebDriverWait(driver, 6).until(
                lambda d: d.execute_script("return document.readyState") in ["interactive", "complete"]
            )
        except TimeoutException:
            pass

        driver.execute_script("window.scrollTo(0, 0)")
        wait_small(0.2, 0.5)
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()

        if is_already_applied(page_text):
            print("  ♻️ Отклик уже был: " + title + " | " + employer)
            log("♻️  УЖЕ ОТКЛИКАЛСЯ: " + title + " | " + employer, to_console=False)
            session_stats["skipped_already"] += 1
            close_extra_tabs_and_return(driver, main_tab)
            rp_short()
            return "already_applied"

        clicked, click_info = click_response_button(driver)
        if not clicked:
            print("  ❌ Кнопка откликнуться не найдена: " + click_info)
            log("🔘 ПРОПУЩЕНО (нет кнопки): " + title + " | " + employer, to_console=False)
            session_stats["skipped_no_button"] += 1
            close_extra_tabs_and_return(driver, main_tab)
            rp_short()
            return False

        wait_small(0.8, 1.4)
        driver.execute_script("window.scrollTo(0, 0)")
        wait_small(0.2, 0.5)
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()

        if (
            "вы откликнулись" in page_text
            or "резюме доставлено" in page_text
            or "отклик отправлен" in page_text
        ):
            print("  ✅ Отклик отправлен: " + title + " | " + employer)
            log("✅ ОТКЛИК: " + title + " | " + employer + " | " + href, to_console=False)
            session_stats["applied"] += 1
            close_extra_tabs_and_return(driver, main_tab)
            rp_short()
            return "applied"

        has_requirements_after_click, requirement_reason_after_click = detect_extra_requirements(driver)
        if has_requirements_after_click:
            print("  ⚠️  Требуется письмо/тест (" + requirement_reason_after_click + "), пропускаем...")
            log(
                "📝 ПРОПУЩЕНО (после клика: " + requirement_reason_after_click + "): " + title + " | " + employer,
                to_console=False
            )
            session_stats["skipped_letter"] += 1
            close_extra_tabs_and_return(driver, main_tab)
            rp_short()
            return False

        if is_already_applied(page_text):
            print("  ♻️ Отклик уже был: " + title + " | " + employer)
            log("♻️  УЖЕ ОТКЛИКАЛСЯ: " + title + " | " + employer, to_console=False)
            session_stats["skipped_already"] += 1
            close_extra_tabs_and_return(driver, main_tab)
            rp_short()
            return "already_applied"

        print("  ❌ Не удалось подтвердить отклик, пропускаем")
        log("❌ НЕ ПОДТВЕРЖДЕНО: " + title + " | " + employer, to_console=False)
        session_stats["errors"] += 1
        close_extra_tabs_and_return(driver, main_tab)
        rp_short()
        return False

    except Exception as e:
        print("  ❌ Ошибка: " + str(e))
        log("❌ ОШИБКА: " + title + " | " + employer + " | " + str(e), to_console=False)
        session_stats["errors"] += 1
        close_extra_tabs_and_return(driver, main_tab)
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

    driver = None
    applied_count = 0
    stop_reason = "Неизвестно"

    try:
        driver = create_driver()
        cleanup_browser_state_preserve_login(driver, "Привожу браузер к чистому состоянию без выхода из аккаунта...")
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
                except Exception:
                    pass

                result = apply_in_new_tab(driver, vacancy["href"], vacancy["title"], vacancy["employer"])
                if result == "applied":
                    applied_count += 1
                    print("  📊 Прогресс: " + str(applied_count) + "/" + str(MAX_APPLICATIONS))
                elif result == "already_applied":
                    print("  ♻️  Уже был отклик, в прогресс не считаем")

                rp(1, 3)

            if applied_count >= MAX_APPLICATIONS:
                stop_reason = "Достигнута цель: " + str(MAX_APPLICATIONS) + " откликов"
                break

            if not go_to_next_page(driver, page):
                stop_reason = "Страница " + str(page + 1) + " не найдена — вакансии закончились"
                break

            page += 1

    except KeyboardInterrupt:
        stop_reason = "Остановлено вручную (Ctrl+C)"
        print("\n⏹️  Бот остановлен вручную")
        log("⏹️  ОСТАНОВЛЕНО ВРУЧНУЮ", to_console=False)
    except Exception as e:
        stop_reason = "Критическая ошибка: " + str(e)
        print("❌ Неожиданная ошибка: " + str(e))
        log("❌ КРИТИЧЕСКАЯ ОШИБКА: " + str(e), to_console=False)
    finally:
        print("\n" + "=" * 50)
        print("🏁 Готово! Отправлено: " + str(applied_count) + " из " + str(MAX_APPLICATIONS))
        print("⛔ Причина остановки: " + stop_reason)
        log_session_end(applied_count, stop_reason)
        if driver:
            cleanup_browser_state_preserve_login(driver, "Очищаю состояние браузера перед завершением...")
            driver.quit()
        print("🔒 Браузер закрыт")
        print("📋 Лог сохранён: ~/hh_bot/log.txt")


if __name__ == "__main__":
    print("🚀 HH.ru Auto Apply Bot")
    print("=" * 50)
    run_bot()
