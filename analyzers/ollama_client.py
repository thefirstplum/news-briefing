import requests
import json
import re
from config import Config
import logging

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self):
        self.base_url = Config.OLLAMA_BASE_URL
        self.model = Config.OLLAMA_MODEL
        self.timeout = Config.OLLAMA_TIMEOUT

    def generate(self, prompt, system=None):
        url = f"{self.base_url}/api/generate"
        # Qwen3 Non-Thinking 모드 권장값 (Qwen/Qwen3-32B 모델 카드)
        # 뉴스 분석은 JSON 구조 따라가야 하므로 보수적 파라미터 + 충분한 num_ctx
        payload = {
            'model': self.model,
            'prompt': prompt,
            'stream': False,
            'think': False,
            'options': {
                'temperature': 0.3,
                'num_predict': 2048,
                'num_ctx': 8192,       # 기본 2048이면 시스템 프롬프트 뒷부분이 잘림
                'top_p': 0.8,          # Qwen3 공식 권장
                'top_k': 20,           # Qwen3 공식 권장
                'min_p': 0,            # Qwen3 공식 권장
                'repeat_penalty': 1.1, # Ollama 기본
            },
        }
        if system:
            payload['system'] = system

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json().get('response', '')
        except requests.RequestException as e:
            logger.error(f"Ollama 요청 실패: {e}")
            return None

    def generate_json(self, prompt, system=None):
        raw = self.generate(prompt, system)
        if not raw:
            return None
        try:
            # thinking 태그 제거 (qwen3.5 등)
            raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
            if '```json' in raw:
                raw = raw.split('```json')[1].split('```')[0]
            elif '```' in raw:
                raw = raw.split('```')[1].split('```')[0]
            # JSON 앞뒤에 설명문이 붙어 나오기도 해서 첫 괄호부터 마지막 닫는 괄호까지만 남긴다
            start_obj = raw.find('{')
            start_arr = raw.find('[')
            if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
                end = raw.rfind(']')
                if end != -1:
                    raw = raw[start_arr:end + 1]
            elif start_obj != -1:
                end = raw.rfind('}')
                if end != -1:
                    raw = raw[start_obj:end + 1]
            result = json.loads(raw)
            return self._clean_garbled(result)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"JSON 파싱 실패: {e}")
            return None

    def _clean_garbled(self, obj):
        """깨진 외국어 정리:
        - 2글자 이상 연속 한자(중국어 문장) 제거. 美/韓/日 1글자 약칭은 유지
        - 일본어 가나(히라가나/가타카나)가 포함된 토큰은 통째로 제거
          예: '체ルト넘'(Cheltenham이 깨진 것)은 토큰째 지운다
        """
        if isinstance(obj, str):
            s = re.sub(r'[一-鿿]{2,}[，。、；：]*', '', obj)
            s = re.sub(r'\S*[぀-ゟ゠-ヿ]+\S*', '', s)
            s = re.sub(r'\s{2,}', ' ', s).strip()
            return s
        elif isinstance(obj, dict):
            return {k: self._clean_garbled(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_garbled(item) for item in obj]
        return obj

    def is_available(self):
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False
