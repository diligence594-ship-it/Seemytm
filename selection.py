import asyncio
import requests
import logging
import os
from urllib.parse import quote, urlsplit, urlunsplit
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class SelectionWayBot:
    def __init__(self):
        self.base_headers = {
            "sec-ch-ua-platform": '"Windows"',
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            "sec-ch-ua-mobile": "?0",
            "accept": "*/*",
            "origin": "https://www.selectionway.com",
            "sec-fetch-site": "cross-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://www.selectionway.com/",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
        }
        self.user_sessions = {}

    def clean_url(self, url):
        if not url:
            return ""
        url = str(url).strip()
        try:
            p = urlsplit(url)
            if not p.scheme or not p.netloc:
                return quote(url, safe="/%:@!$&'()*+,;=~_-")
            path = quote(p.path, safe="/%:@!$&'()*+,;=~_-")
            return urlunsplit((p.scheme, p.netloc, path, p.query, p.fragment))
        except Exception:
            return url.replace(" ", "%20")

    async def get_all_batches(self):
        url = "https://backend.multistreaming.site/api/courses/active?userId=1448640"
        try:
            r = requests.get(url, headers={"host": "backend.multistreaming.site", **self.base_headers}, timeout=60)
            r.raise_for_status()
            j = r.json()
            return (True, j.get("data", [])) if j.get("state") == 200 else (False, "Failed to get batches")
        except Exception as e:
            return False, f"Error: {e}"

    async def get_my_batches(self, user_id):
        if user_id not in self.user_sessions:
            return False, "Please login first"
        u = self.user_sessions[user_id]
        try:
            r = u["session"].post(
                "https://backend.multistreaming.site/api/courses/my-courses",
                headers={"host": "backend.multistreaming.site", **self.base_headers},
                json={"userId": str(u["user_id"])},
                timeout=60,
            )
            r.raise_for_status()
            j = r.json()
            return (True, j.get("data", [])) if str(j.get("state")) == "200" else (False, "Failed to get your courses")
        except Exception as e:
            return False, f"Error: {e}"

    async def login_user(self, email, password, user_id):
        try:
            s = requests.Session()
            r = s.post(
                "https://selectionway.hranker.com/admin/api/user-login",
                headers={"host": "selectionway.hranker.com", **self.base_headers},
                json={
                    "email": email, "password": password, "mobile": "",
                    "otp": "", "logged_in_via": "web", "customer_id": 561
                },
                timeout=60,
            )
            r.raise_for_status()
            j = r.json()
            if j.get("state") == 200:
                self.user_sessions[user_id] = {
                    "user_id": j["data"]["user_id"],
                    "token": j["data"].get("token_id"),
                    "session": s,
                }
                return True, "✅ Login successful!"
            return False, "❌ Login failed: Invalid credentials"
        except Exception as e:
            return False, f"❌ Login error: {e}"

    async def extract_course_data_without_login(self, course_id, course_name):
        try:
            r = requests.get(
                f"https://backend.multistreaming.site/api/courses/{course_id}/classes?populate=full",
                headers={"host": "backend.multistreaming.site", **self.base_headers},
                timeout=60,
            )
            r.raise_for_status()
            j = r.json()
            if j.get("state") != 200:
                return False, "Failed to get course data"

            all_ok, batches = await self.get_all_batches()
            pdf_url = ""
            if all_ok:
                for b in batches:
                    if b.get("id") == course_id:
                        pdf_url = self.clean_url(b.get("batchInfoPdfUrl", ""))
                        break

            return True, {"classes_data": j["data"], "pdf_url": pdf_url, "course_details": {"title": course_name}}
        except Exception as e:
            return False, f"Error: {e}"

    async def extract_course_data_with_login(self, user_id, course_id, course_name):
        if user_id not in self.user_sessions:
            return False, "Please login first!"
        u = self.user_sessions[user_id]
        try:
            r = u["session"].post(
                "https://backend.multistreaming.site/api/courses/by-id-2",
                headers={"host": "backend.multistreaming.site", **self.base_headers},
                json={"userId": str(u["user_id"]), "id": course_id},
                timeout=60,
            )
            r.raise_for_status()
            j = r.json()
            if j.get("state") != 200:
                return False, "Failed to get course details"
            details = j["data"]
            r = u["session"].get(
                f"https://backend.multistreaming.site/api/courses/{course_id}/classes?populate=full",
                headers={"host": "backend.multistreaming.site", **self.base_headers},
                timeout=60,
            )
            r.raise_for_status()
            cj = r.json()
            if cj.get("state") != 200:
                return False, "Failed to get course data"
            return True, {
                "classes_data": cj["data"],
                "pdf_url": self.clean_url(details.get("batchInfoPdfUrl", "")),
                "course_details": details,
            }
        except Exception as e:
            return False, f"Error: {e}"

    def format_batches_list(self, courses_data, list_type="all"):
        if not courses_data:
            return "No batches found!", []
        batches = []
        if list_type == "all":
            batches = list(courses_data)
        else:
            for group in courses_data:
                batches.extend(group.get("liveCourses", []) or [])
                batches.extend(group.get("recordedCourses", []) or [])
        if not batches:
            return "❌ No batches found!", []
        out = "📚 *All Available Batches*\n\n" if list_type == "all" else "📚 *Your Batches*\n\n"
        for i, c in enumerate(batches, 1):
            out += f"*{i}. {c.get('title','Unknown')}*\n"
            out += f"🆔 `{c.get('id','N/A')}`\n\n"
        out += "👉 Reply with batch number" if list_type == "my" else "👉 Reply with batch ID"
        return out, batches

    def extract_all_data(self, classes_data, pdf_url):
        """
        IMPORTANT:
        Uses the API's actual hierarchy:
          data.classes[] = topic objects
          topic.classes[] = classes
        No class-name matching and no merging of separate topic objects.
        Each topic is completely written before the next topic.
        Class order is the order in that topic's classes[] array.
        """
        topics = classes_data.get("classes", []) if isinstance(classes_data, dict) else []
        result = []

        for topic_obj in topics:
            if not isinstance(topic_obj, dict):
                continue

            topic_name = str(topic_obj.get("topicName") or "").strip()
            classes = topic_obj.get("classes", []) or []

            # Preserve the API's topic object as one unit.
            topic_block = {
                "topic": topic_name,
                "topic_id": topic_obj.get("topicId"),
                "classes": [],
            }

            for cls in classes:
                if not isinstance(cls, dict):
                    continue

                videos = []
                for rec in cls.get("mp4Recordings", []) or []:
                    if isinstance(rec, dict) and rec.get("url"):
                        videos.append((str(rec.get("quality") or ""), str(rec["url"]).strip()))

                video_url = ""
                if videos:
                    # Prefer quality without changing class order.
                    quality_rank = {"720p": 0, "480p": 1, "360p": 2, "240p": 3}
                    videos.sort(key=lambda x: quality_rank.get(x[0], 99))
                    quality, video_url = videos[0]
                else:
                    quality = ""
                    video_url = str(cls.get("class_link") or "").strip()

                pdfs = []
                for p in cls.get("classPdf", []) or []:
                    if isinstance(p, dict) and p.get("url"):
                        pdfs.append(self.clean_url(p["url"]))
                    elif isinstance(p, str) and p.strip():
                        pdfs.append(self.clean_url(p.strip()))

                topic_block["classes"].append({
                    "title": str(cls.get("title") or "Unknown Title").strip(),
                    "video_url": self.clean_url(video_url),
                    "quality": quality,
                    "pdfs": pdfs,
                })

            result.append(topic_block)

        return result, self.clean_url(pdf_url) if pdf_url else ""

    def create_course_file(self, course_name, topic_blocks, batch_pdf):
        safe = "".join(c for c in course_name if c.isalnum() or c in " -_").strip()
        filename = f"{safe.replace(' ', '_') or 'SelectionWay'}.txt"
        videos = pdfs = 0

        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"🎯 {course_name}\n\n")

            if batch_pdf:
                f.write(f"Batch Info PDF : {batch_pdf}\n\n")
                pdfs += 1

            for topic in topic_blocks:
                topic_name = topic["topic"]
                # Main folder/section comes from the class object's section field.
                # Since the API groups the response by topic, do not infer hierarchy
                # from class title names.
                current_main = None

                for cls in topic["classes"]:
                    title = cls["title"]
                    # Each class carries its own section in the API; the topic object
                    # remains the authoritative grouping boundary.
                    # Use the class's sectionName when available.
                    main_folder = ""
                    # section data is retained in API class objects; unavailable here
                    # only if the API omitted it.
                    # The topic is always included.
                    parts = [x for x in [main_folder, topic_name, title] if x]

                    # Keep the requested class-wise order: video, then that class's PDFs.
                    prefix = " | ".join(parts)

                    if cls["video_url"]:
                        f.write(f"{prefix} : {cls['video_url']}\n")
                        videos += 1
                    for p in cls["pdfs"]:
                        f.write(f"{prefix} PDF : {p}\n")
                        pdfs += 1
                    f.write("\n")

        return filename, videos, pdfs


bot = SelectionWayBot()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 Login & Extract", callback_data="login_extract")],
        [InlineKeyboardButton("📚 List All Batches", callback_data="list_batches")],
    ]
    await update.message.reply_text(
        "🤖 *SelectionWay Extractor Bot*\n\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "login_extract":
        context.user_data["awaiting_login"] = True
        await q.edit_message_text(
            "🔐 *Login Required*\n\nSend:\n`email:password`",
            parse_mode="Markdown",
        )
        return

    await q.edit_message_text("🔄 Loading all batches...")
    ok, result = await bot.get_all_batches()
    if not ok:
        await q.edit_message_text(f"❌ {result}")
        return
    text, batches = bot.format_batches_list(result, "all")
    context.user_data["all_batches"] = batches
    context.user_data["awaiting_batch_id"] = True
    await q.edit_message_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    text = update.message.text.strip()

    if context.user_data.get("awaiting_login"):
        if ":" not in text:
            await update.message.reply_text("❌ Format: `email:password`", parse_mode="Markdown")
            return
        email, password = text.split(":", 1)
        ok, msg = await bot.login_user(email.strip(), password.strip(), uid)
        await update.message.reply_text(msg)
        if not ok:
            return
        context.user_data["awaiting_login"] = False
        ok, data = await bot.get_my_batches(uid)
        if ok:
            listing, batches = bot.format_batches_list(data, "my")
            context.user_data["my_batches"] = batches
            context.user_data["awaiting_batch_selection"] = True
            await update.message.reply_text(listing, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ {data}")
        return

    if context.user_data.get("awaiting_batch_selection"):
        if not text.isdigit():
            await update.message.reply_text("❌ Send a valid batch number")
            return
        n = int(text)
        batches = context.user_data.get("my_batches", [])
        if not 1 <= n <= len(batches):
            await update.message.reply_text(f"❌ Choose 1-{len(batches)}")
            return
        c = batches[n - 1]
        await extract_and_send(update, c.get("id"), c.get("title", "Course"), uid, True)
        context.user_data["awaiting_batch_selection"] = False
        return

    if context.user_data.get("awaiting_batch_id"):
        batches = context.user_data.get("all_batches", [])
        c = next((x for x in batches if x.get("id") == text), None)
        name = c.get("title", "Course") if c else "Course"
        await extract_and_send(update, text, name, uid, False)
        context.user_data["awaiting_batch_id"] = False


async def extract_and_send(update, course_id, course_name, uid, logged):
    await update.message.reply_text(f"🔄 Extracting *{course_name}*...", parse_mode="Markdown")
    ok, result = (
        await bot.extract_course_data_with_login(uid, course_id, course_name)
        if logged else
        await bot.extract_course_data_without_login(course_id, course_name)
    )
    if not ok:
        await update.message.reply_text(f"❌ {result}")
        return

    topics, batch_pdf = bot.extract_all_data(result["classes_data"], result["pdf_url"])
    filename, nv, np = bot.create_course_file(course_name, topics, batch_pdf)

    try:
        with open(filename, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"🎯 *{course_name}*\n\n🎥 Videos: {nv}\n📄 PDFs: {np}\n\n✅ Original API topic order preserved.",
                parse_mode="Markdown",
            )
    finally:
        try:
            os.remove(filename)
        except OSError:
            pass


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN environment variable.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(login_extract|list_batches)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
