import requests
import base64
from flask_cors import CORS
from flask import Flask, request, Response

def get_tts_audio(speaker, text):
    api_url = 'https://tat-tts.api.translate.tatar/listening/'

    params = {
        'speaker': speaker,
        'text': text
    }

    try:
        response = requests.get(api_url, params=params, headers={'accept': 'application/json'})

        if response.status_code == 200:
            json_response = response.json()
            wav_base64 = json_response['wav_base64']
            audio_data = base64.b64decode(wav_base64)
            return audio_data  # Возвращаем байты аудио
        else:
            print(f'Failed to get response. Status code: {response.status_code}')
            return None
    except requests.RequestException as e:
        print(f'Request failed: {e}')
        return None

app = Flask(__name__)
CORS(app)  # Разрешаем все CORS-запросы


@app.route('/synthesize', methods=['POST', 'OPTIONS'])
def synthesize():
    if request.method == 'OPTIONS':
        return Response(status=200)

    try:
        data = request.get_json()
        text = data.get('text', '')

        if not text:
            return {"error": "Text is required"}, 400

        # Ваша TTS функция (должна возвращать bytes)
        wav_data = get_tts_audio("almaz", text)

        return Response(
            wav_data,
            mimetype='audio/wav',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Content-Disposition': 'attachment; filename=speech.wav'
            }
        )
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
