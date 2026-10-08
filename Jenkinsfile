// 사내 Windows Multibranch Pipeline용 예시입니다.
// 관리자가 GitHub Branch Source의 PR 탐색과 실제 검사 상태 보고를 설정합니다.
pipeline {
  agent { label 'fir-windows' }
  stages {
    stage('가상환경과 의존성 준비') {
      steps {
        bat 'python -m venv .venv'
        bat '.venv\\Scripts\\python.exe -m pip install -r requirements.txt pyinstaller==6.22.3'
      }
    }
    stage('새 기능과 기존 기능 검사') {
      steps { bat '.venv\\Scripts\\python.exe -m unittest discover -s tests -v' }
    }
    stage('검사한 main에서 EXE 만들기') {
      when { branch 'main' }
      steps {
        powershell './scripts/build-fir-exe.ps1'
        bat '.venv\\Scripts\\python.exe scripts/verify-fir-exe.py'
        archiveArtifacts artifacts: 'docs/downloads/fir-tuner.exe', fingerprint: true
      }
    }
  }
}
