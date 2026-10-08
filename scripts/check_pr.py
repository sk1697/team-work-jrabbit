"""PR 필수 기록을 확인합니다. 기록의 사실성은 동료 리뷰에서 확인합니다."""
import json
import re
import sys
from pathlib import Path

HEADINGS = ('연결한 Issue', '변경 내용', '완료 기준', '테스트 결과', '기존 동작 유지', '남은 한계')


def validate(body):
    errors = []
    for title in HEADINGS:
        match = re.search(r'^## ' + title + r'\s*\n(.*?)(?=^## |\Z)', body,
                          re.MULTILINE | re.DOTALL)
        content = match.group(1).strip() if match else ''
        if not content or re.search(r'<[^>]+>', content) or content.lower() in ('todo', 'tbd', '미정', '작성 필요'):
            errors.append(f'{title}: 실제 내용과 확인 결과를 작성하세요.')
        if content.startswith(('작성 안내:', 'Describe ', 'List ', 'Record ', 'Explain ')):
            errors.append(f'{title}: 안내 문장을 실제 작업 기록으로 바꾸세요.')
    if not re.search(r'(?im)^\s*closes\s+#\d+\b', body):
        errors.append('연결한 Issue: Closes #번호 형식으로 담당 Issue를 연결하세요.')
    return errors


if __name__ == '__main__':
    event = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    errors = validate(event['pull_request'].get('body') or '')
    for error in errors:
        print(error)
    raise SystemExit(bool(errors))
