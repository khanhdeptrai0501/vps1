#!/usr/bin/env python3
"""
🖥️ API Server for GitHub Student Verification
Chạy trên VPS Ubuntu đã cài Chromium

Endpoints:
    GET  /           - Trang chủ
    GET  /health     - Kiểm tra server
    POST /render     - Render HTML thành ảnh (base64)
    POST /prepare    - Chuẩn bị data cho GitHub Student (Step 0-5)

Cách dùng:
    pip install flask html2image pillow curl_cffi beautifulsoup4
    python3 api_server.py
"""
from flask import Flask, request, jsonify, send_file
from html2image import Html2Image
import base64
import os
import uuid
import io
import logging
import random
import string
import math
import time
import re
import json
from datetime import date, timedelta, datetime
from bs4 import BeautifulSoup

# curl_cffi cho browser impersonation
USE_CURL_CFFI = True
try:
    from curl_cffi import requests as cffi_requests
    from curl_cffi.requests import Session as CffiSession
except ImportError:
    USE_CURL_CFFI = False
    import requests as std_requests
    from requests import Session as StdSession
    logging.warning("curl_cffi không khả dụng, dùng requests thông thường")

# Import từ project
try:
    from school_data import get_random_school, load_all_schools, generate_fakultas_prodi
    _preloaded = load_all_schools()
    print(f"[Server] Preloaded {len(_preloaded)} schools")
except ImportError:
    logging.warning("school_data.py không tìm thấy, dùng fallback")
    def get_random_school(): return None
    def load_all_schools(): return []
    def generate_fakultas_prodi(): return ("Faculty of IT", "Computer Science")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============ CẤU HÌNH ============
OUTPUT_DIR = "/root/html_output"
if os.name == 'nt':  # Windows
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "html_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

hti = Html2Image(
    output_path=OUTPUT_DIR,
    custom_flags=[
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-software-rasterizer'
    ]
)

# GitHub URLs
URL_2FA = "https://github.com/settings/security"
URL_BENEFITS = "https://github.com/settings/education/benefits"
URL_BILLING = "https://github.com/settings/billing/payment_information"
URL_CONTACT = "https://github.com/account/contact"

# Default values - sẽ bị ghi đè bởi school data
BROWSER_IMPERSONATE = "chrome120"

BASE_HEADERS = {
    'Accept': 'text/vnd.turbo-stream.html, text/html, application/xhtml+xml',
    'Accept-Language': 'en-US,en;q=0.9',
    'Origin': 'https://github.com',
    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Linux"',
}

# ============ SESSION CLASS ============

class CurlCffiSession:
    """Session manager - dùng curl_cffi nếu có, fallback về requests"""
    
    def __init__(self, impersonate=BROWSER_IMPERSONATE):
        self.impersonate = impersonate
        self.cookies = {}
        
        if USE_CURL_CFFI:
            self.session = CffiSession(impersonate=impersonate)
            self.mode = "curl_cffi"
        else:
            self.session = StdSession()
            self.mode = "requests"
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0'
            })
        
    def set_cookies_from_string(self, cookie_string):
        """Parse cookie string và set vào session"""
        for item in cookie_string.split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                self.cookies[key.strip()] = value.strip()
        
        for key, value in self.cookies.items():
            self.session.cookies.set(key, value, domain=".github.com")
        
        logging.info(f"{len(self.cookies)} cookies loaded ({self.mode})")
        return self
    
    def get(self, url, **kwargs):
        """GET request"""
        headers = kwargs.pop('headers', {})
        merged_headers = {**BASE_HEADERS, **headers}
        
        if USE_CURL_CFFI:
            merged_headers.pop('User-Agent', None)
        
        return self.session.get(url, headers=merged_headers, timeout=kwargs.pop('timeout', 30), **kwargs)
    
    def post(self, url, data=None, **kwargs):
        """POST request"""
        headers = kwargs.pop('headers', {})
        merged_headers = {**BASE_HEADERS, **headers}
        
        if USE_CURL_CFFI:
            merged_headers.pop('User-Agent', None)
        
        return self.session.post(url, data=data, headers=merged_headers, timeout=kwargs.pop('timeout', 30), **kwargs)

# ============ HELPER FUNCTIONS ============

def generate_identity():
    """Tạo identity với tên Western"""
    male = [
        ("John", "Smith"), ("Michael", "Johnson"), ("David", "Williams"), 
        ("James", "Brown"), ("Robert", "Jones"), ("William", "Davis"),
    ]
    female = [
        ("Mary", "Smith"), ("Jennifer", "Johnson"), ("Linda", "Williams"), 
        ("Elizabeth", "Brown"), ("Susan", "Jones"), ("Jessica", "Davis"),
    ]
    gender = random.choice(['male', 'female'])
    first, last = random.choice(male) if gender == 'male' else random.choice(female)
    return {"full_name": f"{first} {last}", "first_name": first, "last_name": last, "gender": gender}

def generate_mssv(tahun_masuk=None):
    """Generate MSSV format: YYYYXXXXXX"""
    if tahun_masuk is None:
        tahun_masuk = random.choice([2023, 2024, 2025])
    suffix = ''.join(random.choices(string.digits, k=6))
    return f"{tahun_masuk}{suffix}", tahun_masuk

def generate_dob():
    """Generate date of birth (18-22 tuổi)"""
    return date.today() - timedelta(days=18*365 + random.randint(0, 1500))

def generate_nearby_billing_address():
    """Generate địa chỉ gần trường"""
    streets = [
        "Đường Nguyễn Huệ", "Đường Lê Lợi", "Đường Trần Hưng Đạo", 
        "Đường Hai Bà Trưng", "Đường Lý Thường Kiệt", "Đường Điện Biên Phủ",
    ]
    return f"Số {random.randint(1, 200)}, {random.choice(streets)}, Phường {random.randint(1, 15)}"

def generate_geo_location_tight(lat_center, long_center):
    """Generate GPS gần trường"""
    r = (0.005 + random.random() * 0.025) / 111.0
    theta = random.random() * 2 * math.pi
    new_lat = lat_center + (r * math.cos(theta))
    new_long = long_center + ((r * math.sin(theta)) / math.cos(math.radians(lat_center)))
    return f"{new_lat:.7f}", f"{new_long:.7f}"

# ============ GITHUB FUNCTIONS (Step 0-5) ============

def get_username_from_session(session):
    """Lấy username từ cookie session"""
    urls = [
        "https://github.com/settings/billing/payment_information",
        "https://github.com/settings/profile",
        "https://github.com/"
    ]
    
    for url in urls:
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            page_title = soup.title.string.strip() if soup.title else ""
            
            if "Sign in" in page_title:
                return False, "Cookie Invalid / Expired", "get_username"
            
            meta = soup.find("meta", {"name": "user-login"})
            if meta and meta.get("content"):
                return True, meta.get("content"), None
                
            match = re.search(r'"login":"(.*?)"', resp.text)
            if match and len(match.group(1)) > 2:
                return True, match.group(1), None
                
        except Exception as e:
            continue

    return False, "Username not found", "get_username"

def check_account_age(username):
    """Kiểm tra tuổi tài khoản (phải > 3 ngày)"""
    try:
        import requests
        resp = requests.get(f"https://api.github.com/users/{username}", timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            created_at_str = data.get("created_at")
            
            if not created_at_str:
                return True, 0, None
                
            created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").date()
            age_days = (date.today() - created_at).days
            
            if age_days < 3:
                return False, age_days, "check_age"
            
            return True, age_days, None
            
    except:
        pass
    return True, -1, None

def update_profile_name(session, identity, city):
    """Cập nhật tên profile"""
    try:
        success, username, _ = get_username_from_session(session)
        if not success:
            return False

        resp = session.get("https://github.com/settings/profile")
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        csrf = soup.find('input', {'name': 'authenticity_token'})
        if not csrf:
            return False
            
        timestamp_secret = soup.find('input', {'name': 'timestamp_secret'})
        timestamp = soup.find('input', {'name': 'timestamp'})
        
        payload = {
            '_method': 'put',
            'authenticity_token': csrf['value'],
            'user[profile_name]': identity['full_name'],
            'user[profile_email]': '',
            'user[profile_bio]': '',
            'user[profile_pronouns]': '',
            'user[profile_url]': '',
            'user[profile_twitter_username]': '',
            'user[profile_company]': '',
            'user[profile_location]': f'{city}, Vietnam',
            'user[profile_local_time_zone_name]': '',
            'timestamp': timestamp['value'] if timestamp else str(int(time.time() * 1000)),
            'timestamp_secret': timestamp_secret['value'] if timestamp_secret else ''
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': "https://github.com/settings/profile",
        }
        
        resp = session.post(f"https://github.com/users/{username}", data=payload, headers=headers)
        return resp.status_code in [200, 302]
            
    except Exception as e:
        logging.error(f"update_profile_name error: {e}")
        return False

def add_billing_address(session, identity, address, city, zip_code, country="VN"):
    """Cập nhật địa chỉ thanh toán"""
    try:
        resp = session.get(URL_BILLING)
        soup = BeautifulSoup(resp.text, 'html.parser')

        form = soup.find('form', {'action': '/account/contact'})
        csrf = form.find('input', {'name': 'authenticity_token'}) if form else None
        if not csrf:
            csrf = soup.find('input', {'name': 'authenticity_token'})
        
        if not csrf:
            return False
            
        payload = {
            'authenticity_token': csrf['value'],
            'billing_contact[first_name]': identity['first_name'],
            'billing_contact[last_name]': identity['last_name'],
            'billing_contact[address1]': address,
            'billing_contact[city]': city,
            'billing_contact[country_code]': country,
            'billing_contact[state]': city,
            'billing_contact[postal_code]': zip_code,
            'form_loaded_from': 'BILLING_SETTINGS',
            'target': 'user',
            'contact_type': 'billing',
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': URL_BILLING,
        }
        
        resp = session.post(URL_CONTACT, data=payload, headers=headers)
        return resp.status_code in [200, 302]
            
    except Exception as e:
        logging.error(f"add_billing_address error: {e}")
        return False

def check_2fa_status(session):
    """Kiểm tra 2FA đã bật chưa"""
    try:
        resp = session.get(URL_2FA)
        if "Set up two-factor" in resp.text or "Enable two-factor" in resp.text:
            return False
        return True
    except:
        return False

def check_existing_application(session):
    """Kiểm tra đơn đăng ký hiện có"""
    try:
        resp = session.get(URL_BENEFITS)
        text_lower = resp.text.lower()
        
        if "approved" in text_lower:
            return "approved"
        elif "pending" in text_lower:
            return "pending"
        elif "rejected" in text_lower or "denied" in text_lower:
            return "rejected"
        
        return "none"
    except:
        return "error"

def create_card_image(identity, mssv, dob_obj, khoa, nganh, tahun_masuk, school, process_id):
    """Tạo thẻ sinh viên"""
    html_filename = os.path.join(os.path.dirname(__file__), "generic_card.html")
    output_image = os.path.join(OUTPUT_DIR, f"card_{process_id}.jpg")
    
    if not os.path.exists(html_filename):
        logging.error(f"Template not found: {html_filename}")
        return None, None
    
    with open(html_filename, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Điền thông tin
    mappings = {
        "schoolName": school.get('name', 'University') if school else 'University',
        "cardName": identity['full_name'],
        "cardMSSV": mssv,
        "cardFakultas": khoa,
        "cardProdi": nganh,
        "cardTahunMasuk": str(tahun_masuk),
        "cardIssued": date.today().strftime('%B %d, %Y'),
        "cardValidThru": date(date.today().year + 4, date.today().month, date.today().day).strftime('%B %d, %Y'),
        "cardTTL": dob_obj.strftime('%B %d, %Y'),
    }
    
    for element_id, value in mappings.items():
        el = soup.find(id=element_id)
        if el:
            el.string = value
    
    # Logo trường
    if school and school.get('logo_url'):
        logo_el = soup.find(id="schoolLogo")
        if logo_el:
            logo_el['src'] = school['logo_url']
    
    # Lấy ảnh random
    try:
        gender = identity.get('gender', 'male')
        folder = "men" if gender == "male" else "women"
        photo_url = f"https://randomuser.me/api/portraits/{folder}/{random.randint(0, 99)}.jpg"
        
        if USE_CURL_CFFI:
            photo_resp = cffi_requests.get(photo_url, impersonate=BROWSER_IMPERSONATE, timeout=15)
        else:
            import requests
            photo_resp = requests.get(photo_url, timeout=15)
        
        if photo_resp.status_code == 200:
            photo_b64 = f"data:image/jpeg;base64,{base64.b64encode(photo_resp.content).decode('utf-8')}"
            photo_el = soup.find(id="cardPhoto")
            if photo_el:
                photo_el['src'] = photo_b64
    except Exception as e:
        logging.warning(f"Không lấy được ảnh: {e}")
    
    # Render HTML thành ảnh
    modified_html = str(soup)
    temp_html = os.path.join(OUTPUT_DIR, f"temp_{process_id}.html")
    
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(modified_html)
    
    try:
        hti.size = (700, 550)
        hti.screenshot(html_file=temp_html, save_as=os.path.basename(output_image))
        
        if os.path.exists(output_image) and os.path.getsize(output_image) > 1000:
            with open(output_image, 'rb') as f:
                img_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            # Cleanup
            os.remove(temp_html)
            os.remove(output_image)
            
            return img_base64, mappings
        else:
            logging.error("Card image too small or not created")
            return None, None
            
    except Exception as e:
        logging.error(f"Render error: {e}")
        return None, None
    finally:
        if os.path.exists(temp_html):
            os.remove(temp_html)

# ============ ENDPOINTS ============

@app.route('/', methods=['GET'])
def index():
    """Trang chủ"""
    return """
    <h1>🖥️ GitHub Student API Server</h1>
    <ul>
        <li>GET /health - Kiểm tra server</li>
        <li>POST /render - Render HTML thành ảnh</li>
        <li>POST /prepare - Chuẩn bị data cho GitHub Student (Step 0-5)</li>
    </ul>
    """

@app.route('/health', methods=['GET'])
def health():
    """Kiểm tra server"""
    return jsonify({
        "status": "ok",
        "curl_cffi": USE_CURL_CFFI,
        "output_dir": OUTPUT_DIR
    })

@app.route('/render', methods=['POST'])
def render_base64():
    """Render HTML thành ảnh base64"""
    try:
        data = request.get_json()
        if not data or 'html' not in data:
            return jsonify({"success": False, "error": "Missing 'html' field"}), 400
        
        html_content = data['html']
        width = data.get('width', 700)
        height = data.get('height', 550)
        
        filename = f"render_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        hti.size = (width, height)
        hti.screenshot(html_str=html_content, save_as=filename)
        
        if not os.path.exists(output_path):
            return jsonify({"success": False, "error": "Failed to create image"}), 500
        
        with open(output_path, 'rb') as f:
            img_data = f.read()
        
        os.remove(output_path)
        
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        
        return jsonify({
            "success": True,
            "image": img_base64,
            "format": "png",
            "size": len(img_data)
        })
        
    except Exception as e:
        logging.exception("Error in /render")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/prepare', methods=['POST'])
def prepare():
    """
    Chuẩn bị data cho GitHub Student (Step 0-5)
    
    Input:
        {"cookie": "user_session=xxx; ...", "browser_impersonate": "chrome120"}
    
    Output:
        {
            "success": true,
            "username": "example",
            "student_data": {...},
            "card_base64": "...",
            "geo": {"lat": "...", "lng": "..."},
            ...
        }
    """
    try:
        data = request.get_json()
        if not data or 'cookie' not in data:
            return jsonify({"success": False, "error": "Missing 'cookie' field"}), 400
        
        cookie = data['cookie']
        impersonate = data.get('browser_impersonate', BROWSER_IMPERSONATE)
        process_id = uuid.uuid4().hex[:8]
        
        logging.info(f"[{process_id}] Starting prepare...")
        
        # Step 0: Tạo session và kiểm tra cookie
        session = CurlCffiSession(impersonate=impersonate)
        session.set_cookies_from_string(cookie)
        
        # Step 0.1: Lấy username
        success, username, step = get_username_from_session(session)
        if not success:
            return jsonify({"success": False, "error": username, "step": step})
        
        logging.info(f"[{process_id}] Username: {username}")
        
        # Step 0.2: Kiểm tra tuổi tài khoản
        success, age_days, step = check_account_age(username)
        if not success:
            return jsonify({
                "success": False, 
                "error": f"Account quá mới ({age_days} ngày). Cần > 3 ngày.",
                "step": step
            })
        
        # Lấy school data
        school = get_random_school()
        if not school:
            school = {
                'name': 'Fire Fighting University',
                'id': '122738',
                'lat': 21.0007965,
                'long': 105.7920846,
                'city': 'Hanoi',
                'zip': '100000'
            }
        
        city = school.get('city', 'Hanoi')
        zip_code = school.get('zip', '100000')
        
        # Tạo data sinh viên
        identity = generate_identity()
        mssv, tahun_masuk = generate_mssv()
        khoa, nganh = generate_fakultas_prodi()
        dob = generate_dob()
        address = generate_nearby_billing_address()
        lat, lng = generate_geo_location_tight(school['lat'], school['long'])
        
        # Step 1: Cập nhật profile name
        profile_updated = update_profile_name(session, identity, city)
        logging.info(f"[{process_id}] Profile updated: {profile_updated}")
        
        # Step 2: Cập nhật billing address
        billing_updated = add_billing_address(session, identity, address, city, zip_code)
        logging.info(f"[{process_id}] Billing updated: {billing_updated}")
        
        # Step 3: Kiểm tra 2FA
        has_2fa = check_2fa_status(session)
        if not has_2fa:
            return jsonify({
                "success": False,
                "error": "2FA chưa bật! Vui lòng bật 2FA trước.",
                "step": "check_2fa"
            })
        
        # Step 4: Kiểm tra existing application
        app_status = check_existing_application(session)
        if app_status == "approved":
            return jsonify({
                "success": False,
                "error": "Tài khoản đã có Student Pack!",
                "step": "check_app",
                "app_status": app_status
            })
        
        # Step 5: Tạo thẻ sinh viên
        card_base64, card_data = create_card_image(identity, mssv, dob, khoa, nganh, tahun_masuk, school, process_id)
        if not card_base64:
            return jsonify({
                "success": False,
                "error": "Không thể tạo thẻ sinh viên",
                "step": "create_card"
            })
        
        logging.info(f"[{process_id}] Card created successfully")
        
        # Return all data
        return jsonify({
            "success": True,
            "username": username,
            "account_age_days": age_days,
            "student_data": {
                "full_name": identity['full_name'],
                "first_name": identity['first_name'],
                "last_name": identity['last_name'],
                "gender": identity['gender'],
                "mssv": mssv,
                "tahun_masuk": tahun_masuk,
                "school_name": school.get('name'),
                "school_id": school.get('id'),
                "khoa": khoa,
                "nganh": nganh,
                "dob": dob.isoformat(),
                "address": address,
            },
            "card_base64": card_base64,
            "geo": {
                "lat": lat,
                "lng": lng
            },
            "profile_updated": profile_updated,
            "billing_updated": billing_updated,
            "has_2fa": has_2fa,
            "existing_app_status": app_status
        })
        
    except Exception as e:
        logging.exception("Error in /prepare")
        return jsonify({"success": False, "error": str(e), "step": "unknown"}), 500


@app.route('/webhooks/sepay', methods=['POST'])
def webhook_payment():
    """
    SePay Payment Webhook
    
    Cấu hình trong SePay:
        Webhook URL: http://45.32.116.164:5000/webhooks/sepay
        
    SePay sẽ gửi POST request khi có giao dịch mới.
    """
    try:
        data = request.json or {}
        
        logging.info(f"[Webhook] Received: {json.dumps(data, ensure_ascii=False)[:500]}")
        
        # Validate SePay data
        transfer_type = data.get('transferType', '')
        if transfer_type != 'in':  # Chỉ xử lý tiền vào
            return jsonify({"success": True, "message": "Ignored (not incoming)"})
        
        amount = data.get('transferAmount', 0)
        content = data.get('content', '') or data.get('description', '')
        
        # Tìm order_id trong nội dung chuyển khoản
        # Format có thể là: "ODR_XXXXXXXX" hoặc "ODRXXXXXXXX" (không có underscore)
        import re
        
        # Thử tìm với underscore trước
        match = re.search(r'ODR[_]?([A-Z0-9]{8})', content.upper())
        
        if not match:
            logging.warning(f"[Webhook] No order_id found in: {content}")
            return jsonify({"success": True, "message": "No matching order"})
        
        # Chuẩn hóa payment_ref với underscore
        payment_ref = f"ODR_{match.group(1)}"
        logging.info(f"[Webhook] Found payment_ref: {payment_ref}, amount: {amount}")
        
        # Cập nhật database (sync) và notify user
        try:
            from database import SyncSessionLocal
            from models import VerificationOrder, OrderStatus, User
            from sqlalchemy import select
            
            with SyncSessionLocal() as session:
                # Tìm order
                result = session.execute(
                    select(VerificationOrder).where(VerificationOrder.payment_ref == payment_ref)
                )
                order = result.scalar_one_or_none()
                
                if not order:
                    logging.warning(f"[Webhook] Order not found: {payment_ref}")
                    return jsonify({"success": True, "message": f"Order not found: {payment_ref}"})
                
                if order.status.value != "PENDING_PAYMENT":
                    logging.info(f"[Webhook] Order already processed: {payment_ref}")
                    return jsonify({"success": True, "message": "Already processed"})
                
                # Cập nhật trạng thái
                order.status = OrderStatus.PAID
                order.paid_at = datetime.now()
                session.commit()
                
                logging.info(f"[Webhook] Order {payment_ref} marked as PAID")
                
                # Lấy user telegram_id để notify
                user_result = session.execute(
                    select(User).where(User.id == order.user_id)
                )
                user = user_result.scalar_one_or_none()
                
                if user:
                    # Gửi notification đến internal endpoint để bot notify user
                    try:
                        import requests as req
                        req.post(
                            "http://localhost:5000/internal/notify-payment",
                            json={
                                "telegram_id": user.telegram_id,
                                "order_id": order.id,
                                "payment_ref": payment_ref,
                                "amount": amount
                            },
                            timeout=5
                        )
                    except Exception as notify_err:
                        logging.warning(f"[Webhook] Could not notify: {notify_err}")
                
        except Exception as db_err:
            logging.exception(f"[Webhook] Database error: {db_err}")
        
        return jsonify({
            "success": True, 
            "payment_ref": payment_ref,
            "amount": amount,
            "message": "Payment confirmed"
        })
        
    except Exception as e:
        logging.exception("[Webhook] Error processing payment")
        return jsonify({"success": False, "error": str(e)}), 500


# Biến global để lưu bot instance (được set từ telegram_bot.py)
_telegram_notify_callback = None

def set_telegram_notify_callback(callback):
    """Set callback function để notify qua Telegram."""
    global _telegram_notify_callback
    _telegram_notify_callback = callback


@app.route('/internal/notify-payment', methods=['POST'])
def internal_notify_payment():
    """Internal endpoint để notify user qua Telegram khi payment confirmed."""
    try:
        data = request.json or {}
        telegram_id = data.get('telegram_id')
        order_id = data.get('order_id')
        payment_ref = data.get('payment_ref')
        amount = data.get('amount', 0)
        
        logging.info(f"[Notify] Payment confirmed for user {telegram_id}, order {order_id}")
        
        # Ghi vào file để bot poll (fallback nếu không có callback)
        notify_file = os.path.join(os.path.dirname(__file__), "pending_notifications.json")
        try:
            notifications = []
            if os.path.exists(notify_file):
                with open(notify_file, 'r') as f:
                    notifications = json.load(f)
            
            notifications.append({
                "type": "payment_confirmed",
                "telegram_id": telegram_id,
                "order_id": order_id,
                "payment_ref": payment_ref,
                "amount": amount,
                "timestamp": datetime.now().isoformat()
            })
            
            with open(notify_file, 'w') as f:
                json.dump(notifications, f)
                
        except Exception as file_err:
            logging.warning(f"[Notify] Could not write notification file: {file_err}")
        
        return jsonify({"success": True})
        
    except Exception as e:
        logging.exception("[Notify] Error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/callback/submit', methods=['POST'])
def callback_submit():
    """
    Callback từ VPS2 sau khi submit xong.
    
    Request:
    {
        "order_id": "uuid",
        "success": true/false,
        "message": "...",
        "email_used": "..."
    }
    """
    try:
        data = request.json or {}
        
        order_id = data.get('order_id')
        success = data.get('success', False)
        message = data.get('message', '')
        
        logging.info(f"[Callback] Order {order_id}: success={success}, message={message}")
        
        # TODO: Cập nhật order trong database và notify user qua Telegram
        # Cần tích hợp với telegram_bot để gửi message
        
        return jsonify({
            "success": True,
            "received": True,
            "order_id": order_id
        })
        
    except Exception as e:
        logging.exception("[Callback] Error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/check-status', methods=['POST'])
def check_github_status():
    """
    Check GitHub Student verification status.
    
    Request:
    {
        "cookie": "GitHub cookie string"
    }
    
    Response:
    {
        "success": true,
        "status": "approved" | "denied" | "pending",
        "reasons": ["reason1", "reason2"] // if denied
    }
    """
    try:
        data = request.json
        cookie = data.get('cookie')
        
        if not cookie:
            return jsonify({"success": False, "error": "Cookie required"}), 400
        
        # Parse cookie
        if isinstance(cookie, str):
            cookies = {}
            for item in cookie.split(';'):
                if '=' in item:
                    key, val = item.strip().split('=', 1)
                    cookies[key.strip()] = val.strip()
        else:
            cookies = cookie
        
        # Request GitHub education discount requests page
        url = "https://education.github.com/discount_requests"
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://education.github.com/pack',
        }
        
        if USE_CURL_CFFI:
            sess = cffi_requests.Session()
            resp = sess.get(url, headers=headers, cookies=cookies, impersonate="chrome120")
        else:
            sess = std_requests.Session()
            resp = sess.get(url, headers=headers, cookies=cookies)
        
        if resp.status_code != 200:
            logging.warning(f"[CheckStatus] HTTP {resp.status_code}")
            return jsonify({
                "success": True,
                "status": "pending",
                "message": "Could not fetch status"
            })
        
        # Parse HTML to find latest application status
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Look for status indicators
        status = "pending"
        reasons = []
        
        # Check for "Approved" status
        approved_elements = soup.find_all(text=re.compile(r'Approved', re.I))
        if approved_elements:
            for elem in approved_elements:
                parent = elem.find_parent(['div', 'span', 'p', 'li'])
                if parent and 'Application Type: Student' in str(parent.parent):
                    status = "approved"
                    break
        
        # Check for "Denied" status
        denied_elements = soup.find_all(text=re.compile(r'Denied', re.I))
        if denied_elements and status != "approved":
            for elem in denied_elements:
                parent = elem.find_parent(['div', 'span', 'p', 'li'])
                if parent and 'Application Type: Student' in str(parent.parent):
                    status = "denied"
                    
                    # Try to find denial reasons
                    reasons_section = parent.find_next('ul')
                    if reasons_section:
                        for li in reasons_section.find_all('li'):
                            reason_text = li.get_text(strip=True)
                            if reason_text:
                                reasons.append(reason_text)
                    break
        
        # Check for "Under Review" / "Pending"
        if status == "pending":
            pending_elements = soup.find_all(text=re.compile(r'(Under Review|Pending|Submitted)', re.I))
            if pending_elements:
                status = "pending"
        
        logging.info(f"[CheckStatus] Status: {status}")
        
        return jsonify({
            "success": True,
            "status": status,
            "reasons": reasons if reasons else None
        })
        
    except Exception as e:
        logging.exception("[CheckStatus] Error")
        return jsonify({"success": False, "error": str(e), "status": "pending"}), 500


# ============ MAIN ============

if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════╗
║  🖥️  GitHub Student API Server v3.1                       ║
╠═══════════════════════════════════════════════════════════╣
║  Endpoints:                                               ║
║    GET  /             - Trang chủ                         ║
║    GET  /health       - Kiểm tra server                   ║
║    POST /render       - Render HTML → base64              ║
║    POST /prepare      - Chuẩn bị GitHub Student (b0-b5)   ║
║    POST /check-status - Check verification status         ║
╠═══════════════════════════════════════════════════════════╣
║  curl_cffi: """ + ("✅ OK" if USE_CURL_CFFI else "❌ Not available") + """
║  Output: """ + OUTPUT_DIR + """
╚═══════════════════════════════════════════════════════════╝
    """)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

