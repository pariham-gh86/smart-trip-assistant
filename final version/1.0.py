import os
from collections import Counter
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify
import requests
import google.generativeai as genai

app = Flask(__name__)

# کلیدهای API از متغیرهای محیطی خوانده می‌شوند (نه از کاربر)
WEATHER_API_KEY = (weatherapi-goes-here)
GEMINI_API_KEY = (Geminiapi-goes-here)
# اگر مدل در دسترس نبود، بدون تغییر کد می‌توانید با متغیر محیطی GEMINI_MODEL عوضش کنید
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash-lite')

# محدودیت‌های گفتگو (برای جلوگیری از طولانی شدن بیش از حد درخواست‌ها)
MAX_HISTORY_MESSAGES = 40
MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_CHARS = 60000

WEEKDAYS_FA = ['دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه', 'یکشنبه']


@app.route('/')
def home():
    return render_template('index.html')


def build_daily_forecast(forecast_data, days):
    """
    پیش‌بینی ۳ ساعته‌ی OpenWeatherMap را به خلاصه‌ی روزانه تبدیل می‌کند:
    کمترین/بیشترین دما، وضعیت جوی غالب، احتمال بارش، مقدار باران/برف، باد و رطوبت.
    """
    tz_offset = forecast_data.get('city', {}).get('timezone', 0)
    grouped = {}

    for item in forecast_data.get('list', []):
        local_dt = datetime.fromtimestamp(item['dt'], tz=timezone.utc) + timedelta(seconds=tz_offset)
        day = local_dt.date()
        g = grouped.setdefault(day, {
            'temps': [], 'feels': [], 'descs': [], 'pops': [],
            'winds': [], 'humidity': [], 'rain': 0.0, 'snow': 0.0,
        })
        g['temps'].append(item['main']['temp'])
        g['feels'].append(item['main']['feels_like'])
        g['humidity'].append(item['main']['humidity'])
        g['descs'].append(item['weather'][0]['description'])
        g['pops'].append(item.get('pop', 0))
        g['winds'].append(item.get('wind', {}).get('speed', 0))
        g['rain'] += item.get('rain', {}).get('3h', 0)
        g['snow'] += item.get('snow', {}).get('3h', 0)

    result = []
    for day in sorted(grouped)[:days]:
        g = grouped[day]
        result.append({
            'date': day.isoformat(),
            'weekday': WEEKDAYS_FA[day.weekday()],
            'temp_min': round(min(g['temps']), 1),
            'temp_max': round(max(g['temps']), 1),
            'feels_min': round(min(g['feels']), 1),
            'feels_max': round(max(g['feels']), 1),
            'desc': Counter(g['descs']).most_common(1)[0][0],
            'rain_chance': round(max(g['pops']) * 100),
            'rain_mm': round(g['rain'], 1),
            'snow_mm': round(g['snow'], 1),
            'wind_max': round(max(g['winds']), 1),
            'humidity': round(sum(g['humidity']) / len(g['humidity'])),
        })
    return result


def forecast_to_text(forecast):
    lines = []
    for i, d in enumerate(forecast, start=1):
        line = (
            f"- روز {i} ({d['weekday']} {d['date']}): "
            f"دما بین {d['temp_min']} تا {d['temp_max']} درجه سانتی‌گراد "
            f"(دمای حس‌شده {d['feels_min']} تا {d['feels_max']})، "
            f"وضعیت جوی: {d['desc']}، "
            f"احتمال بارش: {d['rain_chance']}٪"
        )
        if d['rain_mm'] > 0:
            line += f"، میزان باران: حدود {d['rain_mm']} میلی‌متر"
        if d['snow_mm'] > 0:
            line += f"، میزان برف: حدود {d['snow_mm']} میلی‌متر"
        line += f"، حداکثر سرعت باد: {d['wind_max']} متر بر ثانیه، رطوبت: {d['humidity']}٪"
        lines.append(line)
    return "\n".join(lines)


@app.route('/get_plan', methods=['POST'])
def get_plan():
    data = request.json or {}
    city = (data.get('city') or '').strip()
    weather_key = WEATHER_API_KEY
    gemini_key = GEMINI_API_KEY
    user_description = (data.get('description') or '').strip()  # اختیاری

    # تعداد روزها (پیش‌فرض ۱ روز، حداکثر ۱۴ روز)
    try:
        days = int(data.get('days', 1))
    except (TypeError, ValueError):
        return jsonify({'error': 'تعداد روزها باید یک عدد معتبر باشد.'}), 400

    if days < 1 or days > 14:
        return jsonify({'error': 'تعداد روزها باید بین ۱ تا ۱۴ باشد.'}), 400

    # تعداد نفرات (پیش‌فرض ۱ نفر، حداکثر ۲۰ نفر)
    try:
        raw_people = data.get('people')
        people = 1 if raw_people in (None, '') else int(raw_people)
    except (TypeError, ValueError):
        return jsonify({'error': 'تعداد نفرات باید یک عدد معتبر باشد.'}), 400

    if people < 1 or people > 20:
        return jsonify({'error': 'تعداد نفرات باید بین ۱ تا ۲۰ باشد.'}), 400

    if not weather_key or not gemini_key:
        return jsonify({'error': 'کلیدهای API روی سرور تنظیم نشده‌اند (WEATHER_API_KEY و GEMINI_API_KEY).'}), 500

    if not city:
        return jsonify({'error': 'لطفاً نام شهر را وارد کنید.'}), 400

    # ۱. دریافت پیش‌بینی آب‌وهوا (پلن رایگان OpenWeatherMap تا ۵ روز آینده)
    try:
        response = requests.get(
            'https://api.openweathermap.org/data/2.5/forecast',
            params={'q': city, 'appid': weather_key, 'units': 'metric', 'lang': 'fa'},
            timeout=15,
        )
    except requests.RequestException:
        return jsonify({'error': 'ارتباط با سرویس آب‌وهوا برقرار نشد. اینترنت را بررسی کنید.'}), 502

    if response.status_code == 401:
        return jsonify({'error': 'کلید OpenWeatherMap نامعتبر است (یا هنوز فعال نشده).'}), 400
    if response.status_code == 404:
        return jsonify({'error': 'شهر پیدا نشد. نام شهر را به انگلیسی و درست وارد کنید.'}), 400
    if response.status_code != 200:
        return jsonify({'error': 'خطا در دریافت اطلاعات آب‌وهوا.'}), 400

    forecast = build_daily_forecast(response.json(), days)
    if not forecast:
        return jsonify({'error': 'پیش‌بینی آب‌وهوا برای این شهر در دسترس نیست.'}), 400

    available_days = len(forecast)
    missing_days = days - available_days

    # برای سازگاری با صفحه‌ی فعلی: دما و وضعیت اولین روز
    temp = round((forecast[0]['temp_min'] + forecast[0]['temp_max']) / 2, 1)
    desc = forecast[0]['desc']

    weather_text = forecast_to_text(forecast)

    # اگر پیش‌بینی برای همه‌ی روزها موجود نباشد
    missing_text = ""
    forecast_note = ""
    if missing_days > 0:
        first_missing = available_days + 1
        missing_text = (
            f"\nبرای روزهای {first_missing} تا {days} پیش‌بینی دقیق در دسترس نیست. "
            f"برای این روزها بر اساس آب‌وهوای معمول این شهر در همین فصل و روند روزهای قبل، "
            f"یک حدس منطقی بزن و صریحاً بنویس که این بخش تخمینی است.\n"
        )
        forecast_note = (
            f'پیش‌بینی دقیق فقط برای {available_days} روز اول موجود است؛ '
            f'روزهای بعد توسط هوش مصنوعی تخمین زده شده‌اند.'
        )

    # ۲. ارسال به Gemini
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(GEMINI_MODEL)

        if people == 1:
            people_text = "من تنها سفر می‌کنم (۱ نفر)."
        else:
            people_text = f"تعداد مسافران: {people} نفر هستیم."

        prompt = f"""
        من می‌خواهم {days} روز به شهر {city} سفر کنم. {people_text}
        پیش‌بینی آب‌وهوای روزهای سفر به این صورت است:

{weather_text}
{missing_text}
        لطفاً به زبان فارسی و دقیقاً بر اساس همین وضعیت آب‌وهوا موارد زیر را بنویس:

        ۱. یک برنامه سفر جذاب {days} روزه که با آب‌وهوای هر روز هماهنگ باشد
           (مثلاً در روز بارانی یا برفی بیشتر مکان‌های سرپوشیده مثل موزه، کافه و بازار، و در روز آفتابی گردش در فضای باز).
           برنامه را روز به روز و با عنوان «روز ۱»، «روز ۲» و ... جدا کن و برای هر روز صبح، ظهر و عصر/شب را مشخص کن.

        ۲. برای هر روز، بخش جداگانه‌ای به نام «لباس و وسایل مورد نیاز» بنویس و بر اساس دما، بارش، باد و آفتاب همان روز
           لباس و وسایل مناسب را پیشنهاد بده (مثل چتر، بارانی، کلاه، دستکش، عینک آفتابی، کرم ضدآفتاب، کفش ضدآب یا راحت و ...).

        ۳. در پایان، یک فهرست کلی از وسایلی که باید برای کل سفر با خودم ببرم بنویس.

        ۴. پیشنهادها (رفت‌وآمد، رستوران، اقامت، فعالیت‌ها و رزرو) را با تعداد مسافران ({people} نفر) هماهنگ کن
           و در صورت لزوم نکته‌ی عملی بنویس (مثلاً نیاز به رزرو قبلی، خودروی بزرگ‌تر یا چند اتاق).
        """

        # اگر کاربر توضیحات اضافی نوشته باشد، به پرامپت اضافه می‌شود
        if user_description:
            prompt += f"""
        توضیحات و درخواست‌های اضافه من (لطفاً حتماً در برنامه رعایت کن):
        {user_description}
        """

        ai_response = model.generate_content(prompt)
        ai_plan = ai_response.text

        return jsonify({
            'city': city,
            'temp': temp,
            'desc': desc,
            'days': days,
            'people': people,
            'forecast': forecast,
            'forecast_note': forecast_note,
            'plan': ai_plan,
            # Gemini حافظه ندارد؛ برای ادامه‌ی گفتگو کل تاریخچه باید هر بار دوباره فرستاده شود
            'history': [
                {'role': 'user', 'text': prompt.strip()},
                {'role': 'model', 'text': ai_plan},
            ],
        })

    except Exception as e:
        return jsonify({'error': f'خطا در ارتباط با هوش مصنوعی: {str(e)}'}), 500


@app.route('/chat')
def chat_page():
    return render_template('chat.html')


@app.route('/send_message', methods=['POST'])
def send_message():
    """
    ادامه‌ی گفتگو: تاریخچه‌ی قبلی + پیام جدید کاربر را به Gemini می‌فرستد.
    خود API هیچ حافظه‌ای ندارد، پس کل گفتگو هر بار در درخواست ارسال می‌شود.
    """
    data = request.json or {}
    message = (data.get('message') or '').strip()
    history = data.get('history')

    if not GEMINI_API_KEY:
        return jsonify({'error': 'کلید GEMINI_API_KEY روی سرور تنظیم نشده است.'}), 500

    if not message:
        return jsonify({'error': 'پیام خالی است.'}), 400

    if len(message) > MAX_MESSAGE_CHARS:
        return jsonify({'error': f'پیام خیلی طولانی است (حداکثر {MAX_MESSAGE_CHARS} کاراکتر).'}), 400

    if not isinstance(history, list) or not history:
        return jsonify({'error': 'تاریخچه‌ی گفتگو نامعتبر است. یک برنامه‌ی جدید بسازید.'}), 400

    if len(history) >= MAX_HISTORY_MESSAGES:
        return jsonify({'error': 'گفتگو خیلی طولانی شده است. لطفاً یک برنامه‌ی جدید بسازید.'}), 400

    contents = []
    total_chars = 0
    for i, item in enumerate(history):
        role = item.get('role') if isinstance(item, dict) else None
        text = item.get('text') if isinstance(item, dict) else None

        # نقش‌ها باید به ترتیب user, model, user, model, ... باشند
        expected_role = 'user' if i % 2 == 0 else 'model'
        if role != expected_role or not isinstance(text, str) or not text.strip():
            return jsonify({'error': 'تاریخچه‌ی گفتگو نامعتبر است. یک برنامه‌ی جدید بسازید.'}), 400

        total_chars += len(text)
        contents.append({'role': role, 'parts': [text]})

    # آخرین پیام تاریخچه باید جواب مدل باشد تا نوبت کاربر شود
    if len(contents) % 2 != 0:
        return jsonify({'error': 'تاریخچه‌ی گفتگو نامعتبر است. یک برنامه‌ی جدید بسازید.'}), 400

    if total_chars > MAX_HISTORY_CHARS:
        return jsonify({'error': 'گفتگو خیلی طولانی شده است. لطفاً یک برنامه‌ی جدید بسازید.'}), 400

    contents.append({'role': 'user', 'parts': [message]})

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        ai_response = model.generate_content(contents)
        return jsonify({'reply': ai_response.text})

    except Exception as e:
        return jsonify({'error': f'خطا در ارتباط با هوش مصنوعی: {str(e)}'}), 500


if __name__ == '__main__':
    # host='0.0.0.0' باعث می‌شود از طریق شبکه Wi-Fi و روی گوشی قابل دسترسی باشد
    app.run(host='0.0.0.0', port=5000, debug=True)
