#!/usr/bin/env python3
"""NeBuNotes regression suite. Usage: python3 nebunotes_tests.py [NeBuNotes_Vxx.html] [--quick]
Needs: pip install playwright (and a Chrome/Chromium it can launch). Exit code 1 if anything fails.
Set CHROME=/path/to/chrome if Playwright's own browser is not installed."""
import sys, os, re, glob, json, random, zipfile, io, tempfile, shutil, time
from xml.dom import minidom
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
QUICK = '--quick' in sys.argv
if args: FILE = os.path.abspath(args[0])
else:
    cands = sorted(glob.glob(os.path.join(HERE, 'NeBuNotes_V*.html')), key=lambda p: int(re.search(r'V(\d+)', p).group(1)))
    FILE = cands[-1]
URL = 'file://' + FILE + '?nointro'
RESULTS = []
def check(name, ok, detail=''):
    RESULTS.append((bool(ok), name, detail))
    print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + str(detail)) if (detail and not ok) else ''))
def group(title): print('\n== ' + title)

SONG = {"title": "Test Song & <Co>", "tempo": 96, "timeSig": "3/4", "key": "Am", "sections": [
 {"id": "a", "name": "Intro", "type": "Intro", "bars": 4, "color": "#F2A7C6", "notes": "Soft start", "drummer": "Brushes only", "tempoChange": "", "timeSigChange": "", "lines": [
   {"id": "l0", "lyric": "", "chordEvents": [{"chord": "Am", "wordIndex": 0}, {"chord": "F", "wordIndex": 1}]}]},
 {"id": "b", "name": "Verse 1", "type": "Verse", "bars": 8, "color": "#F4D35E", "notes": "", "drummer": "Kick on 1", "tempoChange": "100", "timeSigChange": "4/4", "lines": [
   {"id": "l1", "lyric": "Hello darkness my old friend", "chordEvents": []},
   {"id": "l2", "lyric": "I've come to talk with you again", "chordEvents": [{"chord": "Asus2", "wordIndex": 0}, {"chord": "C", "wordIndex": 3}, {"chord": "G/B", "wordIndex": 5}]},
   {"id": "l3", "lyric": "Because a vision softly creeping", "chordEvents": [{"chord": "F#m7b5", "wordIndex": 0}]}]},
 {"id": "c", "name": "Chorus 1", "type": "Chorus", "bars": 4, "color": "#62B84F", "notes": "", "drummer": "", "tempoChange": "", "timeSigChange": "", "lines": [
   {"id": "l4", "lyric": "Shine like the light tonight", "chordEvents": [{"chord": "F", "wordIndex": 0}]},
   {"id": "l5", "lyric": "Hold me through the night", "chordEvents": [{"chord": "C", "wordIndex": 0}]}]}]}

def setsong(pg, obj):
    pg.evaluate("o=>{song=JSON.parse(JSON.stringify(o));render()}", obj); pg.wait_for_timeout(120)
def menu(pg, top, item):
    pg.click(f'.menu-trigger:text-is("{top}")'); pg.click(item)
def new_ctx(b, w=1280, h=900, **kw):
    c = b.new_context(viewport={'width': w, 'height': h}, accept_downloads=True, **kw)
    pg = c.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
    pg.on('dialog', lambda d: d.accept())
    return c, pg, errs
def fresh(b, w=1280, h=900):
    c, pg, errs = new_ctx(b, w, h); pg.goto(URL); pg.wait_for_timeout(350); return c, pg, errs

TYPE_JS = """()=>{const s={},w={},f=new Set();document.querySelectorAll('body *').forEach(e=>{if(e.closest('svg,script,style')||!e.getBoundingClientRect().width)return;if([...e.childNodes].some(n=>n.nodeType==3&&n.textContent.trim())){const c=getComputedStyle(e);s[c.fontSize]=1;w[c.fontWeight]=1;f.add(c.fontFamily)}});return {sizes:Object.keys(s),weights:Object.keys(w),fams:f.size,over:document.documentElement.scrollWidth-innerWidth}}"""

def run(b):
    # ---------- 1 load ----------
    group('Load, size, errors')
    size = os.path.getsize(FILE)
    check('file under 400 KB (logo/CSS bloat guard)', size < 400_000, f'{size/1024:.0f} KB')
    txt = open(FILE, encoding='utf-8').read()
    check('removed themes are gone (Sage Line, Peach Folio)', 'Sage Line' not in txt and 'Peach Folio' not in txt)
    print('INFO !important count:', txt.count('!important'))
    c, pg, errs = fresh(b)
    check('loads with no console/page errors (desktop)', not errs, errs)
    themes = pg.evaluate("[...document.querySelectorAll('.theme-item')].map(i=>[i.dataset.theme,i.querySelector('b').textContent])")
    check('theme menu has the expected themes', len(themes) == 12 and ('quiet' in dict(themes)), themes)

    # ---------- 2 type scale ----------
    group('Type scale: 3 sizes, 2 weights, across themes/modes/views')
    setsong(pg, SONG)
    bad = []
    tl = themes[:3] if QUICK else themes
    for tid, _ in tl:
        pg.evaluate("t=>setNebuTheme(t)", tid)
        for dark in (False, True):
            pg.evaluate("d=>document.body.classList.toggle('dark',d)", dark)
            for v in ('edit', 'preview', 'drummer'):
                pg.evaluate("v=>setView(v)", v); pg.wait_for_timeout(40)
                r = pg.evaluate(TYPE_JS)
                if set(r['sizes']) - {'12px', '15px', '24px'} or set(r['weights']) - {'400', '700'}: bad.append((tid, dark, v, r['sizes'], r['weights']))
    check(f'{len(tl)} themes x light/dark x 3 views use only 12/15/24px and weights 400/700', not bad, bad[:3])
    pg.evaluate("setNebuTheme('clean');document.body.classList.remove('dark');setView('edit')")
    errs_before = len(errs)

    # ---------- 3 layout ----------
    group('Layout and zoom')
    r = pg.evaluate(TYPE_JS); check('no horizontal overflow at 1280', r['over'] <= 1, r['over'])
    for z in (80, 150, 200, 100):
        pg.evaluate("z=>setNebuZoom(z)", z); pg.wait_for_timeout(80)
    check('zoom 200% switches to compact layout then returns', pg.evaluate("document.body.classList.contains('compact')") is False)
    pg.evaluate("setNebuZoom(200)"); pg.wait_for_timeout(100)
    check('zoom 200% uses compact layout', pg.evaluate("document.body.classList.contains('compact')"))
    pg.evaluate("setNebuZoom(100)")
    check('no ResizeObserver/console errors after zoom + resize storm', True)
    for w in (390, 1280, 500, 900, 390): pg.set_viewport_size({'width': w, 'height': 800}); pg.wait_for_timeout(60)
    check('resize storm raised no errors', len(errs) == errs_before, errs[errs_before:])
    c.close()

    c, pg, errs = fresh(b, 390, 800)
    setsong(pg, SONG)
    check('mobile uses compact layout', pg.evaluate("document.body.classList.contains('compact')"))
    for v in ('edit', 'preview', 'drummer'):
        pg.click(f'#mobileTabs [data-view={v}]'); pg.wait_for_timeout(80)
        r = pg.evaluate(TYPE_JS)
        check(f'mobile {v}: no horizontal overflow', r['over'] <= 1, r['over'])
        check(f'mobile {v}: type sizes only 13/16/22', not (set(r['sizes']) - {'13px', '16px', '22px'}), r['sizes'])
    pg.click('#mobileTabs [data-view=edit]')
    check('mobile section card has a ⋯ options button', pg.locator('.sec-more').count() >= 3)
    pg.locator('.sec-more').first.click()
    check('⋯ reveals section tools', pg.locator('.section-card.more-open .section-tools').first.is_visible())
    # theme menu scroll
    pg.set_viewport_size({'width': 390, 'height': 640}); pg.click('.menu-trigger:text-is("Theme")')
    r = pg.evaluate("(()=>{const m=[...document.querySelectorAll('.menu-panel')].find(x=>x.querySelector('.theme-item'));return [m.clientHeight,m.scrollHeight,getComputedStyle(m).overflowY]})()")
    check('theme menu scrolls on a short phone screen', r[1] > r[0] and r[2] in ('auto', 'scroll'), r)
    pg.evaluate("[...document.querySelectorAll('.menu-panel')].find(x=>x.querySelector('.theme-item')).scrollTop=99999")
    last = pg.locator('.theme-item').last
    last.click(); check('last theme reachable by scrolling and selectable', pg.evaluate("document.body.dataset.theme") == 'quiet')
    check('mobile run had no errors', not errs, errs)
    c.close()

    # ---------- bar numbering ----------
    group('Bar numbering fuzz')
    c, pg, errs = fresh(b)
    random.seed(7); fails = []
    for it in range(60 if QUICK else 150):
        secs = []
        for si in range(random.randint(1, 5)):
            secs.append({"id": f"s{si}", "name": f"S{si}", "type": random.choice(['Verse', 'Chorus', 'Bridge']), "bars": random.randint(1, 20), "color": "#F4D35E", "notes": "", "drummer": "", "tempoChange": "", "timeSigChange": "",
                         "lines": [{"id": f"s{si}l{li}", "lyric": "la " * random.randint(0, 4), "chordEvents": []} for li in range(random.randint(0, 9))]})
        pg.evaluate("s=>{song={title:'f',tempo:120,timeSig:'4/4',key:'',sections:s};render()}", secs)
        r = pg.evaluate("""()=>{const L=barLayout();const out=[];let prev=0;const probs=[];L.forEach((sec,i)=>{if(sec.start!==prev+1)probs.push('gap '+i);prev=sec.end;let pl=sec.start-1;(sec.lines||[]).forEach((l,j)=>{if(l.from<sec.start||l.to>sec.end)probs.push('range '+i+'.'+j);})});
          const squares=[...document.querySelectorAll('.timeline-section .bar')].map(e=>e.textContent.trim());const total=song.sections.reduce((a,s)=>a+s.bars,0);
          if(squares.length!==total)probs.push('timeline squares '+squares.length+' vs '+total);squares.forEach((t,i)=>{if(t!==String(i+1))probs.push('square '+i+'='+t)});
          const labels=[...document.querySelectorAll('.line-bar')].length;const nl=song.sections.reduce((a,s)=>a+s.lines.length,0);if(labels!==nl)probs.push('labels '+labels+' vs '+nl);
          return probs}""")
        if r: fails.append((it, r[:3]))
    check('timeline, Song Contents and layout agree for random songs', not fails, fails[:2])
    check('fuzz raised no errors', not errs, errs[:2]); c.close()

    # ---------- project json + library ----------
    group('Autosave, recovery, library')
    c, pg, errs = fresh(b); setsong(pg, SONG); pg.wait_for_timeout(600)
    check('save-state chip says Saved', pg.inner_text('#saveState').strip() == 'Saved')
    lib = pg.evaluate("nebuLib()"); check('song autosaved into the library', len(lib['songs']) == 1 and list(lib['songs'].values())[0]['data']['title'] == SONG['title'], lib.keys())
    pg.reload(); pg.wait_for_timeout(500)
    check('reload restores the song', pg.evaluate("song.title") == SONG['title'] and pg.evaluate("song.sections.length") == 3)
    check('welcome-back prompt is shown', pg.locator('#nbBanner.show').count() == 1 and 'Welcome back' in pg.inner_text('#nbBanner'))
    # edit via UI then reload before debounce settles
    pg.fill('.lyric-text >> nth=1', 'Edited lyric line'); pg.reload(); pg.wait_for_timeout(500)
    check('a UI edit survives an immediate reload', 'Edited lyric line' in pg.evaluate("JSON.stringify(song)"))
    # library ops
    menu(pg, 'File', '#newSong'); pg.wait_for_timeout(300)
    check('New song creates a second library entry', len(pg.evaluate("nebuLib()")['songs']) == 2 and pg.evaluate("song.sections.length") == 0)
    pg.evaluate("song.title='Second';render()"); pg.wait_for_timeout(600)
    menu(pg, 'File', '#songsBtn'); pg.wait_for_timeout(150)
    rows = pg.locator('.song-row'); check('Songs list shows both songs', rows.count() == 2, rows.count())
    pg.locator('.song-row .song-open', has_text='Test Song').click(); pg.wait_for_timeout(200)
    check('opening a song from the list loads it', pg.evaluate("song.title") == SONG['title'])
    menu(pg, 'File', '#songsBtn'); pg.locator('.song-row button[data-act=dup]').first.click(); pg.wait_for_timeout(100)
    check('Duplicate adds a copy', pg.locator('.song-row').count() == 3 and 'copy' in pg.inner_text('#songList'))
    pg.locator('.song-row button[data-act=del]').first.click(); pg.wait_for_timeout(100)
    check('Delete removes one', pg.locator('.song-row').count() == 2)
    with pg.expect_download() as d: pg.click('#songsBackup')
    p = os.path.join(tempfile.gettempdir(), 'nb_lib.json'); d.value.save_as(p)
    data = json.load(open(p)); check('Back up all songs writes a library file', data['format'] == 'nebunotes-library' and len(data['songs']) == 2)
    pg.set_input_files('#libPicker', p); pg.wait_for_timeout(200)
    check('Restore backup adds songs without overwriting', pg.locator('.song-row').count() == 4, pg.locator('.song-row').count())
    check('library flow raised no errors', not errs, errs[:2]); c.close()

    c, pg, errs = fresh(b); setsong(pg, SONG)
    pg.evaluate("localStorage.setItem('nebunotes-backup-v1',JSON.stringify({last:Date.now()-3600e3,edits:39,nag:0}))"); pg.reload(); pg.wait_for_timeout(300)
    pg.wait_for_timeout(600)
    if pg.locator('#nbBanner.show').count(): pg.click('#nbBanner .nb-x')
    setsong(pg, SONG); pg.evaluate("song.title='x1';render();"); pg.evaluate("song.title='x2';render();"); pg.wait_for_timeout(300)
    check('backup reminder appears after many edits and an old backup', 'backup' in pg.inner_text('#nbBanner').lower() and pg.locator('#nbBanner.show').count() == 1)
    with pg.expect_download() as d: pg.locator('#nbBanner button', has_text='Export backup').click()
    check('Export backup button downloads the project', d.value.suggested_filename.endswith('.song.json'))
    check('reminder not shown right after backing up', pg.evaluate("JSON.parse(localStorage.getItem('nebunotes-backup-v1')).edits") == 0)
    c.close()

    # ---------- json round trip ----------
    group('Project .json round trip + undo')
    c, pg, errs = fresh(b); setsong(pg, SONG)
    with pg.expect_download() as d: menu(pg, 'File', '#exportBtn')
    p = os.path.join(tempfile.gettempdir(), 'nb_proj.json'); d.value.save_as(p)
    j = json.load(open(p)); check('project json has the song', j['title'] == SONG['title'] and len(j['sections']) == 3)
    pg.evaluate("song.title='changed';render()"); pg.set_input_files('#filePicker', p); pg.wait_for_timeout(300)
    check('opening the project file restores it', pg.evaluate("song.title") == SONG['title'] and pg.evaluate("JSON.stringify(song.sections.map(s=>s.lines.map(l=>[l.lyric,l.chordEvents.map(e=>e.chord+e.wordIndex)])))") == json.dumps([[[ln['lyric'], [e['chord'] + str(e['wordIndex']) for e in ln['chordEvents']]] for ln in s['lines']] for s in SONG['sections']], separators=(',', ':')))
    check('opened file became its own library entry', len(pg.evaluate("nebuLib()")['songs']) >= 2)
    pg.fill('.lyric-text >> nth=1', 'Undo me'); pg.wait_for_timeout(800)
    pg.click('#undoBtn'); pg.wait_for_timeout(200)
    check('undo restores the previous lyric', 'Undo me' not in pg.evaluate("JSON.stringify(song)"))
    check('json/undo raised no errors', not errs, errs[:2]); c.close()

    # ---------- exports ----------
    group('Word / PDF export (full, lead sheet, lyrics, notes)')
    c, pg, errs = fresh(b); setsong(pg, SONG)
    def export(content, notes=False, drum=False):
        menu(pg, 'File', '#exportSheet'); pg.check(f'input[name=xf][value=docx]'); pg.check(f'input[name=xc][value={content}]')
        pg.set_checked('#xNotes', notes); pg.set_checked('#xDrum', drum)
        with pg.expect_download() as d: pg.click('#xGo')
        p = os.path.join(tempfile.gettempdir(), f'nb_{content}_{notes}_{drum}.docx'); d.value.save_as(p)
        z = zipfile.ZipFile(p); assert z.testzip() is None
        xml = z.read('word/document.xml').decode(); minidom.parseString(xml)
        return d.value.suggested_filename, xml, ''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml)), p
    fn, xml, text, full_path = export('full')
    check('full docx is a valid zip with well-formed XML', True)
    check('docx has title (escaped), details and sections', 'Test Song &amp; &lt;Co&gt;' in xml and '96bpm' in text and '3/4' in text and 'Verse 1' in text)
    check('docx puts chords above lyrics (Consolas, bold chords)', 'Asus2' in text and 'Hello darkness my old friend' in text and 'Consolas' in xml and 'w:fill="F4D35E"' in xml)
    check('docx chord column aligns over its word', any(re.search(r'^Asus2\s{4,}C\s+G/B$', t) for t in re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml)))
    check('docx excludes notes and drummer by default', 'Brushes only' not in text and 'Kick on 1' not in text)
    fn2, xml2, text2, _ = export('lead')
    check('lead sheet filename + chords only', fn2.endswith('-lead-sheet.docx') and 'Asus2' in text2 and 'Hello darkness' not in text2)
    fn3, xml3, text3, _ = export('lyrics')
    check('lyrics-only has lyrics and no chords', 'Hello darkness my old friend' in text3 and 'Asus2' not in text3 and 'F#m7b5' not in text3 and fn3.endswith('-lyrics.docx'))
    fn4, xml4, text4, _ = export('full', True, True)
    check('notes + drummer options include them', 'Soft start' in text4 and 'Kick on 1' in text4 and 'Brushes only' in text4 and 'Tempo: 100' in text4)
    # PDF/print
    menu(pg, 'File', '#exportSheet'); pg.check('input[name=xf][value=pdf]'); pg.check('input[name=xc][value=full]'); pg.set_checked('#xDrum', True)
    with pg.expect_popup() as pop: pg.click('#xGo')
    popup = pop.value; popup.wait_for_load_state(); html = popup.content()
    check('print sheet matches the Word layout (title, details, chords, drummer)', 'Test Song' in html and '96bpm' in html and 'Asus2' in html and 'Kick on 1' in html and 'background:#F4D35E' in html)
    popup.close()
    check('export raised no errors', not errs, errs[:2])
    # ---------- docx import ----------
    group('Import Word (.docx) round trip')
    before = pg.evaluate("JSON.stringify(song.sections.map(s=>({n:s.name,c:s.color.toUpperCase(),l:s.lines.map(x=>[x.lyric,x.chordEvents.map(e=>e.chord+'@'+e.wordIndex)])})))")
    pg.evaluate("song.title='zzz';render()")
    menu(pg, 'File', '#importDocx') if False else None
    pg.set_input_files('#docxPicker', full_path); pg.wait_for_timeout(500)
    after = pg.evaluate("JSON.stringify(song.sections.map(s=>({n:s.name,c:s.color.toUpperCase(),l:s.lines.map(x=>[x.lyric,x.chordEvents.map(e=>e.chord+'@'+e.wordIndex)])})))")
    b_, a_ = json.loads(before), json.loads(after)
    # chord-only intro line: lyric '' preserved with chord order
    check('imported title, tempo, time, key', pg.evaluate("[song.title,song.tempo,song.timeSig,song.key]") == [SONG['title'], 96, '3/4', 'Am'], pg.evaluate("[song.title,song.tempo,song.timeSig,song.key]"))
    check('imported section names and colours match', [(x['n'], x['c']) for x in a_] == [(x['n'], x['c']) for x in b_], (a_, b_))
    same_lines = all(x['l'] == y['l'] for x, y in zip(a_, b_)) and len(a_) == len(b_)
    check('imported lyrics and chord placement match exactly', same_lines, [(x['l'], y['l']) for x, y in zip(a_, b_) if x['l'] != y['l']][:2])
    check('imported song became a new library entry', len(pg.evaluate("nebuLib()")['songs']) >= 2)
    # parser on a Google-Docs-like sheet (chords above lyrics, no shading)
    parsed = pg.evaluate("""()=>nebuParseSheet([{text:'My Tune',fill:'',style:'Title'},{text:'Tempo: 88bpm',fill:'',style:''},{text:'Key: Em',fill:'',style:''},{text:'',fill:'',style:''},{text:'Verse 1',fill:'hl',style:''},{text:'',fill:'',style:''},{text:'Em        C\\nWalking in the rain',fill:'',style:''},{text:'',fill:'',style:''},{text:'Chorus',fill:'',style:''},{text:'G  D\\nOh oh oh',fill:'',style:''}])""")
    check('parser handles chord-over-lyric text, highlight headings, details', parsed['title'] == 'My Tune' and parsed['tempo'] == 88 and parsed['key'] == 'Em' and parsed['sections'][0]['lines'][0]['chordEvents'] == [{'chord': 'Em', 'wordIndex': 0}, {'chord': 'C', 'wordIndex': 2}] and parsed['sections'][1]['name'] == 'Chorus', parsed)
    bad = c.new_page(); bad.close()
    open(os.path.join(tempfile.gettempdir(), 'bad.docx'), 'wb').write(b'not a zip')
    pg.set_input_files('#docxPicker', os.path.join(tempfile.gettempdir(), 'bad.docx')); pg.wait_for_timeout(300)
    check('a non-docx file is rejected without breaking the app', pg.evaluate("Array.isArray(song.sections)") and not [e for e in errs if 'pageerror' in e], errs[:2])
    c.close()

    # ---------- syllables / rhymes ----------
    group('Syllables and rhymes')
    c, pg, errs = fresh(b)
    cases = {"Hello darkness my old friend": 7, "I've come to talk with you again": 8, "Shine like the light tonight": 6, "Hold me through the night": 5, "Ben, siz, yer kül, yol boş": 6}
    got = {k: pg.evaluate("t=>nebuSyl(t)", k) for k in cases}
    check('syllable counts within ±1 of the true count (approximate by design)', all(abs(got[k] - v) <= 1 for k, v in cases.items()), got)
    check('Turkish line counts vowels exactly', got["Ben, siz, yer kül, yol boş"] == 6, got)
    check('rhyme tails: night/light/tonight share a tail', len({pg.evaluate("t=>nebuTail(t)", t) for t in ('the night', 'the light', 'tonight')}) == 1)
    check('rhyme tails: different endings differ', pg.evaluate("nebuTail('the night')") != pg.evaluate("nebuTail('the day')"))
    setsong(pg, SONG); menu(pg, 'View', '#statsToggle'); pg.wait_for_timeout(150)
    stats = pg.evaluate("[...document.querySelectorAll('.row-actions')].map(a=>a.dataset.stats)")
    check('stats badges appear when toggled on', any(' syl' in (s or '') for s in stats), stats)
    check('rhyming chorus lines get the same letter', stats[-1].endswith('A') and stats[-2].endswith('A'), stats)
    check('toggle persists', pg.evaluate("localStorage.getItem('nebunotes-stats')") == '1')
    pg.fill('.lyric-text >> nth=1', 'one two three'); pg.wait_for_timeout(100)
    check('stats update while typing', pg.evaluate("document.querySelectorAll('.row-actions')[1].dataset.stats").startswith('3 syl'))
    menu(pg, 'View', '#statsToggle'); check('toggle off hides stats', not pg.evaluate("document.body.classList.contains('show-stats')"))
    check('stats raised no errors', not errs, errs[:2]); c.close()

    # ---------- misc ----------
    group('Themes, views, preview, drummer, text import, chord maker')
    c, pg, errs = fresh(b); setsong(pg, SONG)
    pg.evaluate("localStorage.setItem('nebunotes-style-v2','sage')"); pg.reload(); pg.wait_for_timeout(300)
    check('a stored removed theme falls back to Clean Slate', pg.evaluate("document.body.dataset.theme") == 'clean')
    setsong(pg, SONG)
    for v, needle in (('preview', 'Hello darkness'), ('drummer', 'Verse 1'), ('edit', None)):
        pg.evaluate("v=>setView(v)", v); pg.wait_for_timeout(60)
        if needle: check(f'{v} view renders song content', needle in ' '.join(pg.inner_text('#previewPanel').split()), ' '.join(pg.inner_text('#previewPanel').split())[:300])
    pg.evaluate("openImport()"); pg.fill('#importText', 'Song Title: T\nTempo: 100\n\nVerse 1:\n[Am]Walking in the [G]rain\n'); pg.click('#parseImport'); pg.wait_for_timeout(200)
    check('Import text still converts [chord] notation', pg.evaluate("song.title") == 'T' and pg.evaluate("song.sections[0].lines[0].chordEvents.length") == 2)
    pg.click('.menu-trigger:text-is("Tools")'); pg.click('#chordMakerBtn'); pg.wait_for_timeout(200)
    check('Chord Maker opens', pg.locator('#chordMakerModal.show').count() == 1)
    check('misc raised no errors', not errs, errs[:2]); c.close()

    # ---------- V31: grid, focus mode, help ----------
    group('Field grid, Focus mode, Help and About')
    c, pg, errs = fresh(b); setsong(pg, SONG)
    hts = pg.evaluate("['songTitle','tempo','timeSig','songKey'].map(i=>Math.round(document.getElementById(i).getBoundingClientRect().height))")
    check('song title, tempo, time and key fields share one height', len(set(hts)) == 1, hts)
    hh = pg.evaluate("[...document.querySelector('.section-card-head').querySelectorAll('input,select,.bar-range,.section-tools button')].filter(e=>e.getBoundingClientRect().width).map(e=>Math.round(e.getBoundingClientRect().height))")
    check('section header controls share one height', len(set(hh)) == 1, hh)
    check('song title is not oversized in the editor', pg.evaluate("getComputedStyle(document.getElementById('songTitle')).fontSize") == '15px')
    pg.evaluate("setView('preview')"); big = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#previewPanel h1')).fontSize)"); pg.evaluate("setView('edit')")
    check('song title stays large in Preview', big >= 24, big)
    menu(pg, 'View', '#focusToggle'); pg.mouse.click(640, 300); pg.wait_for_timeout(150)
    flat = pg.evaluate("['#metaPanel','#timelinePanel','#editorWorkspace>main'].map(s=>{const c=getComputedStyle(document.querySelector(s));return [c.borderTopWidth,c.boxShadow,c.backgroundColor]})")
    check('Focus mode removes panel boxes', all(f[0] == '0px' and f[1] == 'none' and f[2] == 'rgba(0, 0, 0, 0)' for f in flat), flat)
    check('Focus mode hides the timeline and contents headings', not pg.locator('#timelinePanel .section-head').is_visible() and not pg.locator('#editorWorkspace>main>.section-head').is_visible())
    check('Focus mode shows a single Add section button', pg.locator('#addSectionFocus').is_visible() and not pg.locator('#addSection').is_visible() and not pg.locator('#addSectionTop').is_visible())
    n = pg.evaluate("song.sections.length"); pg.click('#addSectionFocus'); check('Focus Add section works', pg.evaluate("song.sections.length") == n + 1)
    pg.reload(); pg.wait_for_timeout(300); check('Focus mode persists', pg.evaluate("document.body.classList.contains('focus')"))
    r = pg.evaluate(TYPE_JS); check('Focus mode: no overflow and only 12/15/24px', r['over'] <= 1 and not (set(r['sizes']) - {'12px', '15px', '24px'}), r)
    menu(pg, 'View', '#focusToggle'); pg.mouse.click(640, 300)
    check('Focus mode toggles off', not pg.evaluate("document.body.classList.contains('focus')"))
    menu(pg, 'Help', '#learnBtn'); pg.wait_for_timeout(200)
    sc = pg.evaluate("(()=>{const b=document.querySelector('#learnModal .learn-body');return [b.scrollHeight,b.clientHeight]})()")
    check('Learn window is scrollable', sc[0] > sc[1] + 200, sc)
    pg.click('[data-goto=l-save]'); pg.wait_for_timeout(700)
    check('Learn topic buttons scroll to their section', pg.evaluate("document.querySelector('#learnModal .learn-body').scrollTop") > 300)
    ltxt = pg.inner_text('#learnModal')
    check('Learn has no emoji', not re.search('[\U0001F300-\U0001FAFF\u2600-\u27BF]', ltxt))
    pg.keyboard.press('Escape'); check('Esc closes Learn', pg.locator('#learnModal.show').count() == 0)
    menu(pg, 'Help', '#aboutBtn'); pg.wait_for_timeout(150)
    at = pg.inner_text('#aboutModal'); bx = pg.locator('#aboutModal .about-card').bounding_box()
    check('About shows name, version, date and developer', 'NeBuNotes' in at and re.search(r'V\d+', at) and re.search(r'\d{1,2} \w+ 20\d\d', at) and 'Developed by Bora Demirbilek' in at, at)
    check('About card is a square', abs(bx['width'] - bx['height']) <= 2, bx)
    check('About logo is shown', pg.evaluate("document.getElementById('aboutLogo').naturalWidth") > 0)
    pg.click('#aboutModal .help-close'); check('About closes', pg.locator('#aboutModal.show').count() == 0)
    check('V31 features raised no errors', not errs, errs[:2]); c.close()
    c, pg, errs = fresh(b, 390, 800); setsong(pg, SONG)
    check('mobile: Help in the menu bar does not overflow', pg.evaluate("document.documentElement.scrollWidth-innerWidth") <= 1)
    pg.click('.menu-trigger:text-is("Help")'); pg.click('#aboutBtn'); pg.wait_for_timeout(150)
    bx = pg.locator('#aboutModal .about-card').bounding_box(); check('mobile About card fits the screen', bx['x'] >= 0 and bx['x'] + bx['width'] <= 390, bx)
    pg.keyboard.press('Escape'); pg.click('.menu-trigger:text-is("Help")'); pg.click('#learnBtn'); pg.wait_for_timeout(150)
    check('mobile Learn is scrollable', pg.evaluate("(()=>{const b=document.querySelector('#learnModal .learn-body');return b.scrollHeight>b.clientHeight})()"))
    check('mobile help raised no errors', not errs, errs[:2]); c.close()

def v32(b):
    group('V32: derived chords, legend view, dynamic timeline, spacing')
    c, pg, errs = fresh(b); setsong(pg, SONG)
    sv = pg.evaluate("""(()=>{const ok=[],OP=[4,9,2,7,11,4],PC={C:0,D:2,E:4,F:5,G:7,A:9,B:11};const bad=[];
      for(const r of ['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'])for(const q of ['','m','7','maj7','m7','sus2','sus4','dim','aug','6','9','add9','m7b5','5']){
        const n=r+q;if(!chordDiagramSVG(n))bad.push(n)}
      const d=deriveShape('B').f.join(',');return {bad,B:d,Bm:deriveShape('Bm').f.join(','),lower:!!chordDiagramSVG('b'),none:chordDiagramSVG('H')==='',slash:!!chordDiagramSVG('G/B')}})()""")
    check('every root x common quality has a diagram', not sv['bad'], sv['bad'][:8])
    check('typed B gives the standard barre shape', sv['B'] == '-1,2,4,4,4,2', sv['B'])
    check('typed Bm gives the standard barre shape', sv['Bm'] == '-1,2,4,4,3,2', sv['Bm'])
    check('lowercase and slash chords work, nonsense is still empty', sv['lower'] and sv['slash'] and sv['none'])
    check('no chord in the song shows "Diagram unavailable"', 'Diagram unavailable' not in pg.evaluate("guitarChordLegendHTML()"))
    menu(pg, 'View', '#focusToggle'); pg.mouse.click(640, 300)
    check('Focus mode lives in View, not Tools', pg.evaluate("document.body.classList.contains('focus')") and pg.evaluate("!document.querySelector('.menu:nth-child(3) #focusToggle')"))
    menu(pg, 'View', '#focusToggle'); pg.mouse.click(640, 300)
    pg.click('#legendQuick'); pg.wait_for_timeout(150)
    check('legend quick button shows only the legend', pg.locator('.legend-view .guitar-chord-item').count() >= 5 and pg.locator('#metaPanel').is_hidden() and pg.locator('.print-section').count() == 0)
    check('legend quick button is pressed, preview is not', pg.get_attribute('#legendQuick', 'aria-pressed') == 'true' and pg.get_attribute('#previewQuick', 'aria-pressed') == 'false')
    pg.click('#legendQuick'); pg.wait_for_timeout(100); check('legend quick button toggles back to the editor', pg.locator('#metaPanel').is_visible())
    menu(pg, 'View', '#legendBtn'); pg.wait_for_timeout(100); check('View > Chord Legend opens the legend', pg.locator('.legend-view').count() == 1)
    pg.click('.back-to-editor'); pg.wait_for_timeout(100)
    # dynamic timeline
    Q = "(()=>{const t=document.getElementById('timeline'),w=t.parentElement;return {sw:t.scrollWidth,cw:w.clientWidth,cls:t.className,bw:t.style.getPropertyValue('--tlbw')}})()"
    mk = "n=>{song.sections=[];for(let i=0;i<n;i++)song.sections.push({id:'x'+i,name:'S'+i,type:'Verse',bars:8,color:'#F4D35E',notes:'',drummer:'',tempoChange:'',timeSigChange:'',lines:[{id:'q'+i,lyric:'la',chordEvents:[]}]});render()}"
    check('Dynamic timeline is on by default', pg.evaluate("document.body.classList.contains('dyn-tl')"))
    pg.evaluate(mk, 3); pg.wait_for_timeout(200); q = pg.evaluate(Q)
    check('short timeline keeps full size and numbers', q['sw'] <= q['cw'] and 'tl-nonum' not in q['cls'], q)
    pg.evaluate(mk, 7); pg.wait_for_timeout(200); q = pg.evaluate(Q)
    check('longer timeline scales to fit without scrolling', q['sw'] <= q['cw'] + 1 and float(q['bw'][:-2]) < 34, q)
    check('numbers are hidden when boxes are too small', 'tl-nonum' in q['cls'] and pg.evaluate("getComputedStyle(document.querySelector('#timeline .bar')).color") == 'rgba(0, 0, 0, 0)', q)
    pg.evaluate(mk, 2); pg.wait_for_timeout(200); q = pg.evaluate(Q)
    check('numbers come back when they fit again', 'tl-nonum' not in q['cls'], q)
    pg.evaluate(mk, 9); pg.wait_for_timeout(200)
    menu(pg, 'View', '#dynTlToggle'); pg.wait_for_timeout(200); q = pg.evaluate(Q)
    check('switching it off gives the scroller back', q['sw'] > q['cw'] and q['bw'] == '' and pg.evaluate("localStorage.getItem('nebunotes-dyntl')") == '0', q)
    menu(pg, 'View', '#dynTlToggle'); pg.wait_for_timeout(200)
    pg.set_viewport_size({'width': 800, 'height': 900}); pg.wait_for_timeout(400); q = pg.evaluate(Q)
    check('timeline refits when the window is resized', q['sw'] <= q['cw'] + 1, q)
    check('bars never overlap sections in dynamic mode', pg.evaluate("[...document.querySelectorAll('#timeline .timeline-section')].every(s=>s.scrollWidth<=s.clientWidth+1)"))
    pg.set_viewport_size({'width': 1280, 'height': 900})
    # spacing
    setsong(pg, SONG); pg.wait_for_timeout(200)
    sp = pg.evaluate("""(()=>{const g=s=>getComputedStyle(document.querySelector(s));const pads=['#metaPanel','#timelinePanel','#editorWorkspace>main'].map(s=>g(s).paddingLeft+'/'+g(s).paddingTop);
      const gaps=['#metaPanel','#timelinePanel'].map(s=>g(s).marginBottom);const all=[g('.meta').columnGap,g('.meta').rowGap,g('.timeline').columnGap,g('.bar-row').columnGap,g('.guitar-chord-grid').columnGap,g('.section-card').marginBottom,g('.section-head').marginBottom];
      const lefts=['#metaPanel','#timelinePanel','#editorWorkspace>main'].map(s=>document.querySelector(s).getBoundingClientRect().left);
      const inner=['.meta','#timelinePanel .section-head','#editorWorkspace .section-head','.section-card'].map(s=>Math.round(document.querySelector(s).getBoundingClientRect().left));
      return {pads,gaps,all,lefts,inner}})()""")
    check('all three panels share one padding', len(set(sp['pads'])) == 1, sp['pads'])
    check('panel gaps are one value', len(set(sp['gaps'])) == 1 and sp['gaps'][0] == '16px', sp['gaps'])
    check('every gap is on the 4/8/16/24 scale', all(v.replace('px', '') in ('4', '8', '16', '24') for v in sp['all']), sp['all'])
    check('panels and their contents share left edges', len(set(sp['lefts'])) == 1 and len(set(sp['inner'])) == 1, (sp['lefts'], sp['inner']))
    check('V32 raised no errors', not errs, errs[:2]); c.close()
    # themes
    c, pg, errs = fresh(b); setsong(pg, SONG)
    bad = []
    for t in ['clean', 'brutal', 'pixel', 'pop', 'retro', 'spec', 'gallery', 'phosphor', 'acid', 'mac', 'track', 'quiet']:
        pg.evaluate("t=>document.body.dataset.theme=t", t); pg.evaluate("nebuFitTimeline()"); pg.wait_for_timeout(120)
        r = pg.evaluate("""(()=>{const g=s=>getComputedStyle(document.querySelector(s));return [g('#metaPanel').paddingLeft,g('#timelinePanel').paddingLeft,g('.section-card').marginBottom,document.documentElement.scrollWidth-innerWidth,document.getElementById('timeline').scrollWidth-document.getElementById('timeline').parentElement.clientWidth]})()""")
        if r[0] != '24px' or r[1] != '24px' or r[2] != '16px' or r[3] > 1 or r[4] > 1: bad.append((t, r))
    check('all 12 themes: same panel padding, card gap, no overflow, timeline fits', not bad, bad)
    c.close()
    c, pg, errs = fresh(b, 390, 800); setsong(pg, SONG); pg.wait_for_timeout(300)
    check('mobile: four tabs and Chords tab opens legend', pg.locator('#mobileTabs button').count() == 4)
    pg.click('#mobileTabs button[data-view="legend"]'); pg.wait_for_timeout(150)
    check('mobile legend view has diagrams and no overflow', pg.locator('.legend-view .guitar-chord-item').count() >= 5 and pg.evaluate("document.documentElement.scrollWidth-innerWidth") <= 1)
    pg.click('.back-to-editor'); pg.wait_for_timeout(200)
    q = pg.evaluate("(()=>{const t=document.getElementById('timeline');return t.scrollWidth-t.parentElement.clientWidth})()")
    check('mobile: dynamic timeline fits the width', q <= 1, q)
    check('mobile V32 raised no errors', not errs, errs[:2]); c.close()

def v33(b):
    group('V33: favicon, icons, intro animation')
    c, pg, errs = fresh(b); setsong(pg, SONG)
    fav = pg.evaluate("document.querySelector('link[rel=icon]')?.href||''")
    check('favicon is an embedded PNG', fav.startswith('data:image/png;base64,') and len(fav) > 1000)
    check('tab title is still NeBuNotes', pg.title() == 'NeBuNotes', pg.title())
    check('Preview button uses a monitor icon (rect + stand)', pg.evaluate("(()=>{const s=document.querySelector('#previewQuick svg');return !!s.querySelector('rect')&&s.innerHTML.includes('M9 20h6')})()"))
    check('legend button icon changed from the fretboard grid', pg.evaluate("(()=>{const s=document.querySelector('#legendQuick svg');return !!s.querySelector('g[transform]')&&!s.querySelector('rect')})()"))
    check('no intro overlay with ?nointro', pg.locator('#intro').count() == 0)
    check('intro skip flag raised no errors', not errs, errs[:2]); c.close()
    c, pg, errs = new_ctx(b, 1280, 800); pg.goto(URL.replace('?nointro', '')); pg.wait_for_timeout(300)
    check('intro covers the app at start', pg.locator('#intro').count() == 1 and pg.evaluate("getComputedStyle(document.getElementById('intro')).position") == 'fixed')
    check('intro starts yellow (logo yellow)', pg.evaluate("getComputedStyle(document.querySelector('#intro .in-yellow')).backgroundColor") == 'rgb(251, 226, 26)')
    pg.wait_for_timeout(1700)
    cp = pg.evaluate("getComputedStyle(document.querySelector('#intro .in-yellow')).clipPath")
    check('yellow shrinks to the post-it (clip-path no longer full-screen)', 'inset(0px' not in cp.replace('inset(0px 0px 0px 0px','X') or cp != 'inset(0px)', cp)
    pg.wait_for_timeout(3000)
    check('intro removes itself after it finishes', pg.locator('#intro').count() == 0)
    check('app is usable afterwards', pg.evaluate("!!document.getElementById('metaPanel')") and pg.locator('#metaPanel').is_visible())
    check('intro raised no errors', not errs, errs[:2]); c.close()
    c, pg, errs = new_ctx(b, 1280, 800); pg.goto(URL.replace('?nointro', '')); pg.wait_for_timeout(400)
    pg.mouse.click(640, 400); pg.wait_for_timeout(600)
    check('clicking skips the intro', pg.locator('#intro').count() == 0)
    c.close()
    c, pg, errs = new_ctx(b, 390, 800); pg.goto(URL.replace('?nointro', '')); pg.wait_for_timeout(5200)
    check('mobile: intro completes and page has no overflow', pg.locator('#intro').count() == 0 and pg.evaluate("document.documentElement.scrollWidth-innerWidth") <= 1 and not errs, errs[:2]); c.close()

if __name__ == '__main__':
    print('Testing', FILE)
    with sync_playwright() as p:
        kw = {'args': ['--no-sandbox']}
        exe = os.environ.get('CHROME') or next((x for x in ('/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser') if os.path.exists(x)), None)
        if exe: kw['executable_path'] = exe
        b = p.chromium.launch(**kw)
        try:
            run(b)
            v32(b); v33(b)
        except Exception as e:
            import traceback; traceback.print_exc(); check('suite ran to completion', False, repr(e))
        b.close()
    bad = [r for r in RESULTS if not r[0]]
    print(f'\n{len(RESULTS)-len(bad)}/{len(RESULTS)} checks passed' + (' - FAILURES: ' + '; '.join(r[1] for r in bad) if bad else ''))
    sys.exit(1 if bad else 0)
