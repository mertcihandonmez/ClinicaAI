import openai

client = openai.OpenAI(
    base_url="http://127.0.0.1:53307/v1",
    api_key="none"
)

response = client.chat.completions.create(
    model="phi-4-mini",
    messages=[
        {"role": "system", "content": "Sen yardimsever bir asistansin."},
        {"role": "user", "content": "Merhaba, sen kimsin?"}
    ],
    stream=True,
)

print("Cevap:")
for chunk in response:
    if chunk.choices and chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()