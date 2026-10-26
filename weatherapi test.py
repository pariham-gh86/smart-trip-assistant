import requests
import os

# کلید API که از سایت OpenWeatherMap گرفتید را اینجا قرار دهید
API_KEY = (weatherapi-goes-here)
city = "Tehran"

# آدرس درخواست API (با واحد سانتی‌گراد و زبان فارسی برای توصیف هوا)
url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric&lang=fa"

response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    
    # استخراج اطلاعات مهم
    city_name = data['name']
    temp = data['main']['temp']
    weather_desc = data['weather'][0]['description']
    humidity = data['main']['humidity']
    
    print(f"--- اطلاعات آب‌وهوا برای شهر {city_name} ---")
    print(f"دما: {temp} درجه سانتی‌گراد")
    print(f"وضعیت: {weather_desc}")
    print(f"رطوبت هوا: {humidity}%")
else:
    print(f"خطا در دریافت اطلاعات: {response.status_code}")
    print("لطفاً از صحت کلید API و نام شهر اطمینان حاصل کنید.")

os.system("pause")