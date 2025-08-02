import time
import random
import string
import requests
import re
import os
import json
from datetime import datetime
from dateutil.parser import parse as parse_date
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
import undetected_chromedriver as uc
import base64
import cv2
import numpy as np
import socket

# ── TempMail API Helpers ──
API_BASE = "https://api.mail.tm"

def check_network_connectivity():
    """Check if the network is reachable by attempting to connect to a known host."""
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except (socket.gaierror, socket.timeout, OSError):
        return False

def create_temp_account():
    if not check_network_connectivity():
        raise Exception("Network is unreachable. Please check your internet connection.")
    
    for attempt in range(5):
        try:
            doms = requests.get(f"{API_BASE}/domains", timeout=10).json()["hydra:member"]
            domain = doms[0]["domain"]
            user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{user}@{domain}"
            pwd = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            resp = requests.post(f"{API_BASE}/accounts", json={"address": email, "password": pwd}, timeout=10)
            if resp.status_code in (200, 201):
                token_resp = requests.post(f"{API_BASE}/token", json={"address": email, "password": pwd}, timeout=10)
                token = token_resp.json().get("token")
                if token:
                    print(f"Created temp email: {email}")
                    return email, pwd, token
            print(f"Account creation attempt {attempt + 1}/5 failed: Status {resp.status_code}")
            time.sleep(2 ** attempt)
        except requests.RequestException as e:
            print(f"TempMail API error (attempt {attempt + 1}/5): {e}")
            time.sleep(2 ** attempt)
    raise Exception("Failed to create temp mail account after retries")

def wait_for_code(token, send_time, timeout=150):
    headers = {"Authorization": f"Bearer {token}"}
    end = time.time() + timeout
    attempt = 0
    max_attempts = 5
    while time.time() < end and attempt < max_attempts:
        try:
            if not check_network_connectivity():
                print(f"Network unreachable during attempt {attempt + 1}/{max_attempts}")
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            msgs = requests.get(f"{API_BASE}/messages", headers=headers, timeout=10).json().get("hydra:member", [])
            print(f"Retrieved {len(msgs)} messages")
            if msgs:
                recent_msgs = [
                    msg for msg in msgs
                    if msg.get("createdAt") and parse_date(msg.get("createdAt")).timestamp() > send_time
                    and ("tiktok" in msg.get("from", {}).get("address", "").lower() or "verification" in msg.get("subject", "").lower())
                ]
                if recent_msgs:
                    latest_msg = max(recent_msgs, key=lambda x: parse_date(x.get("createdAt")).timestamp())
                    print(f"Latest message from: {latest_msg.get('from', {}).get('address', 'unknown')}")
                    body = requests.get(f"{API_BASE}/messages/{latest_msg['id']}", headers=headers, timeout=10).json().get("text", "")
                    print(f"Message body: {body}")
                    code_match = re.search(r'\b\d{6}\b', body)
                    if code_match:
                        code = code_match.group(0)
                        print(f"Extracted code: {code}")
                        return code
            attempt += 1
            time.sleep(2 ** attempt)
        except (requests.RequestException, ValueError) as e:
            print(f"Error fetching messages (attempt {attempt + 1}/{max_attempts}): {e}")
            attempt += 1
            time.sleep(2 ** attempt)
    raise Exception("No valid 6-digit verification code received in tempmail.")

# ── PuzzleSolver for Captcha ──
class PuzzleSolver:
    def __init__(self, base64puzzle, base64piece):
        self.puzzle = base64puzzle
        self.piece = base64piece

    def get_position(self):
        puzzle = self.__background_preprocessing()
        piece = self.__piece_preprocessing()
        matched = cv2.matchTemplate(puzzle, piece, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(matched)
        return max_loc[0]

    def __background_preprocessing(self):
        img = self.__img_to_grayscale(self.puzzle)
        background = self.__sobel_operator(img)
        return background

    def __piece_preprocessing(self):
        img = self.__img_to_grayscale(self.piece)  # Fixed: Use self.piece instead of self.puzzle
        template = self.__sobel_operator(img)
        return template

    def __sobel_operator(self, img):
        scale = 1
        delta = 0
        ddepth = cv2.CV_16S
        img = cv2.GaussianBlur(img, (3, 3), 0)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        grad_x = cv2.Sobel(gray, ddepth, 1, 0, ksize=3, scale=scale, delta=delta, borderType=cv2.BORDER_DEFAULT)
        grad_y = cv2.Sobel(gray, ddepth, 0, 1, ksize=3, scale=scale, delta=delta, borderType=cv2.BORDER_DEFAULT)
        abs_grad_x = cv2.convertScaleAbs(grad_x)
        abs_grad_y = cv2.convertScaleAbs(grad_y)
        grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)
        return grad

    def __img_to_grayscale(self, img):
        return cv2.imdecode(self.__string_to_image(img), cv2.IMREAD_COLOR)

    def __string_to_image(self, base64_string):
        img = base64.b64decode(base64_string)
        return np.frombuffer(img, dtype="uint8")

# ── Fonction pour sauvegarder les cookies ──
def save_cookies(driver, email):
    try:
        cookies = driver.get_cookies()
        cookie_file = f"cookies_{email.split('@')[0]}.txt"
        
        with open(cookie_file, 'w') as f:
            json.dump(cookies, f, indent=4)
        
        print(f"✅ Cookies saved to {cookie_file}")
    except Exception as e:
        print(f"❌ Failed to save cookies: {e}")

# ── XPaths ──
MONTH_DROPDOWN = '//*[@id="loginContainer"]/div[1]/form/div[2]/div[1]/div[1]'  # Provided XPath
DAY_DROPDOWN = '//*[@id="loginContainer"]/div[1]/form/div[2]/div[2]/div[1]'  # Provided XPath
YEAR_DROPDOWN = '//*[@id="loginContainer"]/div[1]/form/div[2]/div[3]/div[1]'  # Provided XPath
SEND_CODE_BTN = '//button[contains(text(), "Send code") or contains(@class, "send-code")]'
CODE_INPUT_FIELD = '//*[@id="loginContainer"]/div[1]/form/div[7]/div/div/input'  # Provided XPath
SUBMIT_BTN = '//button[@type="submit" or contains(text(), "Submit") or contains(@class, "submit")]'
NEXT_BTN = '//div[contains(@class, "signup")]//button[contains(text(), "Next") or contains(@class, "next")]'
CAPTCHA_PUZZLE = '//div[contains(@id, "captcha_container")]//img[contains(@src, "puzzle")]'
CAPTCHA_PIECE = '//div[contains(@id, "captcha_container")]//img[contains(@src, "piece")]'
CAPTCHA_SLIDER = '//div[contains(@id, "captcha_container")]//div[contains(@class, "slider")]'
USERNAME_FIELD = '//*[@id="loginContainer"]/div[1]/form/div[3]'  # Provided XPath
EMAIL_INPUT = '//*[@id="loginContainer"]/div[1]/form/div[5]/div/input'  # Provided XPath
PASSWORD_INPUT = '//*[@id="loginContainer"]/div[1]/form/div[6]/div/input'  # Provided XPath

month_xpaths = [f'//*[@id="Month-options-item-{i}"]' for i in range(12)]
day_xpaths = [f'//*[@id="Day-options-item-{d}"]' for d in (3, 13, 8, 23, 30, 5, 28, 29, 21)]
year_xpath = '//*[@id="Year-options-item-24"]'  # 2000

# ── Password Generator ──
def gen_pass():
    length = random.randint(8, 19)
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    pw = random.choice(string.ascii_letters) + random.choice(string.digits) + random.choice("!@#$%^&*")
    pw += ''.join(random.choice(chars) for _ in range(length - 3))
    return ''.join(random.sample(pw, len(pw)))

# ── Robust submit button click ──
def wait_and_click_submit(driver, wait, xpath, timeout=30):
    try:
        submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
        time.sleep(0.5)
        submit_btn.click()
        print(f"Clicked button with XPath: {xpath}")
    except Exception as e:
        print(f"Failed to click button with XPath {xpath}: {e}")
        raise

# ── Handle Captcha ──
def handle_captcha(driver, wait, timeout=30):
    try:
        puzzle_img = wait.until(EC.presence_of_element_located((By.XPATH, CAPTCHA_PUZZLE))).get_attribute("src").split(",")[1]
        piece_img = wait.until(EC.presence_of_element_located((By.XPATH, CAPTCHA_PIECE))).get_attribute("src").split(",")[1]
        solver = PuzzleSolver(puzzle_img, piece_img)
        x_offset = solver.get_position()
        
        slider = wait.until(EC.element_to_be_clickable((By.XPATH, CAPTCHA_SLIDER)))
        driver.execute_script("arguments[0].scrollIntoView(true);", slider)
        
        action = ActionChains(driver)
        action.click_and_hold(slider).move_by_offset(x_offset, 0).pause(0.5).release().perform()
        time.sleep(2)
        
        try:
            wait.until_not(EC.presence_of_element_located((By.XPATH, CAPTCHA_PUZZLE)))
            print("Captcha solved successfully")
            return True
        except:
            print("Captcha verification failed")
            return False
    except Exception as e:
        print(f"Captcha handling failed: {e}")
        return False

# ── Start ──
start = time.time()  # Initialize start time outside try block
options = uc.ChromeOptions()
options.add_argument("--start-maximized")
driver = None
account_count = 0

try:
    if not check_network_connectivity():
        raise Exception("Initial network check failed. Please check your internet connection.")
    
    driver = uc.Chrome(options=options, headless=False)
    wait = WebDriverWait(driver, 30)  # Increased timeout

    while True:
        account_count += 1
        print(f"\n=== Starting account creation #{account_count} ===")
        
        # Open new tab and switch to it
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        # Create new account
        try:
            email, tm_pwd, tm_token = create_temp_account()
            pw = gen_pass()
        except Exception as e:
            print(f"Failed to create temp account: {e}")
            continue

        # Save credentials early to ensure they are recorded
        credentials = f"Email:{email} Pass:{pw}"
        try:
            if not os.path.exists("working tiktok-accs.txt"):
                open("working tiktok-accs.txt", "a").close()  # Create file if it doesn't exist
            with open("working tiktok-accs.txt", "a") as f:
                f.write(f"{credentials}\n")
            print(f"✅ Saved credentials: {credentials}")
        except Exception as e:
            print(f"Failed to save credentials to working tiktok-accs.txt: {e}")
            # Continue even if file write fails

        try:
            driver.get("https://www.tiktok.com/signup/phone-or-email/email")
            print("Loaded signup page")
            time.sleep(2)  # Allow page to stabilize
        except Exception as e:
            print(f"Failed to load signup page: {e}")
            continue

        # Check for captcha
        try:
            if wait.until(EC.presence_of_element_located((By.XPATH, CAPTCHA_PUZZLE))):
                if not handle_captcha(driver, wait):
                    print("Failed to solve initial captcha, continuing to next iteration")
                    continue
        except:
            print("No initial captcha detected")

        # 1) Month
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, MONTH_DROPDOWN))).click()
            time.sleep(0.5)
            wait.until(EC.element_to_be_clickable((By.XPATH, random.choice(month_xpaths)))).click()
            print("Selected month")
        except Exception as e:
            print(f"Failed to select month: {e}")
            continue

        # 2) Day
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, DAY_DROPDOWN))).click()
            time.sleep(0.5)
            wait.until(EC.element_to_be_clickable((By.XPATH, random.choice(day_xpaths)))).click()
            print("Selected day")
        except Exception as e:
            print(f"Failed to select day: {e}")
            continue

        # 3) Year
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, YEAR_DROPDOWN))).click()
            time.sleep(0.5)
            wait.until(EC.element_to_be_clickable((By.XPATH, year_xpath))).click()
            print("Selected year")
        except Exception as e:
            print(f"Failed to select year: {e}")
            continue

        # 4) Skip username if present and clickable
        try:
            username_field = wait.until(EC.element_to_be_clickable((By.XPATH, USERNAME_FIELD)))
            username_field.click()
            print("Skipped username (pre-email)")
        except:
            print("No username field to skip or not clickable (pre-email)")

        # 5) Fill email & password
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, EMAIL_INPUT))).send_keys(email)
            wait.until(EC.element_to_be_clickable((By.XPATH, PASSWORD_INPUT))).send_keys(pw)
            print("Filled email and password")
        except Exception as e:
            print(f"Failed to fill email and password: {e}")
            continue

        # 6) Send code with retry
        for attempt in range(3):
            try:
                send_code_btn = wait.until(EC.element_to_be_clickable((By.XPATH, SEND_CODE_BTN)))
                driver.execute_script("arguments[0].scrollIntoView(true);", send_code_btn)
                time.sleep(0.3)
                send_time = time.time()
                driver.execute_script("arguments[0].click();", send_code_btn)
                print("Clicked 'Send code' button")
                break
            except Exception as e:
                print(f"Failed to click send code (attempt {attempt + 1}/3): {e}")
                time.sleep(2)
        else:
            print("Failed to click send code button after retries, continuing to next iteration")
            continue

        # 7) Check for captcha after send code with 20-second wait
        try:
            print("Waiting 20 seconds to check for captcha after send code")
            time.sleep(10)
            if wait.until(EC.presence_of_element_located((By.XPATH, CAPTCHA_PUZZLE))):
                print("Captcha detected after send code, attempting to solve")
                if handle_captcha(driver, wait):
                    print("Captcha solved successfully after send code")
                else:
                    print("Failed to solve captcha after send code, continuing anyway")
            else:
                print("No captcha detected after send code")
        except:
            print("No captcha detected after send code (exception caught)")

        # 8) Wait for code
        try:
            code = wait_for_code(tm_token, send_time)
            if not code:
                print("No verification code received in tempmail, continuing to next iteration")
                continue
        except Exception as e:
            print(f"Failed to retrieve verification code: {e}")
            continue

        # 9) Input code with retry
        for attempt in range(3):
            try:
                code_input = wait.until(EC.element_to_be_clickable((By.XPATH, CODE_INPUT_FIELD)))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", code_input)
                code_input.clear()
                code_input.send_keys(code)
                print(f"Entered verification code: {code}")
                time.sleep(1)
                entered_value = code_input.get_attribute("value")
                if entered_value == code:
                    print("Code input verified")
                    break
                else:
                    print(f"Code input mismatch: expected {code}, got {entered_value}")
                    raise Exception("Failed to correctly input verification code")
            except Exception as e:
                print(f"Failed to input code (attempt {attempt + 1}/3): {e}")
                time.sleep(2)
        else:
            print("Failed to input verification code after retries, continuing to next iteration")
            continue

        # 10) Final Submit after code input
        try:
            wait_and_click_submit(driver, wait, SUBMIT_BTN)
            print("Clicked final submit button")
        except Exception as e:
            print(f"Failed to submit form: {e}")
            continue

        # 11) Wait 8 seconds and skip username again
        try:
            time.sleep(8)
            username_field = wait.until(EC.element_to_be_clickable((By.XPATH, USERNAME_FIELD)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", username_field)
            username_field.click()
            print("Skipped username (post-submit)")
        except Exception as e:
            print(f"Failed to skip username (post-submit): {e}")

        # 12) Click Next button
        try:
            next_btn = wait.until(EC.element_to_be_clickable((By.XPATH, NEXT_BTN)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            next_btn.click()
            print("Clicked Next button")
        except Exception as e:
            print(f"Failed to click Next button ({NEXT_BTN}): {e}")

        # 13) Check for captcha after submit
        try:
            if wait.until(EC.presence_of_element_located((By.XPATH, CAPTCHA_PUZZLE))):
                if not handle_captcha(driver, wait):
                    print("Failed to solve captcha after submit, continuing to next iteration")
                    continue
        except:
            print("No captcha after submit")

        # 14) Sauvegarder les cookies après création réussie du compte
        try:
            save_cookies(driver, email)
        except Exception as e:
            print(f"Failed to save cookies: {e}")

        # 15) Clear cookies to reset session
        try:
            driver.delete_all_cookies()
            print("Cleared cookies for next iteration")
        except Exception as e:
            print(f"Failed to clear cookies: {e}")

        # 16) Close current tab and prepare for next iteration
        try:
            if len(driver.window_handles) > 1:
                driver.close()  # Close the current tab
                driver.switch_to.window(driver.window_handles[-1])  # Switch to the last open tab
            print("Closed current tab")
        except Exception as e:
            print(f"Failed to close tab: {e}")

except Exception as e:
    print(f"❌ Critical error: {e}")

except KeyboardInterrupt:
    print("Script stopped manually by user")

finally:
    print(f"⏱ Total runtime: {time.time() - start:.2f} s, Accounts created: {account_count}")
    if driver:
        try:
            driver.quit()
        except Exception as e:
            print(f"Error closing driver: {e}")
    time.sleep(5)