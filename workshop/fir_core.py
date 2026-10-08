"""Shared FIR work functions. GUI and MCP both use these functions.

Signed Q coefficients / 2**fractional_bits. The FFT is the FIR impulse
response's frequency response, NOT an audio recording's spectrum.
"""
import cmath
import math
from pathlib import Path


def tuning_preset() -> dict:
    """Educational 127-tap Hamming lowpass, 6 kHz cutoff at 48 kHz.

    Separate from the simple hand-checkable MCP reference fixture.
    """
    count, middle, cutoff = 127, 63, 6000 / 48000
    coefficients = []
    for index in range(count):
        distance = index - middle
        sinc = 2 * cutoff if distance == 0 else math.sin(2 * math.pi * cutoff * distance) / (math.pi * distance)
        window = .54 - .46 * math.cos(2 * math.pi * index / (count - 1))
        coefficients.append(sinc * window)
    total = sum(coefficients)
    q = [round(value / total * 2**30) for value in coefficients]
    return dict(q_coefficients=q[:63], center_q=q[63], word_bits=32,
                fractional_bits=30, sample_rate_hz=48000,
                query_hz=[0, 3000, 12000, 24000],
                coefficient_layout='mirror63_center', fft_size=2048)


def reference() -> dict:
    # Simple 63-value fixture with hand-checkable H(f): shifted cos(2*pi*f/Fs).
    return dict(q_coefficients=[0]*62+[536870912], word_bits=32,
                fractional_bits=30, sample_rate_hz=48000, query_hz=[0,6000,12000,24000],
                coefficient_layout='mirror63_center', center_q=0,
                expected_gain_linear=[1.0,2**-.5,0.0,1.0], fft_size=128,
                units='linear gain and 20*log10(gain) dB; zero gain has null dB',
                scope='63 + center + reversed 63 = 127 FIR taps; one zero is FFT padding, not a FIR tap. Configurable reconstruction assumption, not a confirmed legacy format.')


def _fft(values):
    """Radix-2 FFT of zero-padded impulse response; no 2/N normalization."""
    n = len(values)
    out = [complex(v) for v in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j: out[i], out[j] = out[j], out[i]
    width = 2
    while width <= n:
        root = cmath.exp(-2j * math.pi / width)
        for start in range(0, n, width):
            w = 1
            for k in range(width // 2):
                a = out[start + k]
                b = w * out[start + k + width // 2]
                out[start + k], out[start + k + width // 2] = a + b, a - b
                w *= root
        width *= 2
    return out


def _db(gain):
    return None if gain <= 1e-12 else 20 * math.log10(gain)


def analyze(q_coefficients: list[int], word_bits: int, fractional_bits: int,
            sample_rate_hz: int, query_hz: list[float], coefficient_layout: str='direct',
            center_q: int=0, fft_size: int=2048) -> dict:
    if type(word_bits) is not int or word_bits not in (32, 64):
        raise ValueError('word_bits must be 32 or 64 (coefficient width, not tap count)')
    if type(fractional_bits) is not int or not 0 <= fractional_bits < word_bits:
        raise ValueError('fractional_bits must be 0..word_bits-1')
    if not 1 <= len(q_coefficients) <= 512 or any(type(c) is not int or
            not -(2**(word_bits-1)) <= c < 2**(word_bits-1) for c in q_coefficients):
        raise ValueError('Use 1..512 signed integer coefficients within the selected word width')
    if type(center_q) is not int or not -(2**(word_bits-1)) <= center_q < 2**(word_bits-1):
        raise ValueError('center_q must be a signed integer within the selected word width')
    if coefficient_layout=='mirror63_center':
        if len(q_coefficients)!=63: raise ValueError('mirror63_center requires exactly 63 input coefficients')
        expanded=q_coefficients+[center_q]+q_coefficients[::-1]
    elif coefficient_layout=='mirror64':
        if len(q_coefficients)!=64: raise ValueError('mirror64 requires exactly 64 input coefficients')
        expanded=q_coefficients+q_coefficients[::-1]
    elif coefficient_layout=='direct': expanded=list(q_coefficients)
    else: raise ValueError('coefficient_layout must be mirror63_center, mirror64 or direct')
    if type(fft_size) is not int or fft_size not in (128,256,512,1024,2048,4096,8192) or fft_size<len(expanded):
        raise ValueError('FFT size must be 128..8192 power of two and at least the expanded FIR length; no truncation')
    if type(sample_rate_hz) is not int or not 8000 <= sample_rate_hz <= 192000:
        raise ValueError('sample_rate_hz must be an integer in 8000..192000 Hz')
    if not 1 <= len(query_hz) <= 32 or any(type(f) not in (int,float) or
            not math.isfinite(f) or not 0 <= f <= sample_rate_hz/2 for f in query_hz):
        raise ValueError('Use 1..32 finite frequencies from 0 to sample_rate_hz/2')
    coeffs = [c / 2**fractional_bits for c in expanded]
    spectrum = _fft(coeffs + [0.0] * (fft_size - len(coeffs)))[:fft_size//2+1]
    gains = [abs(v) for v in spectrum]
    rows = []
    for f in query_hz:
        # Exact response at requested frequencies, including off-grid frequencies.
        gain = abs(sum(c * cmath.exp(-2j*math.pi*f*n/sample_rate_hz) for n,c in enumerate(coeffs)))
        if gain <= 1e-12: gain = 0.0
        rows.append(dict(frequency_hz=f, gain_linear=gain, gain_db=_db(gain)))
    return dict(q_coefficients=q_coefficients, word_bits=word_bits, fractional_bits=fractional_bits,
                coefficient_layout=coefficient_layout,center_q=center_q,input_count=len(q_coefficients),
                expanded_q_coefficients=expanded,
                sample_rate_hz=sample_rate_hz, coefficients=coeffs, tap_count=len(coeffs),
                frequencies=rows, fft=dict(size=fft_size, resolution_hz=sample_rate_hz/fft_size,
                    padding_count=fft_size-len(coeffs),
                    frequency_hz=[k*sample_rate_hz/fft_size for k in range(fft_size//2+1)], gain_linear=gains,
                    gain_db=[_db(g) for g in gains]))


def compact(result):
    """Agent gets inputs/units/queried values; GUI retains all FFT bins."""
    return {k:v for k,v in result.items() if k != 'fft'} | {
        'q_coefficients': [str(c) for c in result['q_coefficients']],
        'expanded_q_coefficients': [str(c) for c in result['expanded_q_coefficients']],
        'center_q': str(result['center_q']), 'fft_padding_count': result['fft']['padding_count'],
        'fft_size': result['fft']['size'], 'fft_resolution_hz': result['fft']['resolution_hz'],
        'units': 'gain_linear: ratio; gain_db: dB (null = zero gain)'}


def response_image(result, width=1100, height=620):
    """One renderer for the GUI display and PNG export."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (width,height), '#000000')
    d = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('segoeui.ttf', 16)
        title = ImageFont.truetype('segoeuib.ttf', 22)
    except OSError:
        font = ImageFont.load_default(size=16)
        title = ImageFont.load_default(size=22)
    d.text((32,18), 'FIR Tuner | Frequency response', fill='#f1f3f5', font=title)
    d.text((32,54), f"Input {result['input_count']} -> FIR {result['tap_count']} taps | {result['word_bits']}-bit / 2^{result['fractional_bits']} | FFT {result['fft']['size']} (+{result['fft']['padding_count']} zeros)", fill='#aeb4bf',font=font)
    x0,x1,y0,y1=85,width-45,110,height-95
    d.text((32,85),'Magnitude (dB)',fill='#f1f3f5',font=font)
    dbs=[max(-100.0, -100.0 if v is None else v) for v in result['fft']['gain_db']]
    ceiling=max(6,math.ceil(max(dbs)/6)*6); span=ceiling+100
    for j in range(5):
        y=y0+j*(y1-y0)/4
        x=x0+j*(x1-x0)/4
        d.line((x0,y,x1,y),fill='#242424')
        d.line((x,y0,x,y1),fill='#242424')
        d.text((10,y-8),f'{ceiling-j*span/4:g}',fill='#aeb4bf',font=font)
    d.line((x0,y0,x0,y1,x1,y1),fill='#62666c')
    coords=[(x0+i*(x1-x0)/(len(dbs)-1),y0+(ceiling-v)/span*(y1-y0)) for i,v in enumerate(dbs)]
    d.line(coords,fill='#ffdf00',width=3)
    for j in range(5):
        f=j*result['sample_rate_hz']/8
        d.text((x0+j*(x1-x0)/4,y1+12),f'{f:g}',fill='#aeb4bf',font=font,anchor='mt')
    d.text((width/2,y1+36),'Frequency (Hz)',fill='#f1f3f5',font=font,anchor='mt')
    d.text((32,height-25),f"Fs {result['sample_rate_hz']} Hz | bin {result['fft']['resolution_hz']:g} Hz | display floor -100 dB",fill='#aeb4bf',font=font)
    return image


def save_response_image(result, output_dir, filename='fir-response.png') -> dict:
    if not isinstance(filename,str) or not filename or '/' in filename or '\\' in filename or ':' in filename or Path(filename).suffix.lower() != '.png':
        raise ValueError('filename must be a plain PNG filename, without a path')
    folder=Path(output_dir).resolve(); folder.mkdir(parents=True,exist_ok=True)
    image=response_image(result)
    for i in range(10000):
        path=folder/(filename if i==0 else f'{Path(filename).stem}-{i}.png')
        try:
            with path.open('xb') as stream: image.save(stream,format='PNG')
            return {'path':str(path),'format':'PNG','width':image.width,'height':image.height}
        except FileExistsError: continue
    raise ValueError('Too many existing files with this filename')
