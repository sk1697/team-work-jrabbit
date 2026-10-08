"""Verify actual stdio tools/resources/prompts AND live GUI updates.

Keep the GUI open and press '연결 준비' first. No CLI login/API key required.
"""
import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def payload(result):
    assert not result.isError,result
    return json.loads(next(c.text for c in result.content if c.type=='text'))


async def verify(command,args):
    async with stdio_client(StdioServerParameters(command=command,args=args)) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            names={t.name for t in (await session.list_tools()).tools}
            assert {'get_fir_state','analyze_fir','query_fir_frequencies','save_fir_image'} <= names
            assert 'fir://reference' in {str(r.uri) for r in (await session.list_resources()).resources}
            config=json.loads((await session.read_resource('fir://reference')).contents[0].text)
            assert config['coefficient_layout']=='mirror63_center' and len(config['q_coefficients'])==63
            assert 'compare_fir' in {p.name for p in (await session.list_prompts()).prompts}
            assert 'analyze_fir' in (await session.get_prompt('compare_fir')).messages[0].content.text
            inputs=dict(q_coefficients=['268435456','536870912','268435456'],word_bits=32,
                        fractional_bits=30,sample_rate_hz=48000,query_hz=[0,12000,24000],
                        coefficient_layout='direct',center_q='0',fft_size=2048)
            data=payload(await session.call_tool('analyze_fir',inputs))
            for row,expected in zip(data['frequencies'],[1,0.5,0]):
                assert math.isclose(row['gain_linear'],expected,abs_tol=1e-10)
            assert data['frequencies'][2]['gain_db'] is None
            state=payload(await session.call_tool('get_fir_state',{}))
            assert state['analysis']['coefficients']==[.25,.5,.25]
            changed=payload(await session.call_tool('analyze_fir',{**inputs,'q_coefficients':['536870912','536870912']}))
            assert math.isclose(changed['frequencies'][1]['gain_linear'],2**-0.5,abs_tol=1e-10)
            queried=payload(await session.call_tool('query_fir_frequencies',{'query_hz':[6000,12000]}))
            assert math.isclose(queried['frequencies'][0]['gain_linear'],0.9238795325,abs_tol=1e-9)
            bad=await session.call_tool('analyze_fir',{**inputs,'query_hz':[24001]})
            assert bad.isError,'Out-of-range frequency must be rejected'
            state=payload(await session.call_tool('get_fir_state',{}))
            assert state['analysis']['tap_count']==2,'Invalid request must not replace the last valid result'
            saved=payload(await session.call_tool('save_fir_image',{'filename':'mcp-check.png'}))
            path=Path(saved['path']); assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            saved2=payload(await session.call_tool('save_fir_image',{'filename':'mcp-check.png'}))
            assert saved2['path']!=saved['path'],'Never overwrite an existing image'
            assert (await session.call_tool('save_fir_image',{'filename':'../escape.png'})).isError
            symmetric={key:config[key] for key in ('word_bits','fractional_bits','sample_rate_hz','query_hz','coefficient_layout','fft_size')}
            symmetric['q_coefficients']=[str(c) for c in config['q_coefficients']]
            symmetric['center_q']=str(config['center_q'])
            data=payload(await session.call_tool('analyze_fir',symmetric))
            assert data['input_count']==63 and data['tap_count']==127
            assert data['fft_size']==128 and data['fft_padding_count']==1
            for row,gain in zip(data['frequencies'],[1,2**-.5,0,1]):
                assert math.isclose(row['gain_linear'],gain,abs_tol=1e-9)
            centered=payload(await session.call_tool('analyze_fir',{**symmetric,'center_q':'536870912'}))
            assert centered['expanded_q_coefficients'][63]=='536870912'
            assert math.isclose(centered['frequencies'][0]['gain_linear'],1.5,abs_tol=1e-9)
            assert (await session.call_tool('analyze_fir',{**symmetric,'q_coefficients':['1']*62})).isError
            mirror64=payload(await session.call_tool('analyze_fir',{**symmetric,'q_coefficients':['0']*63+['536870912'],'coefficient_layout':'mirror64'}))
            assert mirror64['tap_count']==128 and mirror64['fft_padding_count']==0
            saved=payload(await session.call_tool('save_fir_image',{'filename':'mcp-symmetric.png'}))
            assert Path(saved['path']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            # Restore familiar reference so the learner can see the default after checking.
            payload(await session.call_tool('analyze_fir',symmetric))
            print(json.dumps({'reference':data['frequencies'],'saved_png':str(path)},ensure_ascii=False,indent=2))
            print('VALID: stdio + live dark GUI + 63/127/128 symmetry and padding + center change + 64/128 + query + PNG + errors')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',default=str(Path.cwd()/'.fir-runtime'/'runtime.json'))
    parser.add_argument('--server',default=str(Path(__file__).with_name('fir_server.py')))
    parser.add_argument('--exe')
    args=parser.parse_args()
    if args.exe:
        command=str(Path(args.exe).resolve()); params=['--mcp','--runtime',str(Path(args.runtime).resolve())]
    else:
        server=Path(args.server).resolve()
        if not server.is_file(): raise SystemExit('Create workshop/fir_server.py first, or use --server workshop/fir_mcp.py')
        command=sys.executable; params=[str(server),'--runtime',str(Path(args.runtime).resolve())]
    asyncio.run(verify(command,params))
