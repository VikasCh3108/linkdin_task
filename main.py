import time
import json
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import openai
from dotenv import load_dotenv
import os

# Load OpenAI key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- SPAM CHECK LOGIC ---
def is_spam_message(message_content):
    prompt = f"Classify the following message strictly as 'Spam' or 'Not Spam'.\n\nMessage: {message_content}\n\nRespond with only 'Spam' or 'Not Spam'."
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0
        )
        result = response.choices[0].message.content.strip()
        # Normalize output just in case
        if 'spam' in result.lower() and 'not' not in result.lower():
            return 'Spam'
        else:
            return 'Not Spam'
    except Exception as e:
        return f"Error: {str(e)}"

def check_messages_for_spam(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for conversation in data:
        for msg in conversation.get('messages', []):
            content = msg.get('content', '')
            result = is_spam_message(content)
            msg['spam_check'] = result
            print(f"Sender: {msg.get('sender')}, Spam Check: {result}\nMessage: {content}\n")
    with open('linkedin_messages_spam_checked.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- SCRAPING LOGIC AS FUNCTION ---
import pickle

def fetch_and_save_linkedin_messages():
    # Wait until 16:46 before proceeding
    target_time = datetime.now().replace(hour=16, minute=46, second=0, microsecond=0)
    now = datetime.now()
    if now < target_time:
        wait_seconds = (target_time - now).total_seconds()
        print(f"Waiting until 16:46 ({int(wait_seconds)} seconds)...")
        time.sleep(wait_seconds)
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    cookies_path = "cookies.pkl"
    # Try to load cookies if they exist
    if os.path.exists(cookies_path):
        driver.get("https://www.linkedin.com/")
        with open(cookies_path, "rb") as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                # Selenium expects expiry to be int, not float
                if isinstance(cookie.get('expiry', None), float):
                    cookie['expiry'] = int(cookie['expiry'])
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    pass
        driver.get("https://www.linkedin.com/messaging/")
        print("Loaded cookies and navigated to messages page.")
    else:
        driver.get("https://www.linkedin.com/login")
        try:
            email = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            password = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "password"))
            )
            for char in "khemrajm1947@gmail.com":
                email.send_keys(char)
                time.sleep(0.1)
            time.sleep(1)
            for char in "Khemraj@55":
                password.send_keys(char)
                time.sleep(0.1)
            time.sleep(1)
            password.send_keys(Keys.RETURN)
            print("Waiting for login to complete...")
            time.sleep(5)
            # Save cookies after login
            with open(cookies_path, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
            print("Cookies saved to cookies.pkl.")
            driver.get("https://www.linkedin.com/messaging/")
        except Exception as e:
            print(f"An error occurred during login: {str(e)}")
            driver.quit()
            return
    try:
        print("Finding conversations...")
        # Only select unread conversations (usually have 'msg-conversation-card--unread' in their class)
        unread_conversations = driver.find_elements(By.XPATH, "//li[contains(@class, 'msg-conversation-card--unread')]")
        total_conversations = driver.find_elements(By.XPATH, "//li[contains(@class, 'msg-conversation-listitem')]")
        num_unread = len(unread_conversations)
        num_total = len(total_conversations)
        num_read = num_total - num_unread
        print(f"Total conversations: {num_total}")
        print(f"Unread conversations: {num_unread}")
        print(f"Read conversations: {num_read}")
        conversations = unread_conversations
        messages_data = []
        for i, conv in enumerate(conversations[:5]):
            print(f"Processing conversation {i+1}/5...")
            conv.click()
            time.sleep(3)
            chat_messages = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, "//div[contains(@class, 'msg-s-event-listitem')]"))
            )
            conversation_messages = []
            for msg in chat_messages:
                try:
                    sender = msg.find_element(By.CLASS_NAME, "msg-s-message-group__name").text
                    content = msg.find_element(By.CLASS_NAME, "msg-s-event-listitem__body").text
                    conversation_messages.append({
                        "sender": sender,
                        "content": content
                    })
                except:
                    pass
            messages_data.append({
                "conversation_id": i + 1,
                "messages": conversation_messages
            })
            # Determine spam status for the conversation (based on latest message)
            if conversation_messages:
                last_message = conversation_messages[-1]["content"]
                spam_status = is_spam_message(last_message)
                print(f"Spam status for conversation {i+1}: {spam_status}")
                if spam_status == 'Spam':
                    # Log spam message
                    with open('spam_and_error_log.txt', 'a', encoding='utf-8') as logf:
                        logf.write(f"[SPAM] Conversation {i+1}: {last_message}\n")
                    # Automate reporting as spam (UI steps)
                    try:
                        # Click the 'More' (three dots) button in conversation header
                        more_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'More actions')]"))
                        )
                        more_btn.click()
                        time.sleep(1)
                        # Click 'Report' or similar option
                        report_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Report') or contains(text(), 'Report conversation')]"))
                        )
                        report_btn.click()
                        time.sleep(1)
                        # Select 'Promotional or Spam' option
                        spam_option = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//label[contains(., 'Promotional or Spam')]"))
                        )
                        spam_option.click()
                        time.sleep(1)
                        # Submit the report
                        submit_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Submit') or contains(text(), 'Report')]"))
                        )
                        submit_btn.click()
                        print(f"Conversation {i+1} reported as spam.")
                    except Exception as e:
                        print(f"Could not complete spam report automation for conversation {i+1}: {e}")
                        with open('spam_and_error_log.txt', 'a', encoding='utf-8') as logf:
                            logf.write(f"[ERROR][SPAM_REPORT] Conversation {i+1}: {e}\n")
                else:
                    # Mark as unread (UI steps)
                    try:
                        # Click the 'More' (three dots) button in conversation header
                        more_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'More actions')]"))
                        )
                        more_btn.click()
                        time.sleep(1)
                        # Click 'Mark as unread' option
                        mark_unread_btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Mark as unread')]"))
                        )
                        mark_unread_btn.click()
                        print(f"Conversation {i+1} marked as unread.")
                    except Exception as e:
                        print(f"Could not mark conversation {i+1} as unread: {e}")
                        with open('spam_and_error_log.txt', 'a', encoding='utf-8') as logf:
                            logf.write(f"[ERROR][MARK_UNREAD] Conversation {i+1}: {e}\n")
            time.sleep(1)
        print("Saving messages to JSON file...")
        with open("linkedin_messages.json", "w", encoding="utf-8") as file:
            json.dump(messages_data, file, indent=4, ensure_ascii=False)
        print("Messages saved to linkedin_messages.json")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        print("Closing browser...")
        driver.quit()

# --- SCHEDULER LOGIC ---
def run_scheduled_inbox_check():
    START_HOUR = 13
    START_MINUTE = 0
    now = datetime.now()
    start_time = now.replace(hour=START_HOUR, minute=START_MINUTE, second=0, microsecond=0)
    if now > start_time:
        start_time = start_time + timedelta(days=1)
    wait_seconds = (start_time - now).total_seconds()
    print(f"Waiting until {start_time.strftime('%H:%M')} to start inbox check...")
    time.sleep(wait_seconds)
    print("Starting scheduled inbox spam check...")
    while True:
        print(f"Checking inbox at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")
        fetch_and_save_linkedin_messages()
        check_messages_for_spam("linkedin_messages.json")
        print("Sleeping for 24 hours...")
        time.sleep(24 * 60 * 60)

if __name__ == "__main__":
    run_scheduled_inbox_check()
