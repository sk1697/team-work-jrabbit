import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'workshop'))
from fir_bridge import GuiBridge, call_gui


class BridgeTests(unittest.TestCase):
    def test_local_authenticated_request_and_unavailable_gui(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime=Path(folder)/'runtime.json'
            # Real loopback transport, with a deterministic consumer at its boundary.
            bridge=GuiBridge(runtime,lambda action,args: {'action':action,'value':args.get('value')})
            bridge.start()
            try:
                self.assertEqual(call_gui(runtime,'state',{'value':7}),{'action':'state','value':7})
                info=json.loads(runtime.read_text())
                req=Request(info['url'],data=b'{"action":"state","args":{}}',headers={'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as caught: urlopen(req,timeout=2)
                self.assertEqual(caught.exception.code,403)
                caught.exception.close()
            finally: bridge.stop()
            with self.assertRaises(RuntimeError): call_gui(runtime,'state')

if __name__=='__main__': unittest.main()
