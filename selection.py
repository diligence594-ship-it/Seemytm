import asyncio
import requests
import json
import logging
import os
from urllib.parse import quote, urlsplit, urlunsplit
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Put your bot token in the BOT_TOKEN environment variable.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
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
            "priority": "u=1, i"
        }
        self.user_sessions = {}

    def clean_url(self, url):
        """Encode spaces in URL paths while preserving existing %XX escapes."""
        if not url:
            return ""
        url = str(url).strip()
        try:
            parts = urlsplit(url)
            encoded_path = quote(parts.path, safe="/%:@!$&'()*+,;=~_-%")
            return urlunsplit((parts.scheme, parts.netloc, encoded_path,
                               parts.query, parts.fragment))
        except Exception:
            return url.replace(" ", "%20")

    async def get_all_batches(self):
        courses_url = "https://backend.multistreaming.site/api/courses/active?userId=1448640"
        headers = {"host": "backend.multistreaming.site", **self.base_headers}
        try:
            response = requests.get(courses_url, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            if data.get("state") == 200:
                return True, data.get("data", [])
            return False, "Failed to get batches"
        except Exception as e:
            return False, f"Error: {e}"

    async def get_my_batches(self, user_id):
        if user_id not in self.user_sessions:
            return False, "Please login first"
        user_data = self.user_sessions[user_id]
        url = "https://backend.multistreaming.site/api/courses/my-courses"
        headers = {
            "host": "backend.multistreaming.site",
            "content-length": "20",
            **self.base_headers
        }
        try:
            response = user_data['session'].post(
                url, headers=headers,
                json={"userId": str(user_data['user_id'])}, timeout=60
            )
            response.raise_for_status()
            data = response.json()
            if str(data.get("state")) == "200":
                return True, data.get("data", [])
            return False, "Failed to get your courses"
        except Exception as e:
            return False, f"Error: {e}"

    async def login_user(self, email, password, user_id):
        url = "https://selectionway.hranker.com/admin/api/user-login"
        headers = {
            "host": "selectionway.hranker.com",
            "content-length": "106",
            **self.base_headers
        }
        payload = {
            "email": email,
            "password": password,
            "mobile": "",
            "otp": "",
            "logged_in_via": "web",
            "customer_id": 561
        }
        try:
            session = requests.Session()
            response = session.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if data.get("state") == 200:
                self.user_sessions[user_id] = {
                    "user_id": data["data"]["user_id"],
                    "token": data["data"]["token_id"],
                    "session": session
                }
                return True, "✅ Login successful!"
            return False, "❌ Login failed: Invalid credentials"
        except Exception as e:
            return False, f"❌ Login error: {e}"

    async def extract_course_data_without_login(self, course_id, course_name):
        try:
            url = f"https://backend.multistreaming.site/api/courses/{course_id}/classes?populate=full"
            headers = {"host": "backend.multistreaming.site", **self.base_headers}
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()
            classes_response = response.json()

            # Keep a copy for debugging/verification if needed.
            with open("selectionway_response.json", "w", encoding="utf-8") as f:
                json.dump(classes_response, f, ensure_ascii=False, indent=2)

            if classes_response.get("state") != 200:
                return False, "Failed to get course data"

            ok, batches = await self.get_all_batches()
            pdf_url = ""
            if ok:
                for batch in batches:
                    if str(batch.get("id")) == str(course_id):
                        pdf_url = self.clean_url(batch.get("batchInfoPdfUrl", ""))
                        break

            return True, {
                "classes_data": classes_response["data"],
                "pdf_url": pdf_url,
                "course_details": {"title": course_name}
            }
        except Exception as e:
            return False, f"Error: {e}"

    async def extract_course_data_with_login(self, user_id, course_id, course_name):
        if user_id not in self.user_sessions:
            return False, "Please login first!"
        user_data = self.user_sessions[user_id]
        try:
            course_url = "https://backend.multistreaming.site/api/courses/by-id-2"
            course_headers = {
                "host": "backend.multistreaming.site",
                "content-length": "52",
                **self.base_headers
            }
            response = user_data['session'].post(
                course_url,
                headers=course_headers,
                json={"userId": str(user_data['user_id']), "id": course_id},
                timeout=60
            )
            response.raise_for_status()
            course_response = response.json()
            if course_response.get("state") != 200:
                return False, "Failed to get course details"

            course_details = course_response["data"]
            pdf_url = self.clean_url(course_details.get("batchInfoPdfUrl", ""))

            classes_url = f"https://backend.multistreaming.site/api/courses/{course_id}/classes?populate=full"
            classes_headers = {"host": "backend.multistreaming.site", **self.base_headers}
            response = user_data['session'].get(classes_url, headers=classes_headers, timeout=60)
            response.raise_for_status()
            classes_response = response.json()

            with open("selectionway_response.json", "w", encoding="utf-8") as f:
                json.dump(classes_response, f, ensure_ascii=False, indent=2)

            if classes_response.get("state") == 200:
                return True, {
                    "classes_data": classes_response["data"],
                    "pdf_url": pdf_url,
                    "course_details": course_details
                }
            return False, "Failed to get course data"
        except Exception as e:
            return False, f"Error: {e}"

    def format_batches_list(self, courses_data, list_type="all"):
        if not courses_data:
            return "No batches found!", []
        message = "📚 *All Available Batches*\n\n" if list_type == "all" else "📚 *Your Batches*\n\n"
        batch_list = []
        if list_type == "all":
            batch_list.extend(courses_data)
        else:
            for group in courses_data:
                batch_list.extend(group.get("liveCourses", []))
                batch_list.extend(group.get("recordedCourses", []))
        if not batch_list:
            return "❌ No batches found!", []
        for i, course in enumerate(batch_list, 1):
            title = course.get('title', 'Unknown')
            course_id = course.get('id', 'N/A')
            price = course.get('discountPrice', course.get('price', 'N/A'))
            category = course.get('mainCategory', {}).get('mainCategoryName', 'General')
            course_type = "🔴 LIVE" if course.get('isLive') else "📹 RECORDED"
            message += f"*{i}. {title}*\n"
            message += f"   🆔 `{course_id}`\n"
            message += f"   📁 {category}\n"
            message += f"   💰 ₹{price} | {course_type}\n"
            message += f"   📖 {course.get('short_description', 'No description')}\n\n"
        message += "👉 Reply with batch number to extract (e.g., `1`)" if list_type == "my" else "👉 Reply with *batch ID* to extract"
        return message, batch_list

    def extract_all_data(self, classes_data, pdf_url, course_details):
        """
        Actual Selection Way response structure:
          data.classes[] = topic groups
          topicGroup.topicName = topic/folder
          topicGroup.classes[] = classes
          class.section.sectionName = MAIN FOLDER
          class.topic.topicName = API topic metadata
          class.title = CLASS NAME
          class.mp4Recordings/class_link = VIDEO
          class.classPdf[] = PDFs for that class

        Classes are grouped by section.sectionName so English/Math/etc. never mix.
        Within each section, topic order and class order from the API are retained.
        """
        groups = []
        by_section = {}

        raw_topics = classes_data.get("classes", []) if isinstance(classes_data, dict) else []

        for topic_group in raw_topics:
            if not isinstance(topic_group, dict):
                continue
            wrapper_topic = str(topic_group.get("topicName") or "Unknown Topic").strip()

            for cls in topic_group.get("classes", []) or []:
                if not isinstance(cls, dict):
                    continue

                section_obj = cls.get("section") or {}
                main_folder = str(
                    section_obj.get("sectionName")
                    or cls.get("sectionName")
                    or "Unknown Section"
                ).strip()

                # API's topic wrapper is the actual class-group/topic order.
                topic_name = wrapper_topic
                class_title = str(cls.get("title") or "Unknown Class").strip()

                recordings = cls.get("mp4Recordings") or []
                best_url = ""
                for quality in ("720p", "480p", "360p"):
                    for rec in recordings:
                        if isinstance(rec, dict) and rec.get("quality") == quality and rec.get("url"):
                            best_url = self.clean_url(rec["url"])
                            break
                    if best_url:
                        break
                if not best_url:
                    best_url = self.clean_url(cls.get("class_link", ""))

                pdfs = []
                for pdf in cls.get("classPdf") or []:
                    if isinstance(pdf, dict):
                        purl = pdf.get("url", "")
                    elif isinstance(pdf, str):
                        purl = pdf
                    else:
                        purl = ""
                    if purl:
                        pdfs.append(self.clean_url(purl))

                if not best_url and not pdfs:
                    continue

                if main_folder not in by_section:
                    by_section[main_folder] = {"main_folder": main_folder, "classes": []}
                    groups.append(by_section[main_folder])

                by_section[main_folder]["classes"].append({
                    "topic": topic_name,
                    "class_name": class_title,
                    "video": best_url,
                    "pdfs": pdfs,
                })

        return groups, self.clean_url(pdf_url) if pdf_url else ""

    def create_course_file(self, course_name, groups, batch_pdf):
        clean_name = "".join(c for c in course_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{clean_name.replace(' ', '_')}.txt"
        total_videos = 0
        total_pdfs = 0

        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"🎯 {course_name}\n\n")
            if batch_pdf:
                f.write("📄 BATCH INFO PDF\n")
                f.write(f"Batch Info PDF : {batch_pdf}\n\n")

            for group in groups:
                main_folder = group["main_folder"]
                for item in group["classes"]:
                    prefix = f'{main_folder} | {item["topic"]} | {item["class_name"]}'
                    if item["video"]:
                        f.write(f'{prefix} : {item["video"]}\n')
                        total_videos += 1
                    for pdf in item["pdfs"]:
                        f.write(f'{prefix} PDF : {pdf}\n')
                        total_pdfs += 1

        return filename, total_videos, total_pdfs


bot = SelectionWayBot()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 Login & Extract", callback_data="login_extract")],
        [InlineKeyboardButton("📚 List All Batches", callback_data="list_batches")]
    ]
    await update.message.reply_text(
        "🤖 *SelectionWay Extractor Bot*\n\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "login_extract":
        context.user_data['awaiting_login'] = True
        context.user_data['action_type'] = 'login_extract'
        await query.edit_message_text(
            "🔐 *Login Required*\n\nPlease send your login credentials in this format:\n`email:password`",
            parse_mode='Markdown'
        )
    elif query.data == "list_batches":
        await query.edit_message_text("🔄 Loading all batches...")
        success, result = await bot.get_all_batches()
        if success:
            batches_list, batch_list = bot.format_batches_list(result, "all")
            context.user_data['all_batches'] = batch_list
            context.user_data['awaiting_batch_id'] = True
            context.user_data['action_type'] = 'all_batches'
            await query.edit_message_text(batches_list, parse_mode='Markdown')
        else:
            await query.edit_message_text(f"❌ {result}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text or ""

    if context.user_data.get('awaiting_login'):
        if ":" not in text:
            await update.message.reply_text("❌ Invalid format! Please use: `email:password`", parse_mode='Markdown')
            return
        email, password = text.split(":", 1)
        await update.message.reply_text("🔄 Logging in...")
        success, message = await bot.login_user(email.strip(), password.strip(), user_id)
        if not success:
            await update.message.reply_text(message)
            return
        context.user_data['awaiting_login'] = False
        await update.message.reply_text("🔄 Loading your batches...")
        success, my_batches = await bot.get_my_batches(user_id)
        if success:
            formatted_list, batch_list = bot.format_batches_list(my_batches, "my")
            context.user_data['my_batches'] = batch_list
            context.user_data['awaiting_batch_selection'] = True
            await update.message.reply_text(formatted_list, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"✅ Login successful but {my_batches}")
        return

    if context.user_data.get('awaiting_batch_selection'):
        if not text.isdigit():
            await update.message.reply_text("❌ Please enter a valid number")
            return
        n = int(text)
        batch_list = context.user_data.get('my_batches', [])
        if not 1 <= n <= len(batch_list):
            await update.message.reply_text(f"❌ Please enter a number between 1 and {len(batch_list)}")
            return
        selected = batch_list[n - 1]
        course_id = selected.get('id')
        course_name = selected.get('title', 'Course')
        await update.message.reply_text(f"🔄 Extracting *{course_name}*...", parse_mode='Markdown')
        success, result = await bot.extract_course_data_with_login(user_id, course_id, course_name)
        if success:
            await process_extraction_result(update, course_name, result)
            context.user_data['awaiting_batch_selection'] = False
        else:
            await update.message.reply_text(f"❌ {result}")
        return

    if context.user_data.get('awaiting_batch_id'):
        batch_id = text.strip()
        batch_list = context.user_data.get('all_batches', [])
        course_name = "Unknown Course"
        for batch in batch_list:
            if str(batch.get('id')) == batch_id:
                course_name = batch.get('title', 'Unknown Course')
                break
        await update.message.reply_text(f"🔄 Extracting *{course_name}*...", parse_mode='Markdown')
        success, result = await bot.extract_course_data_without_login(batch_id, course_name)
        if success:
            await process_extraction_result(update, course_name, result)
            context.user_data['awaiting_batch_id'] = False
        else:
            await update.message.reply_text(f"❌ {result}")
        return

    if text.startswith('/'):
        await update.message.reply_text("Please use /start to begin")


async def process_extraction_result(update, course_name, result):
    groups, batch_pdf = bot.extract_all_data(
        result["classes_data"], result["pdf_url"], result["course_details"]
    )
    filename, total_videos, total_pdfs = bot.create_course_file(
        course_name, groups, batch_pdf
    )
    total_pdf_count = total_pdfs + (1 if batch_pdf else 0)
    caption = (
        f"🎯 *{course_name}*\n\n"
        f"📊 *Extraction Complete!*\n"
        f"• 🎥 Total Videos: {total_videos}\n"
        f"• 📄 Total PDFs: {total_pdf_count}\n"
        f"• 📦 File: `{filename}`\n\n"
        f"✅ *Main folder → Topic → Class → PDF order applied!*"
    )
    try:
        with open(filename, "rb") as f:
            await update.message.reply_document(
                document=f, filename=filename, caption=caption, parse_mode='Markdown'
            )
    finally:
        try:
            os.remove(filename)
        except OSError:
            pass


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(login_extract|list_batches)$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
