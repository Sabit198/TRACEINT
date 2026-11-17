import asyncio
import hashlib
import html
import io
import json
import logging
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, ChatMemberHandler

BOT_TOKEN = "8979718258:AAFvgQIQ8p7MenN5prtZS_-QiOtMbZd2Xdw"
BOT_USERNAME = "TRACEINT_XBot"
WEBHOOK_SECRET = "TRACEINT_SECRET_CHANGE_ME"
API_KEY = "Boss8055"
BASE = "https://raxxosint.onrender.com"
BASE2 = "https://admin.gbssystems.com/gateway/v1"

AUTO_DELETE_SECONDS = 55
MAX_MESSAGE_LEN = 3800
RATE_WINDOW = 60
RATE_LIMIT = 40
DEDUP_TTL = 3
IST = timezone(timedelta(hours=5, minutes=30))

CHANNELS = [
    {"title": "𝐂𝐢𝐩𝐡𝐞𝐫𝐑𝐨𝐨𝐦", "invite": "https://t.me/+6dJwOhS6sl80MWI1", "id": -1003376910382},
    {"title": "𝐃𝐎𝐗𝐈𝐍𝐓", "invite": "https://t.me/+YN4T3cq1NYBkYWFl", "id": -1003666010619},
    {"title": "𝘕𝘌𝘛𝘞𝘖𝘙𝘒", "invite": "https://t.me/+bDpbT3XK3mU4NWFl", "id": -1003917976232},
    {"title": "𝐁𝐋𝐀𝐂𝐊 𝐒𝐘𝐍𝐃𝐈𝐂𝐀𝐓𝐄", "invite": "https://t.me/+zQUNUl1MR6I4OTNl", "id": -1004471443531},
]

PUBLIC_GROUPS = [
    {"title": "𝐇𝐲𝐝𝐫𝐚𝐊𝐫𝐚𝐤𝐞𝐧 chat", "link": "https://t.me/+yr-gops36QA2Mjc9"},
]

ROUTES = {
    "numtoinfo":  (BASE2, "/number.php",  "num",      "Number to Info",              "9093614290",   "phone"),
    "numtoname":  (BASE,  "/num-to-name", "number",   "Number to Name",              "9876643210",   "phone"),
    "numtoupi":   (BASE,  "/num-to-upi",  "phone",    "Number to UPI",               "7065202121",   "phone"),
    "vehicle":    (BASE,  "/vehicle",     "rc",       "Vehicle RC",                  "KA01AB1234",   "rc"),
    "challan":    (BASE2, "/challan.php", "rc",       "Challan Info",                "HR26EV0001",   "rc"),
    "fastag":     (BASE,  "/fastag-info", "vehicle",  "Fastag Info",                 "KA01AB1234",   "rc"),
    "rchtml":     (BASE,  "/rchtml",      "vehicle",  "RC HTML",                     "KL41V3504",    "rc"),
    "rcpdf":      (BASE,  "/rc",          "vehicle",  "RC PDF",                      "KL41V3504",    "rc"),
    "voter":      (BASE,  "/voter-id",    "epic",     "Voter ID",                    "ZJJ2263770",   "text"),
    "pan":        (BASE,  "/pan-info",    "pan",      "PAN Info",                    "AXDPR2606K",   "pan"),
    "aadhar":     (BASE2, "/aadhar.php",  "aadhaar",  "Aadhaar to Info",             "886553666165", "aadhaar"),
    "hpgas":      (BASE2, "/hp.php",      "num",      "HP Gas Info",                 "7074578844",   "phone"),
    "tgusername": (BASE,  "/tg-to-num",   "username", "Telegram Username to Number", "flamex11",     "username"),
    "tguserid":   (BASE,  "/tg-to-num",   "userid",   "Telegram UserID to Number",   "6435989814",   "numeric"),
    "leakosint":  (BASE,  "/leakosint",   "quiry",    "LeakOSINT Search",            "test@example.com", "text"),
}

ALIASES = {
    "number": "numtoinfo", "phone": "numtoinfo", "mobile": "numtoinfo",
    "name": "numtoname", "upi": "numtoupi", "rc": "vehicle", "car": "vehicle",
    "challaninfo": "challan", "fastaginfo": "fastag", "html": "rchtml", "pdf": "rcpdf",
    "voterid": "voter", "epic": "voter", "paninfo": "pan", "aadhaar": "aadhar",
    "aadharinfo": "aadhar", "gas": "hpgas", "tg": "tgusername", "telegram": "tgusername",
    "leak": "leakosint", "search": "leakosint",
}

INVISIBLE_PATTERN = re.compile(r"[\u200B-\u200F\u2028\u2029\u202F\u205F\u2060\uFEFF\u00A0\u2000-\u200A\u3000]")
CONTROL_PATTERN = re.compile(r"[\x00-\x1F\x7F]")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

_dedup_cache = {}
_rate_cache = {}
_member_cache = {}

app = FastAPI()
telegram_app = None


def log_error(context, message):
    logger.error("[%s] %s", context, message)


def is_non_critical_error(desc):
    d = (desc or "").lower()
    ignored = [
        "message can't be deleted", "message to delete not found",
        "not enough rights to send text messages", "not enough rights to send documents",
        "not enough rights", "chat not found", "bot was blocked by the user",
        "user is deactivated", "group chat was upgraded to a supergroup chat",
        "message is not modified", "have no rights to send a message",
        "bot is not a member of the", "forbidden: bot was kicked",
        "message text is empty", "connection timed out", "could not resolve host",
        "failed to connect",
    ]
    return any(n in d for n in ignored)


def normalize_query(v):
    if not isinstance(v, str):
        return ""
    v = INVISIBLE_PATTERN.sub("", v)
    v = CONTROL_PATTERN.sub("", v)
    return v.strip()


def digits_only(value):
    d = re.sub(r"\D", "", value or "")
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d


def compact_alnum(value):
    return re.sub(r"[\s\-]+", "", value or "").upper()


def sanitize_for_api(kind, value):
    if kind in ("phone", "aadhaar", "imei"):
        return digits_only(value)
    if kind in ("pan", "rc"):
        return compact_alnum(value)
    if kind == "username":
        return value if value.startswith("@") else "@" + value
    if kind == "numeric":
        return re.sub(r"\D", "", value or "")
    if kind == "ip":
        return value.strip()
    return normalize_query(value)


def validate_for_api(kind, value):
    if kind == "phone":
        return None if re.fullmatch(r"[6-9]\d{9}", digits_only(value)) else "Invalid phone number. Provide a 10-digit Indian mobile number."
    if kind == "aadhaar":
        return None if re.fullmatch(r"\d{12}", digits_only(value)) else "Invalid Aadhaar number. Provide a 12-digit Aadhaar number."
    if kind == "pan":
        return None if re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", compact_alnum(value)) else "Invalid PAN. Provide a 10-character PAN like ABCDE1234F."
    if kind == "rc":
        return None if re.fullmatch(r"[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}", compact_alnum(value)) else "Invalid RC number. Example: WB26AW3880"
    if kind == "username":
        return None if re.fullmatch(r"@?[A-Za-z0-9_]{4,32}", value) else "Invalid Telegram username. Example: @example_user"
    if kind == "numeric":
        return None if re.fullmatch(r"\d+", value) else "Invalid numeric ID."
    if kind == "ip":
        parts = value.split(".")
        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return None
        return "Invalid IP address. Example: 122.183.39.236"
    if kind == "imei":
        return None if re.fullmatch(r"\d{15}", digits_only(value)) else "Invalid IMEI. Provide a 15-digit IMEI number."
    return None


def fetch_api(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            body = resp.read()
            code = resp.status
            ctype = resp.headers.get("Content-Type", "")
    except Exception as e:
        return {"kind": "json", "data": {"_error": str(e)}}
    if url.endswith(".pdf") or "pdf" in ctype.lower():
        return {"kind": "pdf", "raw": body, "content_type": ctype}
    if "html" in ctype.lower() and b"<" in body[:100]:
        return {"kind": "html", "raw": body, "content_type": ctype}
    if code >= 400:
        return {"kind": "json", "data": {"_error": f"Upstream returned HTTP {code}", "_code": code}}
    if not body:
        return {"kind": "json", "data": {"_error": "Empty response from upstream"}}
    try:
        decoded = json.loads(body.decode("utf-8"))
    except Exception:
        return {"kind": "json", "data": {"_error": "Invalid JSON response from upstream"}}
    if not isinstance(decoded, dict):
        return {"kind": "json", "data": {"_error": "Invalid JSON response from upstream"}}
    return {"kind": "json", "data": decoded}


def strip_developer(obj):
    if isinstance(obj, dict):
        obj.pop("developer", None)
        for v in obj.values():
            strip_developer(v)
    elif isinstance(obj, list):
        for i in obj:
            strip_developer(i)


def friendly_error(res):
    err = (res.get("_error") or "").lower()
    code = int(res.get("_code") or 0)
    if "timed out" in err or "timeout" in err:
        return "The upstream service is currently slow. Please retry in a few seconds."
    if "resolve" in err or "connect" in err:
        return "Unable to reach the upstream service right now. Please retry shortly."
    if code == 429:
        return "Too many requests to the upstream service. Please wait a moment and retry."
    if code >= 500:
        return "The upstream service is temporarily unavailable. Please retry shortly."
    if code >= 400:
        return "The upstream service rejected the request. Please verify the input and retry."
    return "The upstream service did not return a valid response. Please retry shortly."


def esc(v):
    return html.escape(str(v), quote=True)


def is_duplicate(chat_id, user_id, fingerprint):
    key = f"{chat_id}:{user_id}:{fingerprint}"
    now = time.time()
    exp = _dedup_cache.get(key, 0)
    if exp > now:
        return True
    _dedup_cache[key] = now + DEDUP_TTL
    return False


def rate_limited(user_id):
    now = time.time()
    hits = [t for t in _rate_cache.get(user_id, []) if t + RATE_WINDOW > now]
    limited = len(hits) >= RATE_LIMIT
    if not limited:
        hits.append(now)
    _rate_cache[user_id] = hits
    return limited


async def channel_membership(app_, user_id):
    now = time.time()
    cached = _member_cache.get(user_id)
    if cached and cached["expires"] > now:
        return cached["missing"]
    missing = []
    for channel in CHANNELS:
        try:
            member = await app_.bot.get_chat_member(channel["id"], user_id)
            if member.status not in ("creator", "administrator", "member"):
                missing.append(channel)
        except Exception:
            missing.append(channel)
    _member_cache[user_id] = {"expires": now + 300, "missing": missing}
    return missing


def build_join_keyboard(channels):
    rows = [[InlineKeyboardButton(f"Join {c['title']}", url=c["invite"])] for c in channels]
    rows.append([InlineKeyboardButton("VERIFY", callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)


def start_text():
    lines = ["<b>BOT IS WORKING!</b>", "", "<b><u>AVAILABLE COMMANDS</u></b>", ""]
    for cmd, (_, _, _, label, example, _) in ROUTES.items():
        lines.append(f"<b>{label}:</b> /{cmd} {example}")
    return "\n".join(lines)


async def send_auto(app_, chat_id, text, reply_markup=None):
    try:
        msg = await app_.bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML",
            disable_web_page_preview=True, reply_markup=reply_markup
        )
    except Exception as e:
        desc = str(e)
        if not is_non_critical_error(desc):
            log_error("send_auto", desc)
        return None
    asyncio.create_task(_auto_delete(app_, chat_id, msg.message_id, AUTO_DELETE_SECONDS))
    return msg


async def send_document_auto(app_, chat_id, file_bytes, filename, caption):
    try:
        msg = await app_.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(file_bytes), filename=filename),
            caption=caption, parse_mode="HTML"
        )
    except Exception as e:
        desc = str(e)
        if not is_non_critical_error(desc):
            log_error("send_document_auto", desc)
        return None
    asyncio.create_task(_auto_delete(app_, chat_id, msg.message_id, AUTO_DELETE_SECONDS))
    return msg


async def _auto_delete(app_, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await app_.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def error_handler(update, context):
    log_error("handler", str(context.error))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name or "User"
    if update.effective_chat.type == "private":
        missing = await channel_membership(context.application, uid)
        if missing:
            await send_auto(context.application, chat_id,
                f"Welcome {esc(name)}!\n\nTo use this bot, you must join all {len(CHANNELS)} mandatory channels below.\n\nAfter joining, tap VERIFY.",
                build_join_keyboard(missing))
            return
    await send_auto(context.application, chat_id, start_text())


async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    await cb.answer()
    uid = cb.from_user.id
    chat_id = cb.message.chat.id
    try:
        await cb.message.delete()
    except Exception:
        pass
    missing = await channel_membership(context.application, uid)
    if missing:
        await send_auto(context.application, chat_id,
            f"Membership Incomplete\n\nYou must join all {len(CHANNELS)} channels to continue.",
            build_join_keyboard(missing))
        return
    await send_auto(context.application, chat_id, f"<b>Verified!</b>\n\nWelcome to the bot.\n\n{start_text()}")


async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.my_chat_member:
        return
    chat = update.my_chat_member.chat
    status = update.my_chat_member.new_chat_member.status
    if status in ("administrator", "member") and chat.type in ("group", "supergroup"):
        await send_auto(context.application, chat.id, "<b>Bot Activated</b>\n\nBot is now active in this group. Use /start to see commands.")


def resolve_service(text):
    lower = text.strip().lower()
    if lower in ROUTES:
        return lower
    return ALIASES.get(lower)


async def run_query(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id, user_id, first_name, username, service, value_text):
    mention = f"<a href='https://t.me/{esc(username)}'>{esc(first_name)}</a>" if username else f"<a href='tg://user?id={user_id}'>{esc(first_name)}</a>"
    base, path, param, label, example, kind = ROUTES[service]
    value = normalize_query(value_text)
    if not value:
        await send_auto(context.application, chat_id, f"Missing Input\n\nPlease provide a value.\nUsage: <code>/{service} {esc(example)}</code>")
        return
    err = validate_for_api(kind, value)
    if err:
        await send_auto(context.application, chat_id, f"Invalid Input\n\n{esc(err)}")
        return
    api_value = sanitize_for_api(kind, value)
    await send_auto(context.application, chat_id, f"Processing...\n\nFetching {esc(label)} for <code>{esc(api_value)}</code>")
    if base == BASE2:
        url = f"{base}{path}?{param}={urllib.parse.quote(api_value)}"
    else:
        url = f"{base}{path}?key={urllib.parse.quote(API_KEY)}&{param}={urllib.parse.quote(api_value)}"
    result = await asyncio.get_event_loop().run_in_executor(None, fetch_api, url)
    if result["kind"] == "pdf":
        caption = f"<b>{esc(label)}</b>\n<b>Requested by:</b> {mention}\n<b>Query:</b> <code>{esc(api_value)}</code>\n\n<i>Auto-delete in {AUTO_DELETE_SECONDS}s.</i>"
        await send_document_auto(context.application, chat_id, result["raw"], f"{api_value}.pdf", caption)
        return
    if result["kind"] == "html":
        caption = f"<b>{esc(label)}</b>\n<b>Requested by:</b> {mention}\n<b>Query:</b> <code>{esc(api_value)}</code>\n\n<i>Auto-delete in {AUTO_DELETE_SECONDS}s.</i>"
        await send_document_auto(context.application, chat_id, result["raw"], f"{api_value}.html", caption)
        return
    data = result["data"]
    strip_developer(data)
    if "_error" in data:
        response = f"<b>{esc(label)}</b>\n<b>Requested by:</b> {mention}\n<b>Query:</b> <code>{esc(api_value)}</code>\n\n{esc(friendly_error(data))}\n\n<i>Auto-delete in {AUTO_DELETE_SECONDS}s.</i>"
        await send_auto(context.application, chat_id, response)
        return
    formatted = json.dumps(data, indent=4, ensure_ascii=False)
    if len(formatted) > MAX_MESSAGE_LEN:
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", api_value) or "result"
        caption = f"<b>{esc(label)}</b>\n<b>Requested by:</b> {mention}\n<b>Query:</b> <code>{esc(api_value)}</code>\n\n<i>Full result attached. Auto-delete in {AUTO_DELETE_SECONDS}s.</i>"
        ok = await send_document_auto(context.application, chat_id, formatted.encode("utf-8"), f"{safe_name}.json", caption)
        if ok is None:
            await send_auto(context.application, chat_id, "Delivery Failed\n\nCould not upload the result file. Please retry.")
        return
    response = f"<b>{esc(label)}</b>\n<b>Requested by:</b> {mention}\n<b>Query:</b> <code>{esc(api_value)}</code>\n\n<pre>{esc(formatted)}</pre>\n\n<i>Auto-delete in {AUTO_DELETE_SECONDS}s.</i>"
    await send_auto(context.application, chat_id, response)


async def command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    chat_id = message.chat.id
    chat_type = message.chat.type
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    username = message.from_user.username or ""
    raw = normalize_query(message.text)
    try:
        await message.delete()
    except Exception:
        pass
    lower = raw.lower()
    if chat_type == "private":
        if lower.startswith("/start"):
            await start(update, context)
            return
        if lower.startswith("/help") or lower.startswith("/menu"):
            missing = await channel_membership(context.application, user_id)
            if missing:
                await send_auto(context.application, chat_id, f"Access Denied\n\nYou must join all {len(CHANNELS)} channels to use this bot.", build_join_keyboard(missing))
                return
            await send_auto(context.application, chat_id, start_text())
            return
        rows = [[InlineKeyboardButton("Add Me To Your Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")]]
        for g in PUBLIC_GROUPS:
            rows.append([InlineKeyboardButton(g["title"], url=g["link"])])
        for c in CHANNELS:
            rows.append([InlineKeyboardButton(c["title"], url=c["invite"])])
        await send_auto(context.application, chat_id, "<b>Private Access Disabled</b>\n\nThis bot only works in groups. Add me to your group or join one of our public groups below.", InlineKeyboardMarkup(rows))
        return
    if not lower.startswith("/"):
        return
    if lower.startswith("/help") or lower.startswith("/menu"):
        missing = await channel_membership(context.application, user_id)
        if missing:
            await send_auto(context.application, chat_id, f"Access Denied\n\nYou must join all {len(CHANNELS)} channels to use this bot.", build_join_keyboard(missing))
            return
        await send_auto(context.application, chat_id, start_text())
        return
    parts = raw.split(maxsplit=1)
    cmd = parts[0][1:].split("@")[0].lower()
    service = cmd if cmd in ROUTES else None
    if service is None:
        return
    if is_duplicate(chat_id, user_id, hashlib.md5(lower.encode("utf-8")).hexdigest()):
        return
    if rate_limited(user_id):
        return
    missing = await channel_membership(context.application, user_id)
    if missing:
        await send_auto(context.application, chat_id, f"Access Denied\n\nYou must join all {len(CHANNELS)} channels to use this bot.", build_join_keyboard(missing))
        return
    value_text = parts[1] if len(parts) > 1 else ""
    await run_query(update, context, chat_id, user_id, first_name, username, service, value_text)


async def plain_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    message = update.message
    chat_id = message.chat.id
    if message.chat.type == "private":
        return
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    username = message.from_user.username or ""
    raw = normalize_query(message.text)
    if not raw or raw.startswith("/"):
        return
    parts = raw.split(maxsplit=1)
    service = resolve_service(parts[0])
    if service is None:
        return
    try:
        await message.delete()
    except Exception:
        pass
    if is_duplicate(chat_id, user_id, hashlib.md5(raw.lower().encode("utf-8")).hexdigest()):
        return
    if rate_limited(user_id):
        return
    missing = await channel_membership(context.application, user_id)
    if missing:
        await send_auto(context.application, chat_id, f"Access Denied\n\nYou must join all {len(CHANNELS)} channels to use this bot.", build_join_keyboard(missing))
        return
    value_text = parts[1] if len(parts) > 1 else ""
    await run_query(update, context, chat_id, user_id, first_name, username, service, value_text)


@app.on_event("startup")
async def on_startup():
    global telegram_app
    telegram_app = Application.builder().token(BOT_TOKEN).updater(None).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify_join$"))
    telegram_app.add_handler(ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    telegram_app.add_handler(MessageHandler(filters.COMMAND, command_handler))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_handler))
    telegram_app.add_error_handler(error_handler)
    await telegram_app.initialize()
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logger.info("Webhook set to %s", webhook_url)
    await telegram_app.start()


@app.on_event("shutdown")
async def on_shutdown():
    if telegram_app:
        await telegram_app.stop()
        await telegram_app.shutdown()


@app.get("/")
async def root():
    return {"status": "ok", "bot": BOT_USERNAME}


@app.post("/webhook")
async def webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret and secret != WEBHOOK_SECRET:
        return Response(status_code=403)
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
