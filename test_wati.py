import requests

base_url = "https://live.wati.io/10132637"
phone = "9647806140857"
token = "test_token"

url = f"{base_url}/api/v1/sendSessionFile/{phone}"

r2 = requests.get(url, timeout=5)
print(f"Status GET: {r2.status_code}")
print("Response text:", r2.text[:500])
