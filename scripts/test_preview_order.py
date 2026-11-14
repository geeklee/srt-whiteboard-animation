"""Pure preview helper checks (Node only, no browser automation)."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node not installed; preview helper tests skipped")
class PreviewHelperTests(unittest.TestCase):
    def test_order_leftovers_prototype_ids_duplicates_and_serial_schedule(self):
        html = (Path(__file__).resolve().parent.parent / "assets" / "preview.html").read_text()
        helpers = html[html.index("function orderedElements()"):html.index("// ---------- 打开文件夹")]
        script = """
const assert = require('node:assert/strict');
const S = {cfg: null};
const els = () => S.cfg.elements;
const endMs = e => e.reveal.startMs + e.reveal.durationMs;
""" + helpers + """
const el = (id,start,duration=600) => ({id, reveal:{startMs:start,durationMs:duration}});
S.cfg = {elements:[el('left',0),el('right',700)],elementOrder:['right','left']};
assert.deepEqual(scheduledElements().map(e => [e.id,e.reveal.startMs]), [['right',700],['left',1300]]);
assert.equal(totalMs(),2400);
S.cfg = {elements:[el('a',300),el('b',100),el('c',200)],elementOrder:['a']};
assert.deepEqual(orderedElements().map(e=>e.id),['a','b','c']);
S.cfg = {elements:[el('__proto__',0),el('same',100),el('same',200)],elementOrder:['__proto__','same']};
assert.equal(orderedElements().length,3);
assert.deepEqual(orderedElements().map(e=>e.id),['__proto__','same','same']);
assert.deepEqual(strokePolylines({strokePaths:[[[null,60],["",60],[[1],60],[30,60]]]}), [[[30,60]]]);
assert.equal(tipAlongStrokes([],0.5),null);
assert.deepEqual(tipAlongStrokes([[[180,60],[20,60]]],0.25),[140,60]);
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
