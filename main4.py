import string
import io
import requests
import base64
from flask_cors import CORS
from flask import Flask, request, jsonify
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

app = Flask(__name__)
CORS(app)  # Разрешаем все CORS-запросы

def prepare(text):
    translator = str.maketrans('', '', string.punctuation)
    cleaned = text.translate(translator)
    cleaned = cleaned.lower()
    return cleaned

def transcribe_audio(audio_bytes):
    api_url = 'https://tat-asr.api.translate.tatar/listening/'

    # Создаем временный файл в памяти
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = 'recording.wav'

    files = {
        'file': ('recording.wav', audio_file, 'audio/wav')
    }

    try:
        response = requests.post(api_url, headers={'accept': 'application/json'}, files=files)

        if response.status_code == 200:
            json_response = response.json()
            transcribed_text = json_response.get('text', '')
            transcribed_text = prepare(transcribed_text)
            return transcribed_text
        else:
            print(f'Failed to get response. Status code: {response.status_code}')
            return None
    except requests.RequestException as e:
        print(f'Request failed: {e}')
        return None

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
            return audio_data
        else:
            print(f'Failed to get response. Status code: {response.status_code}')
            return None
    except requests.RequestException as e:
        print(f'Request failed: {e}')
        return None

def process_text_to_audio(input_text, speaker):
    words = prepare(input_text).split()
    audio_segments = []
    durations = []
    word_audios = []

    for word in words:
        audio_bytes = get_tts_audio(speaker, word)
        if audio_bytes:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
            audio_segments.append(audio)
            durations.append(len(audio))

            # Сохраняем аудио каждого слова как bytes
            word_audio = io.BytesIO()
            audio.export(word_audio, format="wav")
            word_audios.append(word_audio.getvalue())
        else:
            print(f"Failed to get TTS for word: {word}")
            # Добавляем пустой сегмент в случае ошибки
            empty_audio = AudioSegment.silent(duration=100)
            audio_segments.append(empty_audio)
            durations.append(len(empty_audio))
            word_audios.append(b'')

    # Объединяем все аудио сегменты
    combined = sum(audio_segments)

    combined_bytes = io.BytesIO()
    combined.export(combined_bytes, format="wav")

    return combined_bytes.getvalue(), durations, word_audios

def get_audio_duration(audio_bytes):
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")
    return len(audio)

def duplicate_audio_segment(audio_bytes, start_ms, end_ms):
    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="wav")

        start_ms = max(0, start_ms)
        end_ms = min(end_ms, len(audio))
        duration_ms = 20

        duplicated_segments = []
        for i in range(start_ms, end_ms, duration_ms):
            segment = audio[i:min(i + duration_ms, end_ms)]
            for j in range(2):
                duplicated_segments.append(segment)

        duplicated_audio = sum(duplicated_segments)
        original_before = audio[:start_ms]
        original_after = audio[end_ms:]
        final_audio = original_before + duplicated_audio + original_after

        output = io.BytesIO()
        final_audio.export(output, format="wav")
        return output.getvalue()

    except CouldntDecodeError as e:
        print("Could not decode the audio file:", e)
        return None

def slow_sentence_on_case(case_num_array, word_audios):
    final_audio = AudioSegment.empty()

    for case_num, word_audio in zip(case_num_array, word_audios):
        if not word_audio:
            continue

        duration = get_audio_duration(word_audio)

        if case_num == 0:
            audio = AudioSegment.from_file(io.BytesIO(word_audio), format="wav")
            final_audio += audio
        elif case_num == 1:
            slowed = duplicate_audio_segment(word_audio, 0, duration // 2)
            if slowed:
                final_audio += AudioSegment.from_file(io.BytesIO(slowed), format="wav")
        elif case_num == 2:
            slowed = duplicate_audio_segment(word_audio, duration // 2, duration)
            if slowed:
                final_audio += AudioSegment.from_file(io.BytesIO(slowed), format="wav")
        elif case_num == 3:
            slowed = duplicate_audio_segment(word_audio, 0, duration)
            if slowed:
                final_audio += AudioSegment.from_file(io.BytesIO(slowed), format="wav")

    output = io.BytesIO()
    final_audio.export(output, format="wav")
    return output.getvalue()

def compare(w1, w2):
    if len(w1) != len(w2):
        return 3
    cnt = 0

    for i in range(len(w1)):
        if w1[i] != w2[i]:
            cnt += 1

    if cnt == 0:
        return 0
    elif cnt >= 2:
        return 3

    for i in range(len(w1)):
        if w1[i] != w2[i]:
            place = (i + 1) / len(w1)
            if place <= 0.4:
                return 1
            elif 0.4 < place < 0.6:
                return 3
            elif place >= 0.6:
                return 2

def check_two_texts(s1, s2):
    words1 = s1
    words2 = s2.split()
    res = []
    for i in range(len(words1)):
        if i >= len(words2):
            res.append(3)
        else:
            ans = compare(words1[i], words2[i])
            res.append(ans)
    return res

def main_workflow(original_text, user_audio_bytes, speaker='almaz'):
    # Преобразуем текст в аудио
    combined_audio_bytes, durations, word_audios = process_text_to_audio(original_text, speaker)

    # Транскрибируем аудио пользователя
    user_transcribed_text = transcribe_audio(user_audio_bytes)

    if not user_transcribed_text:
        return "error", None, [], []

    # Сравниваем тексты
    words = original_text.split()
    comparison_results = check_two_texts(words, user_transcribed_text)

    # Определяем общий результат
    ok = "correct" if all(r == 0 for r in comparison_results) else "wrong"

    # Создаем замедленное аудио
    slowed_audio_bytes = slow_sentence_on_case(comparison_results, word_audios)

    return ok, slowed_audio_bytes, words, comparison_results

@app.route('/check_pronunciation', methods=['POST'])
def check_pronunciation():
    if 'audio' not in request.files or 'text' not in request.form:
        return jsonify({'error': 'Missing audio or text'}), 400

    text = request.form['text']
    audio_file = request.files['audio']
    text = prepare(text)
    try:
        # Читаем аудио файл в bytes
        user_audio_bytes = audio_file.read()

        # Проверяем произношение
        result, feedback_audio_bytes, words, accuracy = main_workflow(text, user_audio_bytes, "almaz")

        # Конвертируем аудио в base64 для отправки
        feedback_audio_base64 = base64.b64encode(feedback_audio_bytes).decode('utf-8') if feedback_audio_bytes else None

        return jsonify({
            'result': result,
            'feedback_audio': feedback_audio_base64,
            'words': ' '.join(words),
            'accuracy': accuracy
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, ssl_context=('cert.pem', 'key.pem'))
