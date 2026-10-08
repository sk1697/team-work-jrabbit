"""Built-in demonstration adapter. Learners create fir_server.py from GUI/bridge APIs."""
import json
from mcp.server.fastmcp import FastMCP
from fir_bridge import call_gui
from fir_core import reference


def create_server(runtime_path):
    mcp=FastMCP('fir-tuner')

    @mcp.tool()
    def get_fir_state() -> dict:
        """열려 있는 FIR GUI의 입력, 분석 결과와 최근 MCP 호출을 읽습니다."""
        return call_gui(runtime_path,'state')

    @mcp.tool()
    def analyze_fir(q_coefficients: list[str], word_bits: int, fractional_bits: int,
                    sample_rate_hz: int, query_hz: list[float], coefficient_layout: str='mirror63_center',
                    center_q: str='0', fft_size: int=128) -> dict:
        """열린 GUI에 Q 계수를 입력하고 FFT 분석·그래프·표를 갱신합니다.
        signed 32/64-bit 정수의 십진 문자열 1..512개, 소수부 0..word_bits-1,
        샘플링 8000..192000 Hz, 조회 0..Fs/2 Hz. 계수 / 2^소수부.
        32/64는 계수 폭이며 tap 수가 아닙니다. 이득은 linear/dB, 영점의 dB는 null.
        mirror63_center: 정확히 63개+중앙값+역순63개=127 taps (FFT128에서 패딩1).
        mirror64: 64개+역순64개=128 taps. direct: 전체 계수 그대로.
        center_q는 십진 정수 문자열, FFT는 128..8192의 2의 거듭제곱이며 FIR 길이 이상.
        """
        return call_gui(runtime_path,'analyze',dict(q_coefficients=[int(c) for c in q_coefficients],word_bits=word_bits,
            fractional_bits=fractional_bits,sample_rate_hz=sample_rate_hz,query_hz=query_hz,
            coefficient_layout=coefficient_layout,center_q=int(center_q),fft_size=fft_size))

    @mcp.tool()
    def query_fir_frequencies(query_hz: list[float]) -> dict:
        """현재 GUI의 유효한 FIR 분석 결과에서 0..Fs/2 Hz의 이득을 조회하고 표를 갱신합니다."""
        return call_gui(runtime_path,'query',{'query_hz':query_hz})

    @mcp.tool()
    def save_fir_image(filename: str='fir-response.png') -> dict:
        """현재 GUI의 분석 그래프를 실습 폴더 workshop/reports/fir에 PNG로 저장합니다.
        경로 없이 PNG 파일명만 지정합니다. 같은 파일이 있으면 번호를 붙여 원본을 보존합니다.
        """
        return call_gui(runtime_path,'save',{'filename':filename})

    @mcp.resource('fir://reference',mime_type='application/json')
    def fir_reference() -> str:
        """63개 Q30 예제·중앙값·대칭 구성·FFT 패딩·기대 이득을 읽습니다."""
        return json.dumps(reference(),ensure_ascii=False)

    @mcp.prompt()
    def compare_fir() -> str:
        """분석·주파수 확인·이미지 저장 요청 템플릿. 조회 자체는 실행하지 않습니다."""
        return ('fir://reference를 읽고 analyze_fir로 열린 GUI를 갱신해줘. '
                '63개와 중앙0을 mirror63_center로 확장하고 FFT128을 사용해줘. '
                '0/6000/12000/24000 Hz 이득을 1/0.70710678/0/1과 비교하고 save_fir_image로 PNG를 저장해줘. '
                'GUI와 실제 MCP 응답을 확인하고 이득의 단위와 저장 경로를 알려줘.')
    return mcp


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',required=True)
    args=parser.parse_args()
    create_server(args.runtime).run(transport='stdio')

if __name__=='__main__': main()
