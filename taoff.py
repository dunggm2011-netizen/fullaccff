import os
import sys
import json
import time
import math
import random
import logging
import threading
import hashlib
import hmac
import string
import base64
import codecs
import re
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot import types
import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================================================================
# CẤU HÌNH
# ================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8385677064:AAHS5ZqmV9QPka3I1t84lyysLzLsLTp3N6g")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "7564889663").split(",")]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://taoff.onrender.com/webhook")
PORT = int(os.environ.get("PORT", 5000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# ================================================================
# REGION CONFIG
# ================================================================
REGION_LANG = {
    "ME": "ar", "IND": "hi", "ID": "id", "VN": "vi", "TH": "th",
    "BD": "bn", "PK": "ur", "TW": "zh", "CIS": "ru", "SAC": "es", "BR": "pt"
}

REGION_URLS = {
    "IND": "https://client.ind.freefiremobile.com/",
    "ID": "https://clientbp.ggblueshark.com/",
    "BR": "https://client.us.freefiremobile.com/",
    "ME": "https://clientbp.common.ggbluefox.com/",
    "VN": "https://clientbp.ggblueshark.com/",
    "TH": "https://clientbp.common.ggbluefox.com/",
    "CIS": "https://clientbp.ggblueshark.com/",
    "BD": "https://clientbp.ggblueshark.com/",
    "PK": "https://clientbp.ggblueshark.com/",
    "SG": "https://clientbp.ggblueshark.com/",
    "SAC": "https://client.us.freefiremobile.com/",
    "TW": "https://clientbp.ggblueshark.com/"
}

hex_key = "32656534343831396539623435393838343531343130363762323831363231383734643064356437616639643866376530306331653534373135623764316533"
key = bytes.fromhex(hex_key)
GARENA = "RGVtbw=="

# ================================================================
# FILE PATHS
# ================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_FOLDER = os.path.join(CURRENT_DIR, "ACC_REG")
TOKENS_FOLDER = os.path.join(BASE_FOLDER, "TOKENS-JWT")
ACCOUNTS_FOLDER = os.path.join(BASE_FOLDER, "ACCOUNTS")
RARE_ACCOUNTS_FOLDER = os.path.join(BASE_FOLDER, "RARE ACCOUNTS")
COUPLES_ACCOUNTS_FOLDER = os.path.join(BASE_FOLDER, "COUPLES ACCOUNTS")
GHOST_FOLDER = os.path.join(BASE_FOLDER, "GHOST")
GHOST_ACCOUNTS_FOLDER = os.path.join(GHOST_FOLDER, "ACCOUNTS")
GHOST_RARE_FOLDER = os.path.join(GHOST_FOLDER, "RAREACCOUNT")
GHOST_COUPLES_FOLDER = os.path.join(GHOST_FOLDER, "COUPLESACCOUNT")

for folder in [BASE_FOLDER, TOKENS_FOLDER, ACCOUNTS_FOLDER, RARE_ACCOUNTS_FOLDER,
               COUPLES_ACCOUNTS_FOLDER, GHOST_FOLDER, GHOST_ACCOUNTS_FOLDER,
               GHOST_RARE_FOLDER, GHOST_COUPLES_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# ================================================================
# STATE
# ================================================================
EXIT_FLAG = False
SUCCESS_COUNTER = 0
TARGET_ACCOUNTS = 0
RARE_COUNTER = 0
COUPLES_COUNTER = 0
RARITY_SCORE_THRESHOLD = 3
LOCK = threading.Lock()

running_jobs = {}  # chat_id -> job info
user_sessions = {}  # chat_id -> session data

FILE_LOCKS = {}
def get_file_lock(filename):
    if filename not in FILE_LOCKS:
        FILE_LOCKS[filename] = threading.Lock()
    return FILE_LOCKS[filename]

# ================================================================
# RARITY PATTERNS
# ================================================================
ACCOUNT_RARITY_PATTERNS = {
    "REPEATED_DIGITS_4": [r"(\d)\1{3,}", 3],
    "REPEATED_DIGITS_3": [r"(\d)\1\1(\d)\2\2", 2],
    "SEQUENTIAL_5": [r"(12345|23456|34567|45678|56789)", 4],
    "SEQUENTIAL_4": [r"(0123|1234|2345|3456|4567|5678|6789|9876|8765|7654|6543|5432|4321|3210)", 3],
    "PALINDROME_6": [r"^(\d)(\d)(\d)\3\2\1$", 5],
    "PALINDROME_4": [r"^(\d)(\d)\2\1$", 3],
    "SPECIAL_COMBINATIONS_HIGH": [r"(69|420|1337|007)", 4],
    "SPECIAL_COMBINATIONS_MED": [r"(100|200|300|400|500|666|777|888|999)", 2],
    "QUADRUPLE_DIGITS": [r"(1111|2222|3333|4444|5555|6666|7777|8888|9999|0000)", 4],
    "MIRROR_PATTERN_HIGH": [r"^(\d{2,3})\1$", 3],
    "MIRROR_PATTERN_MED": [r"(\d{2})0\1", 2],
    "GOLDEN_RATIO": [r"1618|0618", 3]
}

POTENTIAL_COUPLES = {}
COUPLES_LOCK = threading.Lock()

# ================================================================
# HÀM XỬ LÝ CHÍNH
# ================================================================
def get_random_name(base_name):
    digits = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
    number = random.randint(1, 999)
    number_str = f"{number:03d}"
    exponent_str = ''.join(digits[d] for d in number_str)
    return f"{base_name[:7]}{exponent_str}"

def generate_custom_password(prefix):
    garena_decoded = base64.b64decode(GARENA).decode('utf-8')
    characters = string.ascii_uppercase + string.digits
    random_part1 = ''.join(random.choice(characters) for _ in range(5))
    random_part2 = ''.join(random.choice(characters) for _ in range(5))
    return f"{prefix}_{random_part1}_{garena_decoded}_{random_part2}"

def EnC_Vr(N):
    if N < 0:
        return b''
    H = []
    while True:
        BesTo = N & 0x7F
        N >>= 7
        if N:
            BesTo |= 0x80
        H.append(BesTo)
        if not N:
            break
    return bytes(H)

def CrEaTe_VarianT(field_number, value):
    field_header = (field_number << 3) | 0
    return EnC_Vr(field_header) + EnC_Vr(value)

def CrEaTe_LenGTh(field_number, value):
    field_header = (field_number << 3) | 2
    encoded_value = value.encode() if isinstance(value, str) else value
    return EnC_Vr(field_header) + EnC_Vr(len(encoded_value)) + encoded_value

def CrEaTe_ProTo(fields):
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, dict):
            nested_packet = CrEaTe_ProTo(value)
            packet.extend(CrEaTe_LenGTh(field, nested_packet))
        elif isinstance(value, int):
            packet.extend(CrEaTe_VarianT(field, value))
        elif isinstance(value, (str, bytes)):
            packet.extend(CrEaTe_LenGTh(field, value))
    return packet

def E_AEs(Pc):
    Z = bytes.fromhex(Pc)
    key_bytes = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    K = AES.new(key_bytes, AES.MODE_CBC, iv)
    R = K.encrypt(pad(Z, AES.block_size))
    return R

def encrypt_api(plain_text):
    plain_text = bytes.fromhex(plain_text)
    key_bytes = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(plain_text, AES.block_size)).hex()

def encode_string(original):
    keystream = [0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37, 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37,
                 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30, 0x31, 0x37, 0x30, 0x30, 0x30, 0x30, 0x30, 0x32, 0x30]
    encoded = ""
    for i in range(len(original)):
        orig_byte = ord(original[i])
        key_byte = keystream[i % len(keystream)]
        encoded += chr(orig_byte ^ key_byte)
    return {"open_id": original, "field_14": encoded}

def to_unicode_escaped(s):
    return ''.join(c if 32 <= ord(c) <= 126 else f'\\u{ord(c):04x}' for c in s)

def decode_jwt_token(jwt_token):
    try:
        parts = jwt_token.split('.')
        if len(parts) >= 2:
            payload_part = parts[1]
            padding = 4 - len(payload_part) % 4
            if padding != 4:
                payload_part += '=' * padding
            decoded = base64.urlsafe_b64decode(payload_part)
            data = json.loads(decoded)
            account_id = data.get('account_id') or data.get('external_id')
            if account_id:
                return str(account_id)
    except:
        pass
    return "N/A"

def smart_delay():
    time.sleep(random.uniform(1, 2))

# ================================================================
# TẠO ACCOUNT
# ================================================================
def create_acc(region, account_name, password_prefix, is_ghost=False):
    if EXIT_FLAG:
        return None
    try:
        password = generate_custom_password(password_prefix)
        data = f"password={password}&client_type=2&source=2&app_id=100067"
        message = data.encode('utf-8')
        signature = hmac.new(key, message, hashlib.sha256).hexdigest()

        url = "https://100067.connect.garena.com/oauth/guest/register"
        headers = {
            "User-Agent": "GarenaMSDK/4.0.19P8(ASUS_Z01QD ;Android 12;en;US;)",
            "Authorization": "Signature " + signature,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive"
        }

        response = requests.post(url, headers=headers, data=data, timeout=30, verify=False)
        response.raise_for_status()

        if 'uid' in response.json():
            uid = response.json()['uid']
            smart_delay()
            return token(uid, password, region, account_name, password_prefix, is_ghost)
        return None
    except Exception as e:
        logger.error(f"create_acc error: {e}")
        smart_delay()
        return None

def token(uid, password, region, account_name, password_prefix, is_ghost=False):
    if EXIT_FLAG:
        return None
    try:
        url = "https://100067.connect.garena.com/oauth/guest/token/grant"
        headers = {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "100067.connect.garena.com",
            "User-Agent": "GarenaMSDK/4.0.19P8(ASUS_Z01QD ;Android 12;en;US;)",
        }
        body = {
            "uid": uid, "password": password,
            "response_type": "token", "client_type": "2",
            "client_secret": key, "client_id": "100067"
        }

        response = requests.post(url, headers=headers, data=body, timeout=30, verify=False)
        response.raise_for_status()

        if 'open_id' in response.json():
            open_id = response.json()['open_id']
            access_token = response.json()["access_token"]

            result = encode_string(open_id)
            field = to_unicode_escaped(result['field_14'])
            field = codecs.decode(field, 'unicode_escape').encode('latin1')
            smart_delay()
            return Major_Regsiter(access_token, open_id, field, uid, password, region, account_name, password_prefix, is_ghost)
        return None
    except Exception as e:
        logger.error(f"token error: {e}")
        smart_delay()
        return None

def Major_Regsiter(access_token, open_id, field, uid, password, region, account_name, password_prefix, is_ghost=False):
    if EXIT_FLAG:
        return None
    try:
        if is_ghost:
            url = "https://loginbp.ggblueshark.com/MajorRegister"
            host = "loginbp.ggblueshark.com"
        else:
            if region.upper() in ["ME", "TH"]:
                url = "https://loginbp.common.ggbluefox.com/MajorRegister"
                host = "loginbp.common.ggbluefox.com"
            else:
                url = "https://loginbp.ggblueshark.com/MajorRegister"
                host = "loginbp.ggblueshark.com"

        name = get_random_name(account_name)

        headers = {
            "Accept-Encoding": "gzip",
            "Authorization": "Bearer",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Expect": "100-continue",
            "Host": host,
            "ReleaseVersion": "OB52",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_I005DA Build/PI)",
            "X-GA": "v1 1",
            "X-Unity-Version": "2018.4."
        }

        lang_code = "pt" if is_ghost else REGION_LANG.get(region.upper(), "en")
        payload = {
            1: name, 2: access_token, 3: open_id,
            5: 102000007, 6: 4, 7: 1,
            13: 1, 14: field, 15: lang_code,
            16: 1, 17: 1
        }

        payload_bytes = CrEaTe_ProTo(payload)
        encrypted_payload = E_AEs(payload_bytes.hex())

        response = requests.post(url, headers=headers, data=encrypted_payload, verify=False, timeout=30)

        if response.status_code == 200:
            login_result = perform_major_login(uid, password, access_token, open_id, region, is_ghost)
            account_id = login_result.get("account_id", "N/A")
            jwt_token = login_result.get("jwt_token", "")

            if not is_ghost and jwt_token and account_id != "N/A" and region.upper() != "BR":
                force_region_binding(region, jwt_token)

            return {
                "uid": uid, "password": password, "name": name,
                "region": "GHOST" if is_ghost else region,
                "status": "success", "account_id": account_id, "jwt_token": jwt_token
            }
        return None
    except Exception as e:
        logger.error(f"Major_Regsiter error: {e}")
        smart_delay()
        return None

def perform_major_login(uid, password, access_token, open_id, region, is_ghost=False):
    try:
        lang = "pt" if is_ghost else REGION_LANG.get(region.upper(), "en")

        payload_parts = [
            b'\x1a\x132025-08-30 05:19:21"\tfree fire(\x01:\x081.114.13B2Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)J\x08HandheldR\nATM MobilsZ\x04WIFI`\xb6\nh\xee\x05r\x03300z\x1fARMv7 VFPv3 NEON VMH | 2400 | 2\x80\x01\xc9\x0f\x8a\x01\x0fAdreno (TM) 640\x92\x01\rOpenGL ES 3.2\x9a\x01+Google|dfa4ab4b-9dc4-454e-8065-e70c733fa53f\xa2\x01\x0e105.235.139.91\xaa\x01\x02',
            lang.encode("ascii"),
            b'\xb2\x01 1d8ec0240ede109973f3321b9354b44d\xba\x01\x014\xc2\x01\x08Handheld\xca\x01\x10Asus ASUS_I005DA\xea\x01@afcfbf13334be42036e4f742c80b956344bed760ac91b3aff9b607a610ab4390\xf0\x01\x01\xca\x02\nATM Mobils\xd2\x02\x04WIFI\xca\x03 7428b253defc164018c604a1ebbfebdf\xe0\x03\xa8\x81\x02\xe8\x03\xf6\xe5\x01\xf0\x03\xaf\x13\xf8\x03\x84\x07\x80\x04\xe7\xf0\x01\x88\x04\xa8\x81\x02\x90\x04\xe7\xf0\x01\x98\x04\xa8\x81\x02\xc8\x04\x01\xd2\x04=/data/app/com.dts.freefireth-PdeDnOilCSFn37p1AH_FLg==/lib/arm\xe0\x04\x01\xea\x04_2087f61c19f57f2af4e7feff0b24d9d9|/data/app/com.dts.freefireth-PdeDnOilCSFn37p1AH_FLg==/base.apk\xf0\x04\x03\xf8\x04\x01\x8a\x05\x0232\x9a\x05\n2019118692\xb2\x05\tOpenGLES2\xb8\x05\xff\x7f\xc0\x05\x04\xe0\x05\xf3F\xea\x05\x07android\xf2\x05pKqsHT5ZLWrYljNb5Vqh//yFRlaPHSO9NWSQsVvOmdhEEn7W+VHNUK+Q+fduA3ptNrGB0Ll0LRz3WW0jOwesLj6aiU7sZ40p8BfUE/FI/jzSTwRe2\xf8\x05\xfb\xe4\x06\x88\x06\x01\x90\x06\x01\x9a\x06\x014\xa2\x06\x014\xb2\x06"GQ@O\x00\x0e^\x00D\x06UA\x0ePM\r\x13hZ\x07T\x06\x0cm\\V\x0ejYV;\x0bU5'
        ]

        payload = b''.join(payload_parts)

        if is_ghost:
            url = "https://loginbp.ggblueshark.com/MajorLogin"
            host = "loginbp.ggblueshark.com"
        elif region.upper() in ["ME", "TH"]:
            url = "https://loginbp.common.ggbluefox.com/MajorLogin"
            host = "loginbp.common.ggbluefox.com"
        else:
            url = "https://loginbp.ggblueshark.com/MajorLogin"
            host = "loginbp.ggblueshark.com"

        headers = {
            "Accept-Encoding": "gzip", "Authorization": "Bearer",
            "Connection": "Keep-Alive", "Content-Type": "application/x-www-form-urlencoded",
            "Expect": "100-continue", "Host": host, "ReleaseVersion": "OB52",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_I005DA Build/PI)",
            "X-GA": "v1 1", "X-Unity-Version": "2018.4.11f1"
        }

        data = payload
        data = data.replace(b'afcfbf13334be42036e4f742c80b956344bed760ac91b3aff9b607a610ab4390', access_token.encode())
        data = data.replace(b'1d8ec0240ede109973f3321b9354b44d', open_id.encode())

        d = encrypt_api(data.hex())
        final_payload = bytes.fromhex(d)

        response = requests.post(url, headers=headers, data=final_payload, verify=False, timeout=30)

        if response.status_code == 200 and len(response.text) > 10:
            jwt_start = response.text.find("eyJ")
            if jwt_start != -1:
                jwt_token = response.text[jwt_start:]
                second_dot = jwt_token.find(".", jwt_token.find(".") + 1)
                if second_dot != -1:
                    jwt_token = jwt_token[:second_dot + 44]
                    account_id = decode_jwt_token(jwt_token)
                    return {"account_id": account_id, "jwt_token": jwt_token}

        return {"account_id": "N/A", "jwt_token": ""}
    except Exception as e:
        logger.error(f"MajorLogin error: {e}")
        return {"account_id": "N/A", "jwt_token": ""}

def force_region_binding(region, jwt_token):
    try:
        if region.upper() in ["ME", "TH"]:
            url = "https://loginbp.common.ggbluefox.com/ChooseRegion"
        else:
            url = "https://loginbp.ggblueshark.com/ChooseRegion"

        region_code = "RU" if region.upper() == "CIS" else region.upper()

        fields = {1: region_code}
        proto_data = CrEaTe_ProTo(fields)
        encrypted_data = encrypt_api(proto_data.hex())
        payload = bytes.fromhex(encrypted_data)

        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 12; M2101K7AG Build/SKQ1.210908.001)",
            'Connection': "Keep-Alive", 'Accept-Encoding': "gzip",
            'Content-Type': "application/x-www-form-urlencoded",
            'Expect': "100-continue", 'Authorization': f"Bearer {jwt_token}",
            'X-Unity-Version': "2018.4.11f1", 'X-GA': "v1 1", 'ReleaseVersion': "OB52"
        }

        response = requests.post(url, data=payload, headers=headers, verify=False, timeout=30)
        return response.status_code == 200
    except:
        return False

# ================================================================
# RARITY & COUPLES
# ================================================================
def check_account_rarity(account_data):
    account_id = account_data.get("account_id", "")
    if account_id == "N/A" or not account_id:
        return False, None, None, 0

    rarity_score = 0
    detected_patterns = []

    for rarity_type, pattern_data in ACCOUNT_RARITY_PATTERNS.items():
        if re.search(pattern_data[0], account_id):
            rarity_score += pattern_data[1]
            detected_patterns.append(rarity_type)

    account_id_digits = [int(d) for d in account_id if d.isdigit()]

    if len(set(account_id_digits)) == 1 and len(account_id_digits) >= 4:
        rarity_score += 5
        detected_patterns.append("UNIFORM_DIGITS")

    if len(account_id_digits) >= 4:
        differences = [account_id_digits[i+1] - account_id_digits[i] for i in range(len(account_id_digits)-1)]
        if len(set(differences)) == 1:
            rarity_score += 4
            detected_patterns.append("ARITHMETIC_SEQUENCE")

    if len(account_id) <= 8 and account_id.isdigit() and int(account_id) < 1000000:
        rarity_score += 3
        detected_patterns.append("LOW_ACCOUNT_ID")

    if rarity_score >= RARITY_SCORE_THRESHOLD:
        reason = f"ID {account_id} - Score: {rarity_score} - Patterns: {', '.join(detected_patterns)}"
        return True, "RARE_ACCOUNT", reason, rarity_score

    return False, None, None, rarity_score

def check_account_couples(account_data, thread_id):
    account_id = account_data.get("account_id", "")
    if account_id == "N/A" or not account_id:
        return False, None, None

    with COUPLES_LOCK:
        for stored_id, stored_data in POTENTIAL_COUPLES.items():
            stored_account_id = stored_data.get('account_id', '')
            couple_found, reason = check_account_couple_patterns(account_id, stored_account_id)
            if couple_found:
                del POTENTIAL_COUPLES[stored_id]
                return True, reason, stored_data

        POTENTIAL_COUPLES[account_id] = {
            'uid': account_data.get('uid', ''),
            'account_id': account_id,
            'name': account_data.get('name', ''),
            'password': account_data.get('password', ''),
            'region': account_data.get('region', ''),
            'thread_id': thread_id,
            'timestamp': datetime.now().isoformat()
        }

    return False, None, None

def check_account_couple_patterns(id1, id2):
    if id1 and id2 and abs(int(id1) - int(id2)) == 1:
        return True, f"Sequential IDs: {id1} & {id2}"
    if id1 == id2[::-1]:
        return True, f"Mirror IDs: {id1} & {id2}"
    if id1 and id2:
        s = int(id1) + int(id2)
        if s % 1000 == 0 or s % 10000 == 0:
            return True, f"Complementary sum: {id1} + {id2} = {s}"
    for love in ['520', '521', '1314', '3344']:
        if love in id1 and love in id2:
            return True, f"Love number: {love}"
    return False, None

# ================================================================
# SAVE FUNCTIONS
# ================================================================
def save_rare_account(account_data, rarity_type, reason, rarity_score, is_ghost=False):
    try:
        if is_ghost:
            fn = os.path.join(GHOST_RARE_FOLDER, "rare-ghost.json")
        else:
            region = account_data.get('region', 'UNKNOWN')
            fn = os.path.join(RARE_ACCOUNTS_FOLDER, f"rare-{region}.json")

        entry = {
            'uid': account_data["uid"], 'password': account_data["password"],
            'account_id': account_data.get("account_id", "N/A"),
            'name': account_data["name"],
            'region': "DEMO" if is_ghost else account_data.get('region', 'UNKNOWN'),
            'rarity_type': rarity_type, 'rarity_score': rarity_score, 'reason': reason,
            'date_identified': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'jwt_token': account_data.get('jwt_token', ''),
            'thread_id': account_data.get('thread_id', 'N/A')
        }

        lock = get_file_lock(fn)
        with lock:
            lst = []
            if os.path.exists(fn):
                try:
                    with open(fn, 'r', encoding='utf-8') as f:
                        lst = json.load(f)
                except:
                    lst = []
            existing = [a.get('account_id') for a in lst]
            if entry['account_id'] not in existing:
                lst.append(entry)
                with open(fn + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(lst, f, indent=2, ensure_ascii=False)
                os.replace(fn + '.tmp', fn)
                return True
        return False
    except:
        return False

def save_couples_account(acc1, acc2, reason, is_ghost=False):
    try:
        if is_ghost:
            fn = os.path.join(GHOST_COUPLES_FOLDER, "couples-ghost.json")
        else:
            region = acc1.get('region', 'UNKNOWN')
            fn = os.path.join(COUPLES_ACCOUNTS_FOLDER, f"couples-{region}.json")

        entry = {
            'couple_id': f"{acc1.get('account_id', 'N/A')}_{acc2.get('account_id', 'N/A')}",
            'account1': {'uid': acc1["uid"], 'password': acc1["password"],
                         'account_id': acc1.get("account_id", "N/A"), 'name': acc1["name"]},
            'account2': {'uid': acc2["uid"], 'password': acc2["password"],
                         'account_id': acc2.get("account_id", "N/A"), 'name': acc2["name"]},
            'reason': reason,
            'region': "DEMO" if is_ghost else acc1.get('region', 'UNKNOWN'),
            'date_matched': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        lock = get_file_lock(fn)
        with lock:
            lst = []
            if os.path.exists(fn):
                try:
                    with open(fn, 'r', encoding='utf-8') as f:
                        lst = json.load(f)
                except:
                    lst = []
            existing = [c.get('couple_id') for c in lst]
            if entry['couple_id'] not in existing:
                lst.append(entry)
                with open(fn + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(lst, f, indent=2, ensure_ascii=False)
                os.replace(fn + '.tmp', fn)
                return True
        return False
    except:
        return False

def save_normal_account(account_data, region, is_ghost=False):
    try:
        if is_ghost:
            fn = os.path.join(GHOST_ACCOUNTS_FOLDER, "ghost.json")
        else:
            fn = os.path.join(ACCOUNTS_FOLDER, f"accounts-{region}.json")

        entry = {
            'uid': account_data["uid"], 'password': account_data["password"],
            'account_id': account_data.get("account_id", "N/A"),
            'name': account_data["name"],
            'region': "DEMO" if is_ghost else region,
            'date_created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'thread_id': account_data.get('thread_id', 'N/A')
        }

        lock = get_file_lock(fn)
        with lock:
            lst = []
            if os.path.exists(fn):
                try:
                    with open(fn, 'r', encoding='utf-8') as f:
                        lst = json.load(f)
                except:
                    lst = []
            existing = [a.get('account_id') for a in lst]
            if entry['account_id'] not in existing:
                lst.append(entry)
                with open(fn + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(lst, f, indent=2, ensure_ascii=False)
                os.replace(fn + '.tmp', fn)
                return True
        return False
    except:
        return False

def save_jwt_token(account_data, jwt_token, region, is_ghost=False):
    try:
        if is_ghost:
            fn = os.path.join(GHOST_FOLDER, "tokens-ghost.json")
        else:
            fn = os.path.join(TOKENS_FOLDER, f"tokens-{region}.json")

        entry = {
            'uid': account_data["uid"],
            'account_id': account_data.get("account_id", "N/A"),
            'jwt_token': jwt_token, 'name': account_data["name"],
            'password': account_data["password"],
            'date_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'region': "DEMO" if is_ghost else region,
            'thread_id': account_data.get('thread_id', 'N/A')
        }

        lock = get_file_lock(fn)
        with lock:
            lst = []
            if os.path.exists(fn):
                try:
                    with open(fn, 'r', encoding='utf-8') as f:
                        lst = json.load(f)
                except:
                    lst = []
            existing = [t.get('account_id') for t in lst]
            if entry['account_id'] not in existing:
                lst.append(entry)
                with open(fn + '.tmp', 'w', encoding='utf-8') as f:
                    json.dump(lst, f, indent=2, ensure_ascii=False)
                os.replace(fn + '.tmp', fn)
                return True
        return False
    except:
        return False

# ================================================================
# ACCOUNT GENERATOR
# ================================================================
def generate_single_account(region, account_name, password_prefix, total, thread_id, chat_id, is_ghost=False):
    global SUCCESS_COUNTER, RARE_COUNTER, COUPLES_COUNTER

    if EXIT_FLAG:
        return None

    with LOCK:
        if SUCCESS_COUNTER >= total:
            return None

    acc = create_acc(region, account_name, password_prefix, is_ghost)
    if not acc:
        return None

    account_id = acc.get("account_id", "N/A")
    jwt_token = acc.get("jwt_token", "")
    acc['thread_id'] = thread_id

    with LOCK:
        SUCCESS_COUNTER += 1
        cur = SUCCESS_COUNTER

    # Kiểm tra rare
    is_rare, rarity_type, rarity_reason, rarity_score = check_account_rarity(acc)
    if is_rare:
        with LOCK:
            RARE_COUNTER += 1
        save_rare_account(acc, rarity_type, rarity_reason, rarity_score, is_ghost)

    # Kiểm tra couples
    is_cp, cp_reason, partner = check_account_couples(acc, thread_id)
    if is_cp and partner:
        with LOCK:
            COUPLES_COUNTER += 1
        save_couples_account(acc, partner, cp_reason, is_ghost)

    # Lưu account
    if is_ghost:
        save_normal_account(acc, "GHOST", True)
        if jwt_token:
            save_jwt_token(acc, jwt_token, "GHOST", True)
    else:
        save_normal_account(acc, region)
        if jwt_token:
            save_jwt_token(acc, jwt_token, region)

    # Gửi thông báo
    try:
        rare_text = f"\n💎 *RARE!* {rarity_type}" if is_rare else ""
        cp_text = f"\n💑 *COUPLES!* {cp_reason}" if is_cp else ""

        msg = f"""
✅ *ACC #{cur}/{total}*
━━━━━━━━━━━━━━━━━━━
👤 Name: `{acc['name']}`
🆔 UID: `{acc['uid']}`
🎮 ID: `{account_id}`
🔑 Pass: `{acc['password']}`
🌍 Region: `{acc.get('region', 'N/A')}`{rare_text}{cp_text}
━━━━━━━━━━━━━━━━━━━
"""
        bot.send_message(chat_id, msg, parse_mode='Markdown')
    except:
        pass

    return acc

def worker(region, account_name, password_prefix, total, thread_id, chat_id, is_ghost=False):
    while not EXIT_FLAG:
        with LOCK:
            if SUCCESS_COUNTER >= total:
                break
        generate_single_account(region, account_name, password_prefix, total, thread_id, chat_id, is_ghost)
        time.sleep(random.uniform(0.5, 1.5))

def run_generator(chat_id, region, account_name, password_prefix, total, threads, is_ghost):
    global SUCCESS_COUNTER, TARGET_ACCOUNTS, RARE_COUNTER, COUPLES_COUNTER, EXIT_FLAG

    SUCCESS_COUNTER = 0
    TARGET_ACCOUNTS = total
    RARE_COUNTER = 0
    COUPLES_COUNTER = 0
    EXIT_FLAG = False

    running_jobs[chat_id] = {"running": True, "total": total}

    bot.send_message(chat_id, f"""
🚀 *BẮT ĐẦU TẠO ACC*
━━━━━━━━━━━━━━━━━━━
🌍 Region: `{region}`
👤 Prefix: `{account_name}`
🔑 Pass Prefix: `{password_prefix}`
🎯 Số lượng: `{total}`
🧵 Threads: `{threads}`
{'👻 Ghost Mode: ON' if is_ghost else ''}
━━━━━━━━━━━━━━━━━━━
⏳ Đang chạy...
""", parse_mode='Markdown')

    threads_list = []
    for i in range(threads):
        t = threading.Thread(target=worker, args=(region, account_name, password_prefix, total, i+1, chat_id, is_ghost))
        t.daemon = True
        t.start()
        threads_list.append(t)

    start_time = time.time()

    while any(t.is_alive() for t in threads_list):
        if not running_jobs.get(chat_id, {}).get("running", False):
            EXIT_FLAG = True
            break
        time.sleep(3)

    EXIT_FLAG = True
    for t in threads_list:
        t.join(timeout=3)

    elapsed = time.time() - start_time

    with LOCK:
        final_success = SUCCESS_COUNTER
        final_rare = RARE_COUNTER
        final_cp = COUPLES_COUNTER

    running_jobs[chat_id] = {"running": False}

    bot.send_message(chat_id, f"""
🎉 *HOÀN THÀNH*
━━━━━━━━━━━━━━━━━━━
📊 Tạo được: `{final_success}/{total}`
💎 Rare: `{final_rare}`
💑 Couples: `{final_cp}`
⏱ Thời gian: `{elapsed:.1f}s`
⚡ Tốc độ: `{final_success/elapsed:.2f} acc/s`
━━━━━━━━━━━━━━━━━━━
""", parse_mode='Markdown')

# ================================================================
# BOT HANDLERS
# ================================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    if message.chat.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Bot này chỉ dành cho admin!")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🌍 Tạo Acc", callback_data='gen'),
        types.InlineKeyboardButton("📊 Xem Acc", callback_data='view'),
    )
    keyboard.add(
        types.InlineKeyboardButton("💎 Rare", callback_data='rare'),
        types.InlineKeyboardButton("💑 Couples", callback_data='couples'),
    )
    keyboard.add(
        types.InlineKeyboardButton("📥 Download", callback_data='download'),
        types.InlineKeyboardButton("⏹ Stop", callback_data='stop'),
    )

    bot.reply_to(message, f"""
🤖 *FF ACC GENERATOR BOT*
━━━━━━━━━━━━━━━━━━━
👑 Admin: `{message.chat.id}`
📌 Chọn chức năng:
━━━━━━━━━━━━━━━━━━━
""", reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    if chat_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Không có quyền!")
        return

    data = call.data
    bot.answer_callback_query(call.id)

    if data == 'gen':
        show_regions(call.message)
    elif data == 'view':
        show_saved_accounts(call.message)
    elif data == 'rare':
        show_rare_accounts(call.message)
    elif data == 'couples':
        show_couples_accounts(call.message)
    elif data == 'download':
        show_download_menu(call.message)
    elif data == 'stop':
        stop_job(call.message)

def show_regions(message):
    chat_id = message.chat.id
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    regions = [r for r in REGION_LANG.keys() if r != "BR"]
    buttons = []
    for r in regions:
        buttons.append(types.InlineKeyboardButton(r, callback_data=f'region_{r}'))
    keyboard.add(*buttons)
    keyboard.add(types.InlineKeyboardButton("👻 GHOST Mode", callback_data='region_GHOST'))
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data='back'))

    bot.edit_message_text(f"""
🌍 *CHỌN REGION*
━━━━━━━━━━━━━━━━━━━
📌 Chọn region để tạo acc:
━━━━━━━━━━━━━━━━━━━
""", chat_id=chat_id, message_id=message.message_id, reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('region_'))
def handle_region(call):
    chat_id = call.message.chat.id
    region = call.data.replace('region_', '')
    is_ghost = (region == 'GHOST')

    user_sessions[chat_id] = {
        'region': 'BR' if is_ghost else region,
        'is_ghost': is_ghost,
        'step': 'count'
    }

    bot.answer_callback_query(call.id)
    msg = bot.send_message(chat_id, f"""
🌍 Region: `{region}`
📌 Nhập *số lượng acc* cần tạo:
""", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_count)

def process_count(message):
    chat_id = message.chat.id
    if chat_id not in user_sessions:
        return

    try:
        count = int(message.text.strip())
        if count < 1 or count > 500:
            raise ValueError()
        user_sessions[chat_id]['count'] = count
        user_sessions[chat_id]['step'] = 'name'

        msg = bot.send_message(chat_id, f"✅ Số lượng: `{count}`\n\n👤 Nhập *prefix tên acc* (VD: Duy):", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_name)
    except:
        msg = bot.send_message(chat_id, "❌ Nhập số từ 1-500:")
        bot.register_next_step_handler(msg, process_count)

def process_name(message):
    chat_id = message.chat.id
    if chat_id not in user_sessions:
        return

    name = message.text.strip()
    if not name or len(name) > 20:
        msg = bot.send_message(chat_id, "❌ Prefix không hợp lệ (1-20 ký tự):")
        bot.register_next_step_handler(msg, process_name)
        return

    user_sessions[chat_id]['name'] = name
    user_sessions[chat_id]['step'] = 'password'

    msg = bot.send_message(chat_id, f"✅ Name prefix: `{name}`\n\n🔑 Nhập *prefix password* (VD: Duy):", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_password)

def process_password(message):
    chat_id = message.chat.id
    if chat_id not in user_sessions:
        return

    pwd = message.text.strip()
    if not pwd or len(pwd) > 20:
        msg = bot.send_message(chat_id, "❌ Prefix không hợp lệ (1-20 ký tự):")
        bot.register_next_step_handler(msg, process_password)
        return

    user_sessions[chat_id]['password'] = pwd
    user_sessions[chat_id]['step'] = 'threads'

    msg = bot.send_message(chat_id, f"✅ Password prefix: `{pwd}`\n\n🧵 Nhập *số threads* (1-5, khuyến nghị 2-3):", parse_mode='Markdown')
    bot.register_next_step_handler(msg, process_threads)

def process_threads(message):
    chat_id = message.chat.id
    if chat_id not in user_sessions:
        return

    try:
        threads = int(message.text.strip())
        if threads < 1 or threads > 5:
            raise ValueError()
    except:
        msg = bot.send_message(chat_id, "❌ Nhập số từ 1-5:")
        bot.register_next_step_handler(msg, process_threads)
        return

    session = user_sessions[chat_id]
    session['threads'] = threads

    # Xác nhận
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Bắt đầu", callback_data='confirm_start'),
        types.InlineKeyboardButton("❌ Hủy", callback_data='back'),
    )

    bot.send_message(chat_id, f"""
📋 *XÁC NHẬN*
━━━━━━━━━━━━━━━━━━━
🌍 Region: `{session['region']}`
👤 Name: `{session['name']}`
🔑 Pass: `{session['password']}`
🎯 Số lượng: `{session['count']}`
🧵 Threads: `{threads}`
{'👻 Ghost Mode' if session['is_ghost'] else ''}
━━━━━━━━━━━━━━━━━━━
""", reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == 'confirm_start')
def handle_confirm(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    if chat_id not in user_sessions:
        return

    if running_jobs.get(chat_id, {}).get("running", False):
        bot.send_message(chat_id, "⚠️ Đang có job chạy! Bấm Stop trước.")
        return

    s = user_sessions[chat_id]

    t = threading.Thread(target=run_generator, args=(
        chat_id, s['region'], s['name'], s['password'],
        s['count'], s['threads'], s['is_ghost']
    ))
    t.daemon = True
    t.start()

    del user_sessions[chat_id]

@bot.callback_query_handler(func=lambda call: call.data == 'back')
def handle_back(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)

    if chat_id in user_sessions:
        del user_sessions[chat_id]

    cmd_start(call.message)

def stop_job(message):
    chat_id = message.chat.id
    global EXIT_FLAG

    if running_jobs.get(chat_id, {}).get("running", False):
        running_jobs[chat_id]["running"] = False
        EXIT_FLAG = True
        bot.send_message(chat_id, "⏹ *Đang dừng job...*", parse_mode='Markdown')
    else:
        bot.send_message(chat_id, "⚠️ Không có job nào đang chạy!")

def show_saved_accounts(message):
    chat_id = message.chat.id
    files = []

    if os.path.exists(ACCOUNTS_FOLDER):
        for f in os.listdir(ACCOUNTS_FOLDER):
            if f.endswith('.json'):
                fp = os.path.join(ACCOUNTS_FOLDER, f)
                try:
                    with open(fp, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        files.append(f"📄 `{f}`: {len(data)} acc")
                except:
                    pass

    ghost_file = os.path.join(GHOST_ACCOUNTS_FOLDER, "ghost.json")
    if os.path.exists(ghost_file):
        try:
            with open(ghost_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                files.append(f"👻 `ghost.json`: {len(data)} acc")
        except:
            pass

    if not files:
        text = "📭 Chưa có account nào!"
    else:
        text = "📊 *DANH SÁCH ACCOUNT*\n━━━━━━━━━━━━━━━━━━━\n" + "\n".join(files)

    bot.send_message(chat_id, text, parse_mode='Markdown')

def show_rare_accounts(message):
    chat_id = message.chat.id
    files = []

    if os.path.exists(RARE_ACCOUNTS_FOLDER):
        for f in os.listdir(RARE_ACCOUNTS_FOLDER):
            if f.endswith('.json'):
                fp = os.path.join(RARE_ACCOUNTS_FOLDER, f)
                try:
                    with open(fp, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        files.append(f"💎 `{f}`: {len(data)} acc")
                except:
                    pass

    if not files:
        text = "📭 Chưa có rare account nào!"
    else:
        text = "💎 *DANH SÁCH RARE ACCOUNT*\n━━━━━━━━━━━━━━━━━━━\n" + "\n".join(files)

    bot.send_message(chat_id, text, parse_mode='Markdown')

def show_couples_accounts(message):
    chat_id = message.chat.id
    files = []

    if os.path.exists(COUPLES_ACCOUNTS_FOLDER):
        for f in os.listdir(COUPLES_ACCOUNTS_FOLDER):
            if f.endswith('.json'):
                fp = os.path.join(COUPLES_ACCOUNTS_FOLDER, f)
                try:
                    with open(fp, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        files.append(f"💑 `{f}`: {len(data)} cặp")
                except:
                    pass

    if not files:
        text = "📭 Chưa có couples account nào!"
    else:
        text = "💑 *DANH SÁCH COUPLES ACCOUNT*\n━━━━━━━━━━━━━━━━━━━\n" + "\n".join(files)

    bot.send_message(chat_id, text, parse_mode='Markdown')

def show_download_menu(message):
    chat_id = message.chat.id
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    buttons = []
    if os.path.exists(ACCOUNTS_FOLDER):
        for f in os.listdir(ACCOUNTS_FOLDER):
            if f.endswith('.json'):
                buttons.append(types.InlineKeyboardButton(f"📄 {f}", callback_data=f'dl_{f}'))

    keyboard.add(*buttons[:10])
    keyboard.add(types.InlineKeyboardButton("⬅️ Back", callback_data='back'))

    bot.send_message(chat_id, "📥 *CHỌN FILE ĐỂ TẢI*\n━━━━━━━━━━━━━━━━━━━", reply_markup=keyboard, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def handle_download(call):
    chat_id = call.message.chat.id
    fname = call.data.replace('dl_', '')
    fp = os.path.join(ACCOUNTS_FOLDER, fname)

    bot.answer_callback_query(call.id)

    if os.path.exists(fp):
        with open(fp, 'rb') as f:
            bot.send_document(chat_id, f)
    else:
        bot.send_message(chat_id, "❌ File không tồn tại!")

# ================================================================
# WEBHOOK
# ================================================================
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "✅ Webhook working!", 200

    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        try:
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return f"❌ Error: {e}", 500
    return '❌ Invalid', 403

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        return f"✅ Webhook set to {WEBHOOK_URL}", 200
    except Exception as e:
        return f"❌ Error: {e}", 500

@app.route('/', methods=['GET'])
def index():
    return "🤖 FF ACC GENERATOR BOT is running!", 200

# ================================================================
# MAIN
# ================================================================
if __name__ == '__main__':
    print(f"🚀 FF ACC Bot đang chạy trên port {PORT}")
    print(f"👑 Admin IDs: {ADMIN_IDS}")
    print(f"🔗 Webhook: {WEBHOOK_URL}")
    app.run(host='0.0.0.0', port=PORT)
