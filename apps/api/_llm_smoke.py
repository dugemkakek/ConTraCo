import asyncio, os
from app.services.llm import build_client

async def main():
    c = build_client()
    print("client:", type(c).__name__, "name=", c.name, "model=", c.model,
          "base_url=", getattr(c, "base_url", "n/a"))
    sys_p = "You are a JSON bot. Respond with ONLY a single JSON object matching the schema the user asks for. Do not include prose, code fences, or thinking blocks outside the JSON."
    usr_p = 'Reply with this exact JSON: {"hi":"<5 word greeting>","ok":true}. No prose.'
    try:
        out = await c.chat_json(sys_p, usr_p)
        print("OUT:", repr(out))
    except Exception as e:
        print("ERR:", type(e).__name__, str(e)[:600])

asyncio.run(main())
