import urllib.request, json, time

api_key = open('c:\\adforge\\nv_api_key.txt', 'r', encoding='utf-8-sig').read().strip()

# 이모지 없는 순수 한국어 테스트 (인코딩 오류 회피)
# 작동 가능성 높은 모델들 + 타임아웃 넉넉하게 40초
candidates = [
    "mistralai/mistral-nemotron",
    "mistralai/mixtral-8x22b-v0.1",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "meta/llama-3.3-70b-instruct",
    "meta/llama-3.1-8b-instruct",
]

test_prompt = """당신은 숏폼 마케팅 전문가입니다.
50대 여성을 위한 무릎 통증 완화 스트레칭 주제로 네이버 클립용 대본 첫 3문장만 한국어로 작성해주세요.
이모지 없이, 자연스러운 구어체로 써주세요."""

results = {}
for model in candidates:
    print(f"\n[테스트] {model}")
    try:
        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": test_prompt}],
            "max_tokens": 300,
            "temperature": 0.7,
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://integrate.api.nvidia.com/v1/chat/completions',
            data=data,
            headers={
                'Authorization': 'Bearer ' + api_key,
                'Content-Type': 'application/json'
            }
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            content = result['choices'][0]['message']['content']
            results[model] = {"status": "OK", "output": content}
            print(f"  성공!")
    except Exception as e:
        results[model] = {"status": "ERROR", "output": str(e)}
        print(f"  오류: {e}")
    time.sleep(1)

# 결과를 파일로 저장 (인코딩 안전하게)
with open('c:\\adforge\\model_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n\n=== 최종 결과 ===")
for model, r in results.items():
    print(f"\n[{r['status']}] {model}")
    if r['status'] == 'OK':
        print(r['output'])
