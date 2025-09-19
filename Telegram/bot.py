import logging
import asyncio
import uuid
import time
import traceback
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, PreCheckoutQueryHandler
from maps_api import geocode_address, get_route_info
from onde_api import prepare_order, confirm_order, get_order_offer, get_order_update, get_trip_summary
from storage import load_orders, save_orders
from websocket_listener import listen_notifications
from config import TELEGRAM_BOT_TOKEN, PROVIDER_TOKEN, INVOICE_CURRENCY, CURRENCY_SUB_UNITS, ONDE_HOST
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN, FROM, TO, ASK_PHONE, ASK_PAYMENT, CONFIRM = range(6)

USER_TEMP = {}
ORDERS = load_orders()
PENDING_PREPARES = {}

def persist_orders():
    save_orders(ORDERS)

def main_keyboard():
    kb = [
        ["🚕 طلب تكسي", "💰 تقدير كلفة"],
        ["📜 رحلاتي السابقة", "❓ مساعدة"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("السلام! اختر من القائمة الرئيسية:", reply_markup=main_keyboard())
    return MAIN

async def main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "🚕 طلب تكسي":
        kb = ReplyKeyboardMarkup([[KeyboardButton("📍 أرسل موقعي", request_location=True)], ["📝 اكتب العنوان يدويا"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("اختر طريقة تحديد مكان الالتقاط:", reply_markup=kb)
        return FROM
    if text == "💰 تقدير كلفة":
        await update.message.reply_text("باش نقدر الكلفة اكتب البداية ثم الوجهة أو شارك الموقع عبر 'أرسل موقعي'.", reply_markup=ReplyKeyboardRemove())
        return FROM
    if text == "📜 رحلاتي السابقة":
        await show_my_orders(update, context)
        return MAIN
    if text == "❓ مساعدة":
        await show_help(update, context)
        return MAIN
    await update.message.reply_text("استعمل الأزرار في القائمة الرئيسية.", reply_markup=main_keyboard())
    return MAIN

async def from_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    USER_TEMP[chat_id] = {}
    if update.message.location:
        loc = update.message.location
        USER_TEMP[chat_id]['from_coords'] = {'lat': loc.latitude, 'lng': loc.longitude, 'formatted_address': f"Location {loc.latitude},{loc.longitude}"}
    else:
        text = (update.message.text or "").strip()
        if text == "📝 اكتب العنوان يدويا":
            await update.message.reply_text("اكتب عنوان الانطلاق.")
            return FROM
        USER_TEMP[chat_id]['from_raw'] = text
        try:
            ge = geocode_address(text)
            if ge:
                USER_TEMP[chat_id]['from_coords'] = ge
        except Exception:
            pass
    await update.message.reply_text("تمام. الآن حدد الوجهة.", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 أرسل موقعي", request_location=True)], ["📝 اكتب العنوان يدويا"]], resize_keyboard=True, one_time_keyboard=True))
    return TO

async def to_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.location:
        loc = update.message.location
        USER_TEMP[chat_id]['to_coords'] = {'lat': loc.latitude, 'lng': loc.longitude, 'formatted_address': f"Location {loc.latitude},{loc.longitude}"}
    else:
        text = (update.message.text or "").strip()
        USER_TEMP[chat_id]['to_raw'] = text
        try:
            ge = geocode_address(text)
            if ge:
                USER_TEMP[chat_id]['to_coords'] = ge
        except Exception:
            pass
    temp = USER_TEMP.get(chat_id, {})
    if 'from_coords' not in temp or 'to_coords' not in temp:
        await update.message.reply_text("ما قدرناش نحصل على احداثيات البداية أو الوجهة. استعمل زر 'أرسل موقعي' أو اكتب عنوان دقيق.")
        return ConversationHandler.END
    try:
        route = get_route_info((temp['from_coords']['lat'], temp['from_coords']['lng']), (temp['to_coords']['lat'], temp['to_coords']['lng']))
        if route:
            await update.message.reply_text(f"المسافة: {route['distance_text']}, الوقت التقريبي: {route['duration_text']}")
    except Exception:
        pass
    kb = ReplyKeyboardMarkup([[KeyboardButton("مشاركة رقمي", request_contact=True)], ["تجاوز"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("أعطني رقم هاتفك (يمكن تجاوزه):", reply_markup=kb)
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    contact = update.message.contact
    if contact:
        USER_TEMP[chat_id]['phone'] = contact.phone_number
    else:
        txt = (update.message.text or "").strip()
        if txt != "تجاوز":
            USER_TEMP[chat_id]['phone'] = txt
    buttons = [
        [InlineKeyboardButton("نقدًا (CASH)", callback_data="pay_CASH"), InlineKeyboardButton("بطاقة (CARD)", callback_data="pay_CARD")],
        [InlineKeyboardButton("جهاز دفع (TERMINAL)", callback_data="pay_TERMINAL"), InlineKeyboardButton("طرف ثالث (THIRD_PARTY)", callback_data="pay_THIRD_PARTY")],
        [InlineKeyboardButton("محفظة (WALLET)", callback_data="pay_WALLET"), InlineKeyboardButton("تقدير الكلفة فقط", callback_data="fare_estimate")]
    ]
    await update.message.reply_text("اختر وسيلة الدفع أو اطلب تقدير الكلفة:", reply_markup=InlineKeyboardMarkup(buttons))
    return ASK_PAYMENT

async def payment_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    action = query.data
    temp = USER_TEMP.get(chat_id, {})
    if not temp:
        await query.message.reply_text("جلسة منتهية. ابدأ من /start")
        return ConversationHandler.END
    waypoints = [
        {"exactLatLng":{"lat":temp['from_coords']['lat'],"lng":temp['from_coords']['lng']},"placeLatLng":{"lat":temp['from_coords']['lat'],"lng":temp['from_coords']['lng']}},
        {"exactLatLng":{"lat":temp['to_coords']['lat'],"lng":temp['to_coords']['lng']},"placeLatLng":{"lat":temp['to_coords']['lat'],"lng":temp['to_coords']['lng']}}
    ]
    if action == "fare_estimate":
        try:
            prep = prepare_order(waypoints, currency=None, unit_of_length="KILOMETER")
        except Exception as e:
            await query.message.reply_text(f"خطأ في تقدير الكلفة: {e}")
            return ConversationHandler.END
        estimations = prep.get('orderPreparationData',{}).get('allTariffsTripEstimations',[])
        if not estimations:
            await query.message.reply_text("لم يتم الحصول على تقديرات.")
            return ConversationHandler.END
        lines = []
        for e in estimations:
            lines.append(f"- Tarif ID: {e.get('tariffId')} — cost: {e.get('cost')}")
        payload = str(uuid.uuid4())
        PENDING_PREPARES[payload] = {'order_id': prep.get('orderId'), 'confirmation_id': prep.get('confirmationId'), 'estimations': estimations, 'chat_id': chat_id}
        buttons = [[InlineKeyboardButton("اطلب الآن نقدًا", callback_data=f"confirm|CASH|{payload}")]]
        if PROVIDER_TOKEN and INVOICE_CURRENCY:
            buttons[0].append(InlineKeyboardButton("ادفع الآن (CARD)", callback_data=f"pay_now|THIRD_PARTY|{payload}"))
        await query.message.reply_text("تقديرات الكلفة:\n" + "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
        return CONFIRM
    if action.startswith("pay_") or action.startswith("confirm|"):
        parts = action.split("|")
        if parts[0].startswith("confirm"):
            method = parts[1]
            payload = parts[2]
            pending = PENDING_PREPARES.get(payload)
            if not pending:
                await query.message.reply_text("التحضير انتهت صلاحيته. رجاءً اعد المحاولة.")
                return ConversationHandler.END
            order_id = pending['order_id']
            confirmation_id = pending['confirmation_id']
            user = update.effective_user
            client = {"clientId": str(user.id), "name": user.full_name or user.username or "TelegramUser", "phone": temp.get('phone','')}
            try:
                conf = confirm_order(order_id, confirmation_id, client, payment_methods=[method])
            except Exception as e:
                await query.message.reply_text(f"خطأ أثناء تأكيد الطلب: {e}")
                return ConversationHandler.END
            created_order_id = conf.get('orderId') or order_id
            cost = None
            estim = pending.get('estimations',[])
            if estim:
                cost = estim[0].get('cost')
            msg = f"✅ تم تأكيد رحلتك! رقم الطلب: {created_order_id}"
            if cost is not None:
                msg += f"\nالسعر: {cost}"
            await query.message.reply_text(msg)
            ORDERS[created_order_id] = {"chat_id": chat_id, "user_id": user.id, "status": "CREATED", "meta":{"from": temp.get('from_coords'), "to": temp.get('to_coords')}}
            persist_orders()
            try:
                offer = get_order_offer(created_order_id)
                if offer:
                    d = offer.get('driver')
                    eta = offer.get('eta')
                    if d:
                        await query.message.reply_text(f"🚕 تم تعيين سائق: {d.get('name')}، هاتف: {d.get('phone')}\nالمركبة: {offer.get('car',{}).get('model')} - {offer.get('car',{}).get('plateNumber')}")
                    if eta:
                        await query.message.reply_text(f"⏱️ السائق في الطريق، ETA: {eta}")
            except Exception:
                pass
            return ConversationHandler.END
        else:
            method_code = action.replace("pay_","")
            if method_code == "CARD":
                USER_TEMP[chat_id]['payment'] = "CARD"
                try:
                    prep = prepare_order(waypoints, currency=None, unit_of_length="KILOMETER")
                except Exception as e:
                    await query.message.reply_text(f"خطأ أثناء التحضير: {e}")
                    return ConversationHandler.END
                order_id = prep.get('orderId')
                confirmation_id = prep.get('confirmationId')
                payload = str(uuid.uuid4())
                PENDING_PREPARES[payload] = {'order_id': order_id, 'confirmation_id': confirmation_id, 'estimations': prep.get('orderPreparationData',{}).get('allTariffsTripEstimations',[]), 'chat_id': chat_id}
                if not PROVIDER_TOKEN or not INVOICE_CURRENCY:
                    await query.message.reply_text("الدفع الإلكتروني غير متاح الآن. يرجى اختيار وسيلة أخرى.")
                    return ConversationHandler.END
                estim = PENDING_PREPARES[payload]['estimations']
                if not estim:
                    await query.message.reply_text("لم يتم الحصول على تقدير للسعر.")
                    return ConversationHandler.END
                cost = estim[0].get('cost',0)
                amount = int(round(cost * CURRENCY_SUB_UNITS))
                prices = [LabeledPrice("تكلفة الرحلة", amount)]
                payload_invoice = f"onde_pay|{payload}|{order_id}|{confirmation_id}"
                await context.bot.send_invoice(chat_id=chat_id, title="دفع الرحلة", description=f"دفع تكلفة الرحلة ({cost} {INVOICE_CURRENCY})", payload=payload_invoice, provider_token=PROVIDER_TOKEN, currency=INVOICE_CURRENCY, prices=prices)
                return ConversationHandler.END
            else:
                method = method_code
                try:
                    prep = prepare_order(waypoints, currency=None, unit_of_length="KILOMETER")
                except Exception as e:
                    await query.message.reply_text(f"خطأ أثناء التحضير: {e}")
                    return ConversationHandler.END
                order_id = prep.get('orderId')
                confirmation_id = prep.get('confirmationId')
                user = update.effective_user
                client = {"clientId": str(user.id), "name": user.full_name or user.username or "TelegramUser", "phone": temp.get('phone','')}
                try:
                    conf = confirm_order(order_id, confirmation_id, client, payment_methods=[method])
                except Exception as e:
                    await query.message.reply_text(f"خطأ أثناء تأكيد الطلب: {e}")
                    return ConversationHandler.END
                created_order_id = conf.get('orderId') or order_id
                cost = None
                estim = prep.get('orderPreparationData',{}).get('allTariffsTripEstimations',[])
                if estim:
                    cost = estim[0].get('cost')
                msg = f"✅ تم تأكيد رحلتك! رقم الطلب: {created_order_id}"
                if cost is not None:
                    msg += f"\nالسعر: {cost}"
                await query.message.reply_text(msg)
                ORDERS[created_order_id] = {"chat_id": chat_id, "user_id": user.id, "status": "CREATED", "meta":{"from": temp.get('from_coords'), "to": temp.get('to_coords')}}
                persist_orders()
                try:
                    offer = get_order_offer(created_order_id)
                    if offer:
                        d = offer.get('driver')
                        eta = offer.get('eta')
                        if d:
                            await query.message.reply_text(f"🚕 تم تعيين سائق: {d.get('name')}، هاتف: {d.get('phone')}\nالمركبة: {offer.get('car',{}).get('model')} - {offer.get('car',{}).get('plateNumber')}")
                        if eta:
                            await query.message.reply_text(f"⏱️ السائق في الطريق، ETA: {eta}")
                except Exception:
                    pass
                return ConversationHandler.END
    await query.message.reply_text("اختيار غير معروف.")
    return ConversationHandler.END

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    try:
        await query.answer(ok=True)
    except Exception:
        pass

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = update.effective_chat.id
    payload = msg.successful_payment.invoice_payload
    try:
        parts = payload.split("|")
        if parts[0] != "onde_pay":
            await update.message.reply_text("تم الدفع ولكن المعالجة الداخلية مختلفة.")
            return
        pending_key = parts[1]
        order_id = parts[2]
        confirmation_id = parts[3]
        user = update.effective_user
        client = {"clientId": str(user.id), "name": user.full_name or user.username or "TelegramUser", "phone": ""}
        try:
            conf = confirm_order(order_id, confirmation_id, client, payment_methods=["THIRD_PARTY"])
        except Exception as e:
            await update.message.reply_text(f"الدفع تم بنجاح في تلغرام ولكن فشل تأكيد الطلب عند Onde: {e}")
            return
        created_order_id = conf.get('orderId') or order_id
        ORDERS[created_order_id] = {"chat_id": chat_id, "user_id": user.id, "status": "CREATED", "meta": {}}
        persist_orders()
        pending = PENDING_PREPARES.get(pending_key, {})
        cost = None
        if pending:
            estim = pending.get('estimations',[])
            if estim:
                cost = estim[0].get('cost')
        msg_text = f"✅ تم الدفع بنجاح! تم تأكيد رحلتك. رقم الطلب: {created_order_id}"
        if cost is not None:
            msg_text += f"\nالسعر: {cost}"
        await update.message.reply_text(msg_text)
    except Exception:
        traceback.print_exc()
        await update.message.reply_text("حدث خطأ أثناء معالجة الدفع. تواصل مع الدعم.")

async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lines = []
    for oid, v in ORDERS.items():
        if v.get('chat_id') == chat_id:
            status = v.get('status','-')
            from_addr = v.get('meta',{}).get('from',{}).get('formatted_address','')
            to_addr = v.get('meta',{}).get('to',{}).get('formatted_address','')
            lines.append(f"#{oid} — {status}\nمن: {from_addr}\nالى: {to_addr}")
    if not lines:
        await update.message.reply_text("ما عندك حتى طلب حالياً.")
    else:
        await update.message.reply_text("\n\n".join(lines))

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("مساعدة:\n"
        "1) لطلب تكسي: اضغط '🚕 طلب تكسي' ثم اختر 'أرسل موقعي' أو اكتب العنوان.\n"
        "2) يمكنك طلب تقدير الكلفة بدون إنشاء الرحلة.\n"
        "3) للدفع الإلكتروني: استخدم 'ادفع الآن' عند ظهور الفاتورة (البوت يحتاج PROVIDER_TOKEN وINVOICE_CURRENCY).\n"
        "4) بعد الدفع ستصلك رسائل الحالة: تأكيد الطلب، تعيين السائق، ETA، وصل السائق، بدأ الرحلة، انتهت الرحلة.")
    await update.message.reply_text(text)

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def on_ws_message_async(app, data):
    try:
        order_id = data.get("orderId") or data.get("order_id")
        status = data.get("status")
        if not order_id or not status:
            return
        mapping = ORDERS.get(order_id)
        if not mapping:
            return
        chat_id = mapping.get("chat_id")
        text = None
        if status == "SEARCH":
            text = f"🔎 طلب {order_id}: جاري البحث عن سائق..."
        elif status == "ASSIGNED":
            driver = data.get("driver") or data.get("driverId")
            if isinstance(driver, dict):
                dname = driver.get('name') or driver.get('driverId')
                dphone = driver.get('phone','')
                car = data.get('car',{})
                car_info = f"{car.get('model','')} {car.get('plateNumber','')}".strip()
                text = f"🚕 تم تعيين سائق: {dname}\nالهاتف: {dphone}\nالمركبة: {car_info}"
            else:
                text = f"🚕 تم تعيين سائق للطلب {order_id}."
        elif status == "ARRIVED":
            text = f"📍 السائق وصل إلى موقعك (طلب {order_id})."
        elif status == "STARTED":
            text = f"▶️ الرحلة بدأت (طلب {order_id})."
        elif status == "TRANSFERRING":
            text = f"⏱️ السائق في الطريق (طلب {order_id})."
        elif status in ("FINISHED_PAID","FINISHED_UNPAID","PAYMENT"):
            try:
                summary = get_trip_summary(order_id)
                final = summary.get('finalCost')
                currency = summary.get('currency')
                text = f"🏁 الرحلة انتهت. التكلفة النهائية: {final} {currency}"
            except Exception:
                text = f"🏁 الرحلة انتهت (طلب {order_id})."
        elif status.startswith("CANCELLED"):
            text = f"❌ تم إلغاء الطلب {order_id} (سبب: {status})."
        else:
            text = f"تحديث الطلب {order_id}: الحالة -> {status}"
        if text:
            try:
                await app.bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                pass
        mapping['status'] = status
        persist_orders()
    except Exception:
        traceback.print_exc()

def start_ws_background(loop, app):
    async def runner():
        await listen_notifications(lambda d: asyncio.create_task(on_ws_message_async(app, d)))
    loop.create_task(runner())

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_handler)],
            FROM: [MessageHandler((filters.TEXT | filters.LOCATION) & ~filters.COMMAND, from_address)],
            TO: [MessageHandler((filters.TEXT | filters.LOCATION) & ~filters.COMMAND, to_address)],
            ASK_PHONE: [MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_PAYMENT: [CallbackQueryHandler(payment_choice)],
            CONFIRM: [CallbackQueryHandler(payment_choice)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
        allow_reentry=True
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("myorders", show_my_orders))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    loop = asyncio.get_event_loop()
    start_ws_background(loop, app)
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
