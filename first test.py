import requests
import google.generativeai as genai
import os

# ۱. تنظیمات کلیدهای API
WEATHER_API_KEY = (Openweatherapi-goes-here)
GEMINI_API_KEY = (Gemini_API-goes-here)
city = "Tehran"

# تنظیم کلید هوش مصنوعی جمینی
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.5-flash-lite")

# ۲. دریافت آب‌وهوا از سرویس اول (OpenWeatherMap)
weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=fa"
weather_response = requests.get(weather_url)

if weather_response.status_code == 200:
    weather_data = weather_response.json()
    temp = weather_data['main']['temp']
    desc = weather_data['weather'][0]['description']
    
    print(f"اطلاعات آب‌وهوای دریافتی برای {city}: دما {temp}°C و وضعیت: {desc}\n")
    
    # ۳. ارسال داده‌ها به هوش مصنوعی برای ساخت برنامه سفر
    prompt = f"""
    من می‌خواهم به شهر {city} سفر کنم. وضعیت فعلی آب‌وهوای آنجا به این صورت است:
    - دما: {temp} درجه سانتی‌گراد
    - وضعیت جوی: {desc}
    
    لطفاً با توجه به این شرایط آب‌وهوایی، یک برنامه سفر جذاب و پیشنهادی ۱ روزه (شامل جاهای دیدنی مناسب این هوا و پیشنهاد لباس/تجهیزات) به زبان فارسی برایم بنویس.
    """
    
    ai_response = model.generate_content(prompt)
    
    print("--- برنامه سفر پیشنهادی هوش مصنوعی ---")
    print(ai_response.text)

else:
    print("خطا در دریافت اطلاعات آب‌وهوا. لطفاً مطمئن شوید کلید فعال شده است:", weather_response.status_code)

input("\nبرای خروج کلید Enter را فشار دهید...")