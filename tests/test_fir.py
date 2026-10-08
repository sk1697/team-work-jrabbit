import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workshop'))
import fir_core as core


class FirTests(unittest.TestCase):
    def test_startup_preset_is_a_nontrivial_lowpass_with_unity_dc(self):
        preset = core.tuning_preset()
        self.assertEqual(len(preset['q_coefficients']), 63)
        self.assertGreater(len(set(preset['q_coefficients'])), 20)
        result = core.analyze(**preset)
        self.assertEqual(result['tap_count'], 127)
        self.assertAlmostEqual(result['frequencies'][0]['gain_linear'], 1, places=6)
        self.assertGreater(result['frequencies'][1]['gain_linear'], .95)
        self.assertLess(result['frequencies'][2]['gain_linear'], .01)
        self.assertEqual(result['fft']['size'], 2048)

    def test_63_half_expands_to_127_taps_and_only_fft_is_padded(self):
        half=[0]*62+[536870912]
        result=core.analyze(half,32,30,48000,[0,6000,12000,24000],
            coefficient_layout='mirror63_center',center_q=0,fft_size=128)
        self.assertEqual(result['input_count'],63)
        self.assertEqual(result['tap_count'],127)
        self.assertEqual(result['expanded_q_coefficients'],half+[0]+half[::-1])
        self.assertEqual(result['fft']['padding_count'],1)
        self.assertEqual(len(result['fft']['gain_linear']),65)
        for row,gain in zip(result['frequencies'],[1,2**-.5,0,1]):
            self.assertAlmostEqual(row['gain_linear'],gain,places=9)
        # 128-point FFT's 12 kHz bin must agree with the analytic notch.
        self.assertAlmostEqual(result['fft']['gain_linear'][32],0,places=10)

    def test_center_coefficient_and_64_half_layout_are_distinct(self):
        half=[0]*62+[268435456]
        result=core.analyze(half,32,30,48000,[0],
            coefficient_layout='mirror63_center',center_q=536870912,fft_size=128)
        self.assertEqual(result['expanded_q_coefficients'][63],536870912)
        self.assertAlmostEqual(result['frequencies'][0]['gain_linear'],1)
        result=core.analyze([0]*63+[536870912],32,30,48000,[0,24000],
            coefficient_layout='mirror64',fft_size=128)
        self.assertEqual(result['tap_count'],128)
        self.assertEqual(result['fft']['padding_count'],0)
        self.assertEqual(result['expanded_q_coefficients'],result['expanded_q_coefficients'][::-1])
        self.assertAlmostEqual(result['frequencies'][1]['gain_linear'],0)

    def test_bad_layout_count_and_fft_truncation_rejected(self):
        for kwargs in [dict(coefficient_layout='mirror63_center'),
                       dict(coefficient_layout='mirror64'),dict(coefficient_layout='guess'),
                       dict(fft_size=127),dict(fft_size=128)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                core.analyze([1]*129,32,30,48000,[0],**kwargs)

    def test_q30_lowpass_has_known_response(self):
        result = core.analyze([268435456, 536870912, 268435456], 32, 30, 48000, [0, 12000, 24000])
        self.assertEqual(result['coefficients'], [0.25, 0.5, 0.25])
        for row, gain in zip(result['frequencies'], [1.0, 0.5, 0.0]):
            self.assertAlmostEqual(row['gain_linear'], gain, places=10)
        self.assertAlmostEqual(result['frequencies'][1]['gain_db'], -6.020599913, places=7)
        self.assertIsNone(result['frequencies'][2]['gain_db'])
        # 2048-point FFT at bin 512 agrees with hand-derived 0.5.
        self.assertAlmostEqual(result['fft']['gain_linear'][512], 0.5, places=10)

    def test_signed_64bit_and_non_bin_frequency(self):
        result = core.analyze([-(2**62), 2**62], 64, 62, 48000, [6000])
        self.assertEqual(result['coefficients'], [-1.0, 1.0])
        self.assertAlmostEqual(result['frequencies'][0]['gain_linear'], 0.7653668647, places=9)
        result = core.analyze([1], 32, 0, 48000, [1234.5])
        self.assertEqual(result['frequencies'][0]['gain_linear'], 1.0)

    def test_invalid_qformat_and_frequency_rejected(self):
        for coeffs, bits, frac, rate, query in [([],32,30,48000,[0]),
            ([2**31],32,30,48000,[0]), ([True],32,30,48000,[0]),
            ([1.5],32,30,48000,[0]), ([1],32,32,48000,[0]),
            ([1],16,15,48000,[0]), ([1],32,30,0,[0]),
            ([1],32,30,48000,[24001]), ([1],32,30,48000,[float('nan')])]:
            with self.subTest(inputs=(coeffs,bits,frac,rate,query)):
                with self.assertRaises(ValueError): core.analyze(coeffs,bits,frac,rate,query)

    def test_png_export_preserves_existing_file_and_restricts_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            result = core.analyze([1],32,0,48000,[1000])
            first = Path(core.save_response_image(result, folder, 'fir.png')['path'])
            before = first.read_bytes()
            self.assertTrue(before.startswith(b'\x89PNG\r\n\x1a\n'))
            second = Path(core.save_response_image(result,folder,'fir.png')['path'])
            self.assertNotEqual(first,second)
            self.assertEqual(first.read_bytes(),before)
            for name in ['../out.png', 'C:\\out.png', 'plot.svg']:
                with self.assertRaises(ValueError): core.save_response_image(result,folder,name)

if __name__ == '__main__': unittest.main()
