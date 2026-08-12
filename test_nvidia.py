import os
import urllib.request
import urllib.error
import json

data = json.dumps({
    "model": "nvidia/llama-3.1-nemotron-70b-instruct",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 10
}).encode('utf-8')

req = urllib.request.Request(
    'https://integrate.api.nvidia.com/v1/chat/completions',
    data=data,
    headers={
        'Authorization': 'Bearer ' + os.environ.get('NVIDIA_API_KEY', ''),
        'Content-Type': 'application/json'
    }
)

try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(f"Error {e.code}: {e.read().decode('utf-8')}")
