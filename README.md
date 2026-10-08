# FIR 팀 협업 실습 · 여기서 시작하세요

이 폴더는 5~8교시에 사용하는 팀 저장소 시작 파일입니다.
기존 FIR 프로그램에 기능을 나누어 추가하고, 검사와 동료 리뷰를 거쳐 사용자에게 전달합니다.

## 1. 폴더에서 Agent 시작하기

압축을 푼 폴더에서 탐색기의 **터미널에서 열기**를 선택합니다.
README.md와 workshop이 보이는 폴더를 작업 루트로 사용합니다.

```powershell
claude
# Codex를 사용하는 경우:
codex
```

Codex의 shared background server 오류가 나면 `codex --no-daemon`으로 시작합니다.

Agent 대화창에 입력합니다.

```text
이 폴더의 README.md, AGENTS.md, TEAM_CONTRACT.md를 읽어줘.
각 문서가 팀 협업에서 어떤 역할을 하는지 쉽게 설명해줘.
프로젝트 가상환경과 의존성을 준비하고 기준 테스트를 실행해줘.
새 기능은 아직 만들지 마.
```

## 2. 어떤 문서를 읽을까?

| 파일 | 쉬운 설명 | 언제 사용할까? |
|---|---|---|
| AGENTS.md | 팀원과 Agent가 함께 지킬 개발 규칙 | 작업 시작 전 |
| CLAUDE.md | Claude에게 공통 규칙을 읽도록 안내 | Claude 작업 시작 전 |
| TEAM_CONTRACT.md | 기능 분담·입력과 출력·완료 기준에 대한 팀 약속 | 기능 Issue를 만들 때 |
| .github/ISSUE_TEMPLATE/feature.md | 누가 무엇을 만들고 검사할지 정하는 양식 | 업무 분담 시 |
| .github/pull_request_template.md | 변경 이유와 실제 검사 결과를 남기는 양식 | PR을 열 때 |
| .github/workflows/pr-gate.yml | 기능·회귀 테스트와 PR 기록을 자동 검사 | PR 검사 시 |
| .github/workflows/release-build.yml | 검사한 main에서 EXE 배포 후보 만들기 | 8교시 빌드 시 |
| USER_GUIDE.md | 사용자가 실행·문의·복구할 때 읽는 안내 | 사용자 인수 전 |
| RELEASE.md | 버전·코드·검사·배포 결과를 추적하는 기록 | 배포 후보를 만들 때 |

이 문서·도구·검사·리뷰의 묶음이 팀 개발 하네스입니다.
문서에 규칙을 쓰는 것과 GitHub에서 merge를 차단하는 설정은 별도로 적용합니다.

## 3. 실행과 검사 명령 이해하기

가상환경을 활성화한 터미널에서 실행하는 예시입니다.

```powershell
python -m unittest discover -s tests -v
python workshop/fir_gui.py
```

새 기능은 팀원이 각자의 branch에서 만들고 PR로 검토합니다.
함께 지킬 기존 동작과 기능별 약속은 TEAM_CONTRACT.md에서 확인합니다.

## 4. 회사 CI 환경 확인하기

제공 Actions 파일은 Enterprise Cloud용입니다. Enterprise Server는
강사가 준비한 사내 Windows runner와 허용 Action을 사용합니다.
runner 이름만 바꾸어 그대로 실행하지 않습니다.

Jenkinsfile은 관리자가 준비한 Windows Multibranch job에서 사용합니다.
Jenkins가 보고한 실제 검사 상태를 GitHub의 필수 검사로 지정해야 합니다.
PR 기록은 리뷰에서 확인하거나 사내 job에 별도 검사 단계를 추가합니다.

