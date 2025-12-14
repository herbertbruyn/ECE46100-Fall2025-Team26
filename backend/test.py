import requests
import os

url = "https://genai.rcac.purdue.edu/api/chat/completions"
api_key = os.getenv('GEN_AI_STUDIO_API_KEY')
print(api_key)
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
body = {
    "model": "llama3.1:latest",
    "messages": [
    {
        "role": "user",
        "content": "What is your name?"
    }
    ],
    "stream": False
}
response = requests.post(url, headers=headers, json=body)
if response.status_code == 200:
    print(response.text)
else:
    raise Exception(f"Error: {response.status_code}, {response.text}")

