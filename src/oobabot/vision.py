import aiohttp

# OpenAI API Key


async def get_image_description(image_base64, vision_api_url, vision_api_key):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {vision_api_key}"
    }

    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe the following image. Be as descriptive as possible, and include any relevant details."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }

    
    async with aiohttp.ClientSession() as session:
        async with session.post(url=vision_api_url, headers=headers, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                if data['choices'] and data['choices'][0]['message']['content']:
                    description = data['choices'][0]['message']['content']
                    return description
                else:
                    return "Description not available."
            else:
                response.raise_for_status()

