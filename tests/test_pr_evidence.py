import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('check_pr', Path(__file__).parents[1] / 'scripts/check_pr.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrEvidenceTests(unittest.TestCase):
    def test_complete_evidence(self):
        body = '\n'.join('## ' + h + '\n' + ('Closes #12' if h == '연결한 Issue' else '예시를 실행해 기대 결과와 일치함을 확인했습니다.') for h in module.HEADINGS)
        self.assertEqual(module.validate(body), [])

    def test_empty_or_unfilled_template_fails(self):
        self.assertTrue(module.validate(''))
        template = Path(__file__).parents[1] / '.github/pull_request_template.md'
        self.assertTrue(module.validate(template.read_text(encoding='utf-8')))

    def test_missing_test_evidence_fails(self):
        body = '\n'.join('## ' + h + '\n' + ('Closes #12' if h == '연결한 Issue' else '실행 기록을 첨부했습니다.') for h in module.HEADINGS if h != '테스트 결과')
        self.assertTrue(any('테스트 결과:' in e for e in module.validate(body)))
