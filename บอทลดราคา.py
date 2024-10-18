from flask_ngrok import run_with_ngrok
from flask import Flask, jsonify, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
from pyngrok import ngrok
import json
import re
import requests
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import chromedriver_autoinstaller
from sentence_transformers import SentenceTransformer, util
from neo4j import GraphDatabase  # ไลบรารีสำหรับเชื่อมต่อกับ Neo4j
import datetime
import ollama
from linebot.models import FlexSendMessage
from linebot.models import BubbleContainer, BoxComponent, TextComponent, ButtonComponent, URIAction



model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')

# setup chrome options
chrome_options = webdriver.ChromeOptions()
#chrome_options.add_argument('--headless')  # ensure GUI is off
#chrome_options.add_argument('--no-sandbox')
#chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_experimental_option("detach", True)

# auto-install chromedriver
chromedriver_autoinstaller.install()



ngrok.set_auth_token("2kEIvt7NHIIWCduI4p3dKDdUNRr_2QLtS7R2EKrUjs3PhETR3")
public_url = ngrok.connect(5000).public_url
print(f"ngrok tunnel {public_url} -> http://127.0.0.1:5000")

def get_ollama_response(prompt):
    # Combine prompt with chat history (if needed)
    full_prompt = f"User: {prompt}\nBot: "  # Format the prompt

    try:
        response = ollama.chat(model='supachai/llama-3-typhoon-v1.5', messages=[
            {
                'role': 'user',
                'content': f'ในฐานะผู้เชี่ยวชาญด้านไอทีที่เป็นมิตรและช่วยเหลือได้ดี โปรดเรียบเรียงประโยคต่อไปนี้ใหม่เป็นภาษาที่กระชับและชัดเจน โดยยังคงเนื้อหาสำคัญไว้ อาจให้คำตอบที่แตกต่างกันได้ แต่ยังอยู่ในบริบทเดิม:\n\"{full_prompt}\" กรุณาตอบเป็นภาษาไทยด้วย',

            },
        ])
        return response['message']['content']
    except Exception as e:
        return f"Error: Unable to get response from Ollama. Details: {str(e)}"




# ฟังก์ชันเชื่อมต่อกับ Neo4j
def get_greeting_responses_from_neo4j():
    driver = GraphDatabase.driver("neo4j://localhost", auth=("neo4j", "Dung@159753"))
    query = "MATCH (g:Hello) RETURN g.name AS name, g.msg_reply AS reply"
    
    with driver.session() as session:
        result = session.run(query)
        greetings = []
        for record in result:
            greetings.append({
                "name": record["name"],
                "reply": record["reply"]
            })
    return greetings

def save_chat_history(user_id, timestamp, question, response_message):
    driver = GraphDatabase.driver("neo4j://localhost", auth=("neo4j", "Dung@159753"))
    try:
        with driver.session() as session:
            session.run(
                """
                MERGE (u:User {id: $user_id})
                CREATE (c:Chat {timestamp: $timestamp, question: $question, response_message: $response_message})
                MERGE (u)-[:SENT]->(c)
                """,
                user_id=user_id, timestamp=timestamp, question=question, response_message=response_message
            )
        print("บันทึกข้อมูลสำเร็จ")
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")


# ฟังก์ชันรับข้อความจากผู้ใช้และตรวจสอบความใกล้เคียง
def find_best_greeting(user_input):
    # ดึงข้อมูล greeting จาก Neo4j
    greetings = get_greeting_responses_from_neo4j()
    
    # สร้าง embeddings สำหรับข้อความที่ได้จากผู้ใช้
    user_input_embedding = model.encode(user_input, convert_to_tensor=True)
    
    best_match = None
    highest_similarity = -1
    
    # วนลูปเปรียบเทียบข้อความผู้ใช้กับข้อความ greeting ใน Neo4j
    for greeting in greetings:
        greeting_name_embedding = model.encode(greeting['name'], convert_to_tensor=True)
        
        # คำนวณความคล้ายคลึงกันระหว่างข้อความผู้ใช้กับข้อความ greeting
        similarity = util.pytorch_cos_sim(user_input_embedding, greeting_name_embedding).item()
        
        if similarity > highest_similarity:
            highest_similarity = similarity
            best_match = greeting
    
    # ถ้าพบข้อความที่มีความคล้ายคลึงสูงสุด
    if best_match and highest_similarity > 0.5:  # กำหนด threshold ความคล้ายคลึงตามต้องการ
        return best_match['reply']
    else:
        return get_ollama_response(user_input)

def fetch_products_today():
    url = "https://www.mercular.com/flash-sale"
    response = requests.get(url)

    if response.ok:
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        box_element = soup.find("div", class_="MuiGrid-root MuiGrid-container MuiGrid-spacing-xs-1 MuiGrid-spacing-sm-2 css-1v1eh07")
        if box_element:
            product_elements = box_element.find_all("div", class_="MuiGrid-root MuiGrid-item MuiGrid-grid-xs-6 MuiGrid-grid-sm-4 MuiGrid-grid-md-3 MuiGrid-grid-lg-auto css-1hzyivn")
            for product_element in product_elements:
                title_element = product_element.find("span", class_="MuiTypography-root MuiTypography-3.0/body2 css-19co7pu")
                sale_element = product_element.find("span", class_="MuiChip-label MuiChip-labelSmall css-tavflp")
                real_price_element = product_element.find("p", class_="MuiTypography-root MuiTypography-3.0/caption css-1b7go33")
                now_price_element = product_element.find("span", class_="MuiTypography-root MuiTypography-3.0/subtitle1 css-ikx1jg")
                img_tag = product_element.find('img', class_='MuiBox-root css-2jod5t')

                # Find the <a> tag that contains the link
                link_element = product_element.find("a", href=True)

                if title_element and sale_element and real_price_element and now_price_element and link_element:
                    img_tag = product_element.find('img', class_='MuiBox-root css-2jod5t')
                    img_url = img_tag['src'] if img_tag else None  # ดึง URL รูปภาพจาก src
                    products.append({
                        'ชื่อสินค้า': title_element.text,
                        'ส่วนลด': sale_element.text.replace('-',''),
                        'ราคาเดิม': real_price_element.text.replace('฿', ''),
                        'ราคาล่าสุด': now_price_element.text.replace('฿', ''),
                        'ลิงค์สั่งซื้อ': "https://www.mercular.com" + link_element['href'],  # Added base URL here
                        'รูปภาพสินค้า': img_url
                    })

        return products
    return []

def fetch_products_tomorrow():
    driver = webdriver.Chrome()
    url = "https://www.mercular.com/flash-sale"
    # ตั้งค่า WebDriver
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    driver.implicitly_wait(60)  # รอให้หน้าโหลด
    html = driver.page_source
    
    # วิเคราะห์ HTML ด้วย BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # รอจนกว่าปุ่มจะคลิกได้ และทำการคลิก
    try:
        # รอจนกว่าปุ่มจะสามารถคลิกได้
        button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="__next"]/div[6]/div/div[2]/div/div[2]/div/button[2]'))
        )

        # เลื่อนหน้าไปที่ปุ่ม
        driver.execute_script("arguments[0].scrollIntoView();", button)

         # คลิกปุ่มผ่าน JavaScript แทนการใช้ .click()
        driver.execute_script("arguments[0].click();", button)

        # รอให้ข้อมูลโหลด
        time.sleep(5)  # รอ 5 วินาทีหลังจากคลิกปุ่ม
    except Exception as e:
        print(f"Error clicking the button: {e}")

    # หลังจากคลิกปุ่มแล้ว ให้ดึงข้อมูลหน้าใหม่อีกครั้ง
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")
    box_element = soup.find("div", class_="MuiGrid-root MuiGrid-container MuiGrid-spacing-xs-1 MuiGrid-spacing-sm-2 css-1v1eh07")
    if box_element:
        product_elements = box_element.find_all("div", class_="MuiGrid-root MuiGrid-item MuiGrid-grid-xs-6 MuiGrid-grid-sm-4 MuiGrid-grid-md-3 MuiGrid-grid-lg-auto css-1hzyivn")
        for product_element in product_elements:
            title_element = product_element.find("span", class_="MuiTypography-root MuiTypography-3.0/body2 css-19co7pu")
            real_price_element = product_element.find("p", class_="MuiTypography-root MuiTypography-3.0/caption css-1b7go33")
            now_price_element = product_element.find("span", class_="MuiTypography-root MuiTypography-3.0/subtitle1 css-ikx1jg")
            img_tag = product_element.find('img', class_='MuiBox-root css-2jod5t')
            # Find the <a> tag that contains the link
            link_element = product_element.find("a", href=True)

            if title_element and real_price_element and now_price_element and link_element:
                img_tag = product_element.find('img', class_='MuiBox-root css-2jod5t')
                img_url = img_tag['src'] if img_tag else None  # ดึง URL รูปภาพจาก src
                products.append({
                    'ชื่อสินค้า': title_element.text,
                    'ราคาเดิม': real_price_element.text.replace('฿', ''),
                    'ราคาล่าสุด': now_price_element.text.replace('฿', ''),
                    'ลิงค์สั่งซื้อ': "https://www.mercular.com" + link_element['href'],
                    'รูปภาพสินค้า': img_url  # Added base URL here
                })

            # Return the result as JSON
        return products
    return []


def return_message(line_bot_api, tk, user_id, msg):
    global products_data, matching_products, keyword, response_message
    quick_reply_back = QuickReply(
        items=[
            QuickReplyButton(action=MessageAction(label="กลับไปเลือกหมวดสินค้า", text="กลับไปเลือกหมวดสินค้า")),
            QuickReplyButton(action=MessageAction(label="ดูรายละเอียดสินค้า", text="ดูรายละเอียดสินค้า"))
        ]
    )

    if msg == "ดูรายละเอียดสินค้า":
        if matching_products:
            quick_reply = generate_product_quick_reply(matching_products)
            line_bot_api.reply_message(
                tk,
                TextSendMessage(
                    text="กรุณาเลือกสินค้าที่ต้องการดูรายละเอียด",
                    quick_reply=quick_reply
                )
            )
        if not matching_products:
            line_bot_api.reply_message(
                tk,
                TextSendMessage(text="ไม่มีสินค้าที่สามารถดูรายละเอียดได้ กรุณาเลือกหมวดสินค้าหรือเริ่มต้นใหม่", quick_reply=quick_reply_back)
            )
    
    elif msg.startswith("รายละเอียด "):
        product_details = fetch_product_details_from_user_input(msg, matching_products)
        response_message = product_details

        # ส่งข้อความพร้อมรายละเอียดสินค้าและ Quick Reply
        line_bot_api.reply_message(
            tk, 
            [
                TextSendMessage(text=response_message),  # ข้อความแสดงรายละเอียดสินค้า
                TextSendMessage(
                    text="ต้องการอะไรเพิ่มเติมไหมครับ?", 
                    quick_reply=quick_reply_back  # เพิ่ม Quick Reply
                )
            ]
        )

        # บันทึกประวัติการแชท
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_chat_history(user_id, timestamp, msg, response_message)

    if msg.lower() in ["เริ่มต้นใช้งาน", "start", "กลับไปเลือกหมวดสินค้า"]:
        quick_reply = QuickReply(
            items=[
                QuickReplyButton(action=MessageAction(label="โปรโมชั่นวันนี้", text="โปรโมชั่นวันนี้")),
                QuickReplyButton(action=MessageAction(label="โปรโมชั่นพรุ่งนี้", text="โปรโมชั่นพรุ่งนี้")),
                QuickReplyButton(action=MessageAction(label="สอบถาม Ollama", text="สอบถาม Ollama"))
            ]
        )
        line_bot_api.reply_message(
            tk,
            TextSendMessage(
                text="คุณต้องการเลือกโปรโมชั่นวันไหน?",
                quick_reply=quick_reply
            )
        )

    elif msg in ["โปรโมชั่นวันนี้", "โปรโมชั่นพรุ่งนี้"]:
        if msg == "โปรโมชั่นวันนี้":
            products_data = fetch_products_today()
        else:
            products_data = fetch_products_tomorrow()

        quick_reply_category = create_category_quick_reply()
        line_bot_api.reply_message(tk, TextSendMessage(text="เลือกหมวดสินค้าที่คุณสนใจ", quick_reply=quick_reply_category))

    elif msg == "หูฟัง":  
        matching_products = [product for product in products_data if "หูฟัง" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "หูฟัง"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "ลำโพง":
        matching_products = [product for product in products_data if "ลำโพง" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "ลำโพง"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "เก้าอี้":
        matching_products = [product for product in products_data if "เก้าอี้" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "เก้าอี้"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "เมาส์":
        matching_products = [product for product in products_data if "เมาส์" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "เมาส์"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "คีบอร์ด" or msg == "คีย์บอร์ด":
        matching_products = [product for product in products_data if "คีบอร์ด" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "คีบอร์ด"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "จอคอม":
        matching_products = [product for product in products_data if "จอ" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "จอคอม"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "ขาตั้งจอ":
        matching_products = [product for product in products_data if "ขาตั้งจอ" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "ขาตั้งจอ"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "โน๊ตบุ๊ค":
        matching_products = [product for product in products_data if "โน๊ตบุ๊ค" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "โน๊ตบุ๊ค"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "คีย์แคป":
        matching_products = [product for product in products_data if "คีย์แคป" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "คีย์แคป"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    elif msg == "จอย":
        matching_products = [product for product in products_data if "จอย" in product['ชื่อสินค้า']]
        quick_reply_sort = create_sort_quick_reply()
        keyword = "จอย"
        line_bot_api.reply_message(tk, TextSendMessage(text="คุณต้องการเรียงลำดับราคาสินค้าอย่างไร?", quick_reply=quick_reply_sort))

    
    elif any(sort_option in msg for sort_option in ["ราคาลดจากน้อยไปมาก", "ราคาลดจากมากไปน้อย", "ส่วนลดจากน้อยไปมาก", "ส่วนลดจากมากไปน้อย", "ราคาเดิมจากน้อยไปมาก", "ราคาเดิมจากมากไปน้อย"]):
            sort_type = determine_sort_type(msg)
            matching_products = sort_products(matching_products, sort_type)
            response_message = generate_flex_message(matching_products, keyword)  # ใช้ Flex Message

            # ส่งทั้ง Flex Message และข้อความที่มี Quick Reply ในลิสต์เดียวกัน
            line_bot_api.reply_message(
                tk, 
                [
                    FlexSendMessage(alt_text="รายการสินค้า", contents=response_message),
                    TextSendMessage(
                        text="ต้องการอะไรเพิ่มไหมครับ",
                        quick_reply=quick_reply_back  # เพิ่ม Quick Reply
                    )
                ]
            )
    if "สอบถาม Ollama" in msg:
    # Extract the user's input that follows the command
        user_input = msg.replace("สอบถาม Ollama", "").strip()  # Get the actual question

    # Get response from Ollama using the user's input
        response = get_ollama_response(user_input)

        try:
            line_bot_api.reply_message(tk, TextSendMessage(text=response))
        except Exception as e:
            print(f"Error sending message: {e}")  # Log any error

    # Prompt for the next question
        line_bot_api.reply_message(tk, TextSendMessage(text="ถามอะไรดีครับ?"))  # Ask for the next question
    
    else:
        reply_message = find_best_greeting(msg)
        response = ""  # กำหนดค่าเริ่มต้นให้กับ response

        if reply_message:
            response = find_best_greeting(msg)
            response_message = str(response)
            line_bot_api.reply_message(tk, TextSendMessage(text=response_message)) #ประเด็น

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_chat_history(user_id, timestamp, msg, response_message)

def generate_flex_message(matching_products, keyword):
    flex_contents = {
        "type": "carousel",
        "contents": []
    }

    for product in matching_products:
        flex_contents['contents'].append({
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": product['รูปภาพสินค้า'],
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": product['ชื่อสินค้า'], "weight": "bold", "size": "md", "wrap": True},
                    {"type": "box", "layout": "baseline", "contents": [
                        {"type": "text", "text": "ราคาเดิม:", "size": "sm", "color": "#aaaaaa"},
                        {"type": "text", "text": product['ราคาเดิม'], "size": "sm", "color": "#ff0000", "decoration": "line-through"}
                    ]},
                    {"type": "box", "layout": "baseline", "contents": [
                        {"type": "text", "text": "ราคาล่าสุด:", "size": "sm", "color": "#aaaaaa"},
                        {"type": "text", "text": product['ราคาล่าสุด'], "size": "sm", "color": "#00ff00"}
                    ]},
                    {"type": "box", "layout": "baseline", "contents": [
                        {"type": "text", "text": "ส่วนลด:", "size": "sm", "color": "#aaaaaa"},
                        {"type": "text", "text": product.get('ส่วนลด', 'ยังไม่ได้แจ้ง'), "size": "sm", "color": "#ff0000"}
                    ]}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "label": "ดูรายละเอียด",
                            "uri": product['ลิงค์สั่งซื้อ']
                        },
                        "style": "primary"
                    }
                ]
            }
        })
    
    return {"type": "carousel", "contents": flex_contents['contents']}

def determine_sort_type(msg):
    if "ราคาลดจากน้อยไปมาก" in msg:
        return "price_asc"
    elif "ราคาลดจากมากไปน้อย" in msg:
        return "price_desc"
    elif "ส่วนลดจากน้อยไปมาก" in msg:
        return "discount_asc"
    elif "ส่วนลดจากมากไปน้อย" in msg:
        return "discount_desc"
    elif "ราคาเดิมจากน้อยไปมาก" in msg:
        return "original_price_asc"
    elif "ราคาเดิมจากมากไปน้อย" in msg:
        return "original_price_desc"

def sort_products(products, sort_type):
    key_map = {
        "price_asc": lambda x: float(x['ราคาล่าสุด'].replace(',', '').replace('฿', '')),
        "price_desc": lambda x: float(x['ราคาล่าสุด'].replace(',', '').replace('฿', '')),
        "discount_asc": lambda x: float(x['ส่วนลด'].replace('%', '')),
        "discount_desc": lambda x: float(x['ส่วนลด'].replace('%', '')),
        "original_price_asc": lambda x: float(x['ราคาเดิม'].replace(',', '').replace('฿', '')),
        "original_price_desc": lambda x: float(x['ราคาเดิม'].replace(',', '').replace('฿', ''))
    }
    reverse_map = {
        "price_desc": True, "discount_desc": True, "original_price_desc": True
    }
    reverse = reverse_map.get(sort_type, False)
    products.sort(key=key_map[sort_type], reverse=reverse)
    return products


# ฟังก์ชันสร้าง Quick Reply สำหรับการเรียงลำดับ
def create_sort_quick_reply():
    return QuickReply(
        items=[
            QuickReplyButton(action=MessageAction(label="ราคาลดจากน้อยไปมาก", text="ราคาลดจากน้อยไปมาก")),
            QuickReplyButton(action=MessageAction(label="ราคาลดจากมากไปน้อย", text="ราคาลดจากมากไปน้อย")),
            QuickReplyButton(action=MessageAction(label="ส่วนลดจากน้อยไปมาก", text="ส่วนลดจากน้อยไปมาก")),
            QuickReplyButton(action=MessageAction(label="ส่วนลดจากมากไปน้อย", text="ส่วนลดจากมากไปน้อย")),
            QuickReplyButton(action=MessageAction(label="ราคาเดิมจากมากไปน้อย", text="ราคาเดิมจากมากไปน้อย")),
            QuickReplyButton(action=MessageAction(label="ราคาเดิมจากน้อยไปมาก", text="ราคาเดิมจากน้อยไปมาก"))
        ]
    )

# ฟังก์ชันสร้าง Quick Reply สำหรับเลือกหมวดสินค้า
def create_category_quick_reply():
    return QuickReply(
        items=[
            QuickReplyButton(action=MessageAction(label="หูฟัง", text="หูฟัง")),
            QuickReplyButton(action=MessageAction(label="ลำโพง", text="ลำโพง")),
            QuickReplyButton(action=MessageAction(label="เก้าอี้", text="เก้าอี้")),
            QuickReplyButton(action=MessageAction(label="เมาส์", text="เมาส์")),
            QuickReplyButton(action=MessageAction(label="คีบอร์ด", text="คีย์บอร์ด")),
            QuickReplyButton(action=MessageAction(label="จอคอม", text="จอคอม")),
            QuickReplyButton(action=MessageAction(label="ขาตั้งจอ", text="ขาตั้งจอ")),
            QuickReplyButton(action=MessageAction(label="โน๊ตบุ๊ค", text="โน๊ตบุ๊ค")),
            QuickReplyButton(action=MessageAction(label="คีย์แคป", text="คีย์แคป")),
            QuickReplyButton(action=MessageAction(label="จอย", text="จอย")),
        ]
    )

#สร้าง quick reply ของสินค้าที่กรอง
def generate_product_quick_reply(matching_products):
    quick_reply_items = []
    
    for product in matching_products:
        original_product_name = product['ชื่อสินค้า']  # เก็บชื่อสินค้าต้นฉบับ
        product_name = original_product_name[:20] if len(original_product_name) > 20 else original_product_name
        
        quick_reply_items.append(
            QuickReplyButton(
                action=MessageAction(label=product_name, text=f"รายละเอียด {original_product_name}")  # ใช้ชื่อสินค้าต้นฉบับในข้อความ
            )
        )
    
    return QuickReply(items=quick_reply_items)





def fetch_product_details_from_user_input(user_message, products):
    if user_message.startswith("รายละเอียด "):
        product_name = user_message.split("รายละเอียด ", 1)[1]  # นี่คือชื่อที่ส่งมาจาก quick reply

        # ค้นหาสินค้าโดยใช้ชื่อสินค้าต้นฉบับที่ไม่ถูกตัด
        product = next((p for p in products if p['ชื่อสินค้า'] == product_name), None)
        if product:
            details = fetch_product_details(product['ลิงค์สั่งซื้อ'])
            return details
        else:
            return "ไม่พบรายละเอียดสินค้าสำหรับ input"

    return "ไม่มีสินค้าที่ตรงกับชื่อที่เลือก"


def fetch_product_details(link):
    # เติม #content ที่ท้ายลิงก์
    link_with_content = f"{link}#product-spec"

    # ใช้ requests และ BeautifulSoup ในการดึงข้อมูลจากลิงค์
    import requests
    from bs4 import BeautifulSoup
    
    response = requests.get(link_with_content)
    mysoup = BeautifulSoup(response.content, 'html.parser')
    box_element = mysoup.find("div", class_="product-tabpanel MuiBox-root css-11g9ewz")
    table_spec = box_element.find_all("div", class_="product-spec-row css-14283da")

    # สร้าง list สำหรับเก็บข้อมูลที่วนลูป
    result_list = []
    for spec in table_spec:
        detail_element_1 = spec.find("div", class_ ="MuiBox-root css-zg07nj")
        detail_element_2 = spec.find("div", class_ ="MuiBox-root css-qujboz")
        if detail_element_1 and detail_element_2:  # ตรวจสอบว่ามี element ก่อน
            title = detail_element_1.text.strip()  # ลบช่องว่างที่ไม่จำเป็น
            answer = detail_element_2.text.strip()
            result_list.append(f"{title} ⏩ {answer}\n")
    
    # สร้างข้อความจาก result_list เพื่อส่งไปยัง LINE API
    response_message = "สเปคของสินค้า:\n" + "\n".join(result_list)
    return response_message




app = Flask(__name__)

@app.route("/", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)
    try:
        json_data = json.loads(body)
        access_token = 'VUNP4fFnr9ca/qtw9TGqrv1a8rGI0ehjow0hRCEXNnD+m4kRHG3+af7oq+14U0Hy6j7wnnQSnnnTqnwuqXWfvILDE6+ayQwkVHgmjtu7LzegDOPVEDL3YTtMiBWgaFwhskzP2fowWs8FZW4OtsnPFwdB04t89/1O/w1cDnyilFU='
        secret = 'd3f2df8906e5ca76dcdc8b438cb87ac4'
        line_bot_api = LineBotApi(access_token)
        handler = WebhookHandler(secret)
        signature = request.headers['X-Line-Signature']

        handler.handle(body, signature)

        msg = json_data['events'][0]['message']['text']
        tk = json_data['events'][0]['replyToken']
        user_id = json_data['events'][0]['source']['userId']

        return_message(line_bot_api, tk, user_id, msg)

        print(msg, tk)
    except InvalidSignatureError:
        return 'Invalid signature. Please check your channel access token/secret.', 400
    except Exception as e:
        print(f"Error: {e}")
        print(body)

    return 'OK'

if __name__ == '__main__':
    app.run()  # ไม่ต้องระบุ port เพราะ run_with_ngrok จะจัดการให้
