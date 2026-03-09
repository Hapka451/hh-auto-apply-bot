import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import os

options = uc.ChromeOptions()
options.add_argument("--user-data-dir=" + os.path.expanduser("~/hh_bot/chrome_profile"))
options.add_argument("--no-sandbox")
driver = uc.Chrome(options=options)
driver.maximize_window()

driver.get("https://hh.ru/?hhtmFrom=resume_list")
print("Жду загрузки...")
time.sleep(10)

# Скроллим вниз несколько раз
print("Скроллю страницу...")
for i in range(5):
    driver.execute_script("window.scrollBy(0, 500)")
    time.sleep(2)

all_elements = driver.find_elements(By.CSS_SELECTOR, "[data-qa]")
print("Всего элементов с data-qa: " + str(len(all_elements)))

# Ищем всё что содержит слово vacancy
print("\nЭлементы со словом vacancy в data-qa:")
for el in all_elements:
    qa = el.get_attribute("data-qa") or ""
    if "vacancy" in qa.lower():
        text = el.text[:50].replace("\n", " ")
        print("  " + qa + " | " + text)

input("\nНажми Enter для закрытия...")
driver.quit()
