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
print("Страница открыта, жду 15 секунд...")
time.sleep(15)

print("Текущий URL: " + driver.current_url)
print("Заголовок страницы: " + driver.title)
print("")

all_elements = driver.find_elements(By.CSS_SELECTOR, "[data-qa]")
print("Всего элементов с data-qa: " + str(len(all_elements)))
print("")
print("Первые 30 элементов:")
for el in all_elements[:30]:
    qa = el.get_attribute("data-qa")
    text = el.text[:40].replace("\n", " ")
    print("  " + str(qa) + " | " + text)

input("\nНажми Enter для закрытия...")
driver.quit()
