def ai_generate(provider: str, api_key: str, model: str, brief: str):
    st.session_state.pop("_ai_error", None)
    try:
        if provider == "Anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=model or "claude-sonnet-4-5", max_tokens=1200,
                system=AI_SYSTEM, messages=[{"role": "user", "content": brief}])
            raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        elif provider == "OpenAI":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=[{"role": "system", "content": AI_SYSTEM},
                          {"role": "user", "content": brief}], max_tokens=1200)
            raw = resp.choices[0].message.content
        else:
            return None
        
        # Fixed regex string line
        raw = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("title"):
            return data
    except Exception as exc:
        st.session_state["_ai_error"] = str(exc)
    return None
