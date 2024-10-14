import os
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Please install the (selenium) library before running

# Get HOST_IP from environment variables
host_ip = os.getenv("HOST_IP")
if not host_ip:
    raise RuntimeError("HOST_IP environment variable is not set.")

# Configuration
MANAGER_URL = f"http://{host_ip}:4444/wd/hub"
print(f"Selenium HUB URL: {MANAGER_URL}")

# Set JENKINS_URL using HOST_IP
JENKINS_URL = f"https://{host_ip}:8443"
print(f"Jenkins URL: {JENKINS_URL}")

# Get selenium hub ip address
def get_selenium_hub():
    """Get selenium server url."""
    build_url = os.getenv("BUILD_URL")
    task_case_str = os.getenv("testCases")
    if task_case_str:
        load = task_case_str.count(",") + 1
        if load > 12:
            load = 12
    else:
        return None

    for _ in range(60):
        data = {
            'build_url': build_url,
            'load': load
        }
        json_data = json.dumps(data)
        headers = {'Content-Type': 'application/json'}
        response = requests.post(MANAGER_URL, data=json_data, headers=headers)
        res_dir = json.loads(response.text)
        if res_dir.get("result") == "ready":
            return res_dir.get("selenium_hub")
        time.sleep(5)
    return None

# Determine SELENIUM_GRID_URL based on HOST_LOCALE
host_locale = os.getenv("HOST_LOCALE")
if host_locale == "aws_test":
    SELENIUM_GRID_URL = get_selenium_hub()
    USERNAME = "aauto_task"
    PASSWORD = "c60$8Fwwic"
    if SELENIUM_GRID_URL is None:
        raise RuntimeError("Failed to obtain Selenium Hub URL for aws_test.")
elif host_locale == "chengdu":
    SELENIUM_GRID_URL = f"http://{host_ip}:4444/wd/hub"
    USERNAME = "test"
    PASSWORD = "123.com@123"
else:
    raise RuntimeError("Unsupported HOST_LOCALE value.")

def login_to_jenkins(driver):
    """Log in to Jenkins."""
    driver.get(f"{JENKINS_URL}/login")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "j_username")))

    driver.find_element(By.NAME, "j_username").send_keys(USERNAME)
    driver.find_element(By.NAME, "j_password").send_keys(PASSWORD)
    driver.find_element(By.NAME, "j_password").send_keys(Keys.RETURN)

    WebDriverWait(driver, 20).until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), "Welcome to the test env"))
    time.sleep(10)

def wait_for_text_in_body(driver, text, timeout=600, interval=2):
    """Refresh the page every interval seconds until the specified text is found in the body or timeout occurs."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        driver.refresh()
        if text in driver.find_element(By.TAG_NAME, "body").text:
            return True
        time.sleep(interval)
    return False

def wait_for_login_page(driver, timeout=300, interval=2):
    """Wait until the login page is displayed."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            driver.refresh()
            WebDriverWait(driver, interval).until(EC.presence_of_element_located((By.NAME, "j_username")))
            return True
        except TimeoutException:
            pass
    return False

def upgrade_jenkins_version(driver):
    """Upgrade Jenkins version."""
    try:
        login_to_jenkins(driver)

        driver.get(f"{JENKINS_URL}/manage")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        upgrade_button = None
        for _ in range(10):  # Try refreshing 10 times
            try:
                upgrade_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Or Upgrade Automatically')]"))
                )
                if upgrade_button:
                    break
            except (NoSuchElementException, TimeoutException):
                time.sleep(10)
                driver.refresh()

        if not upgrade_button:
            print("Upgrade button not found after 10 attempts. Upgrade failed.")
            return

        upgrade_button.click()
        print("Successfully clicked upgrade button")

        try:
            restart_checkbox = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Restart Jenkins when installation is complete and no jobs are running')]"))
            )
            restart_checkbox.click()
            print("Successfully checked 'Restart Jenkins when installation is complete and no jobs are running' checkbox")
        except (NoSuchElementException, TimeoutException):
            print("Could not find restart Jenkins checkbox or timeout occurred")

        WebDriverWait(driver, 10).until(EC.staleness_of(upgrade_button))
        print("Jenkins version upgrade complete")

        # Wait for the login page to reappear
        if wait_for_login_page(driver):
            print("Login page reappeared after upgrade")
        else:
            print("Timeout waiting for login page after upgrade")

    except TimeoutException as e:
        print(f"Timeout exception: {e}")
    except NoSuchElementException as e:
        print(f"Element not found exception: {e}")
    except Exception as e:
        print(f"Other exception: {e}")

def upgrade_jenkins_plugins(driver):
    """Upgrade Jenkins plugins."""
    try:
        login_to_jenkins(driver)

        driver.get(f"{JENKINS_URL}/pluginManager")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "filter-box")))

        update_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Check now')]"))
        )
        update_button.click()
        print("Clicked 'Check now' button to check for updates")

        WebDriverWait(driver, 60).until(EC.invisibility_of_element_located((By.XPATH, "//div[@class='jenkins-spinner']")))

        updates_element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'task-link') and .//span[text()='Updates']]"))
        )
        updates_element.click()
        print("Successfully clicked 'Updates' tab")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "filter-box")))

        update_all_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "jenkins-table__checkbox"))
        )
        update_all_button.click()
        print("Successfully selected all plugin updates")

        update_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "button-update"))
        )
        update_button.click()
        print("Clicked 'Update' button")

        try:
            restart_checkbox = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//label[contains(text(), 'Restart Jenkins when installation is complete and no jobs are running')]"))
            )
            restart_checkbox.click()
            print("Checked 'Restart Jenkins when installation is complete and no jobs are running' checkbox")
        except NoSuchElementException:
            print("Could not find checkbox label")
        except TimeoutException:
            print("Timeout waiting for checkbox label")

        # Wait for Jenkins to restart
        if wait_for_text_in_body(driver, "Please wait while Jenkins is restarting"):
            print("Jenkins restart complete")
        else:
            print("Timeout: Did not find 'Please wait while Jenkins is restarting'")

    except TimeoutException as e:
        print(f"Timeout exception: {e}")
    except NoSuchElementException as e:
        print(f"Element not found exception: {e}")
    except Exception as e:
        print(f"Other exception: {e}")

if __name__ == "__main__":
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--ignore-certificate-errors")

    driver = webdriver.Remote(command_executor=SELENIUM_GRID_URL, options=chrome_options)

    try:
        upgrade_jenkins_version(driver)
        upgrade_jenkins_plugins(driver)
    finally:
        driver.quit()
