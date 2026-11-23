"""
app.py  -  Audiophile  |  Hugging Face Spaces
Full pitch detection + age-adjusted feedback demo.
"""

import gradio as gr
from feedback import generate_feedback
from instruments import INSTRUMENT_RANGES
from pitch_utils import NOTE_NAMES, create_pitch_graph, detect_pitch_and_note

PRACTICE_LIBRARY_HTML = r"""
<section class="practice-library" id="practice-library" aria-label="Practice scales" hidden>
  <div class="practice-layout">
    <aside class="practice-sidebar" aria-label="Choose your practice">
      <div class="practice-field"><label>Instrument</label><div>Guitar · standard tuning</div></div>
      <div class="practice-field"><label for="practice-scale">Scale</label><select id="practice-scale"><option>Minor pentatonic</option><option>Major pentatonic</option><option>Major</option><option>Natural minor</option><option>Blues</option></select></div>
      <div class="practice-field"><label for="practice-key">Key</label><select id="practice-key"><option>A</option><option>A♯/B♭</option><option>B</option><option>C</option><option>C♯/D♭</option><option>D</option><option>D♯/E♭</option><option>E</option><option>F</option><option>F♯/G♭</option><option>G</option><option>G♯/A♭</option></select></div>
      <div class="practice-quick"><h3>Quick access</h3><div class="practice-subheading">Saved</div><div id="practice-favorites"></div><div class="practice-subheading">Recent</div><div id="practice-recent"></div></div>
    </aside>
    <div class="practice-content">
      <div class="practice-selected"><div><span class="practice-eyebrow">Scale</span><h3 id="practice-title">A minor pentatonic</h3><p>Guitar · standard tuning</p></div><button id="practice-save" type="button" aria-pressed="false">☆ Save</button></div>
      <div class="practice-section"><div class="practice-label">Position</div><div id="practice-positions" class="practice-positions" role="group" aria-label="Choose a guitar position"><button type="button" data-position="shape-1" data-kind="shape">Position 1</button><button type="button" data-position="shape-2" data-kind="shape">Position 2</button><button type="button" data-position="shape-3" data-kind="shape">Position 3</button><button type="button" data-position="shape-4" data-kind="shape">Position 4</button><button type="button" data-position="shape-5" data-kind="shape">Position 5</button><button type="button" data-position="0-4" data-kind="range" hidden>Frets 0–4</button><button type="button" data-position="5-8" data-kind="range" hidden>Frets 5–8</button><button type="button" data-position="9-12" data-kind="range" hidden>Frets 9–12</button><button type="button" data-position="all">All notes</button></div><p id="practice-position-help" class="practice-pattern-note"></p></div>
      <div class="practice-section"><label class="practice-label" for="practice-pattern">Practice pattern</label><select id="practice-pattern"><option>Scale notes</option><option>Ascending thirds</option><option>Groups of four</option></select><p class="practice-pattern-note">Play the sequence in any octave. Thirds are shown when both notes belong to the selected scale.</p><div id="practice-sequence" class="practice-sequence" aria-live="polite"></div></div>
    </div>
  </div>
</section>

"""

PRACTICE_LIBRARY_JS = r"""
() => {
  const root = document.getElementById('practice-library');
  const practiceSwitch = document.getElementById('scale-practice-switch');
  const fretboard = document.getElementById('scale-fretboard');
  if (!root || !practiceSwitch || !fretboard || root.dataset.ready === 'true') return;
  root.dataset.ready = 'true';
  const notes = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'];
  const scales = {'Minor pentatonic':[0,3,5,7,10], 'Major pentatonic':[0,2,4,7,9], 'Major':[0,2,4,5,7,9,11], 'Natural minor':[0,2,3,5,7,8,10], 'Blues':[0,3,5,6,7,10]};
  const strings = [['e',64],['B',59],['G',55],['D',50],['A',45],['E',40]];
  const keyValues = {'A':9,'A♯/B♭':10,'B':11,'C':0,'C♯/D♭':1,'D':2,'D♯/E♭':3,'E':4,'F':5,'F♯/G♭':6,'G':7,'G♯/A♭':8};
  const ranges = {'0-4':[0,4],'5-8':[5,8],'9-12':[9,12],all:[0,12]};
  // Fret offsets from the minor root on the low E string, ordered high e to low E.
  const shapes = [
    [[0,3],[0,3],[0,2],[0,2],[0,2],[0,3]],
    [[3,5],[3,5],[2,4],[2,5],[2,5],[3,5]],
    [[5,7],[5,8],[4,7],[5,7],[5,7],[5,7]],
    [[7,10],[8,10],[7,9],[7,9],[7,10],[7,10]],
    [[10,12],[10,12],[9,12],[9,12],[10,12],[10,12]],
  ];
  const shapePositions = shapes.map((_,i)=>`shape-${i+1}`);
  const pentatonic = value => value === 'Minor pentatonic' || value === 'Major pentatonic';
  const $ = id => root.querySelector('#practice-' + id);
  const scale = $('scale'), key = $('key'), pattern = $('pattern');
  let position = 'shape-1';
  let selectedStart = 0;
  function revealPosition() {
    const scroll = fretboard.closest('.scale-scroll');
    if (!practiceSwitch.checked || !scroll || scroll.scrollWidth <= scroll.clientWidth || selectedStart === 0) return;
    const firstCell = fretboard.querySelector(`tbody tr td:nth-child(${selectedStart + 2})`);
    if (firstCell) scroll.scrollLeft += firstCell.getBoundingClientRect().left - scroll.getBoundingClientRect().left - 65;
  }
  const storageKey = 'audiophile.practice-library.v1';
  let storage = {favorites:[], recent:[]};
  try { const prior = JSON.parse(localStorage.getItem(storageKey) || '{}'); if (Array.isArray(prior.favorites)) storage.favorites = prior.favorites; if (Array.isArray(prior.recent)) storage.recent = prior.recent; } catch (_) {}
  const persist = () => { try { localStorage.setItem(storageKey, JSON.stringify(storage)); } catch (_) {} };
  const current = () => ({scale:scale.value, key:key.value, pattern:pattern.value, position});
  const valid = x => x && Object.hasOwn(scales,x.scale) && Object.hasOwn(keyValues,x.key) && (Object.hasOwn(ranges,x.position) || (pentatonic(x.scale) && shapePositions.includes(x.position))) && Array.from(pattern.options).some(o => o.value === x.pattern);
  storage.favorites = storage.favorites.filter(valid).slice(0,20);
  storage.recent = storage.recent.filter(valid).slice(0,5);
  const id = x => JSON.stringify([x.key,x.scale,x.position,x.pattern]);
  const prettyPosition = x => shapePositions.includes(x) ? `position ${x.slice(-1)}` : ({'0-4':'frets 0–4','5-8':'frets 5–8','9-12':'frets 9–12',all:'all notes'})[x];
  const name = x => `${x.key} ${x.scale.toLowerCase()}`;
  function noteAt(midi) { return notes[midi % 12] + (Math.floor(midi / 12) - 1); }
  function sequence(rootNote, intervals, selectedPattern) {
    const degree = n => 60 + rootNote + intervals[n % intervals.length] + 12 * Math.floor(n / intervals.length);
    const pitch = midi => notes[midi % 12];
    if (selectedPattern === 'Ascending thirds') return Array.from({length:intervals.length}, (_,i) => { const from=degree(i); const to=[3,4].map(step=>from+step).find(candidate=>intervals.includes((candidate-60-rootNote)%12)); return to===undefined?null:[from,to].map(pitch).join(' – '); }).filter(Boolean).join('  ·  ');
    if (selectedPattern === 'Groups of four') return Array.from({length:intervals.length}, (_,i) => [0,1,2,3].map(n => pitch(degree(i+n))).join(' – ')).join('  ·  ');
    return Array.from({length:intervals.length+1}, (_,i) => pitch(degree(i))).join(' – ');
  }
  function board(rootNote, intervals) {
    const shapeIndex = shapePositions.indexOf(position);
    const minorRoot = scale.value === 'Major pentatonic' ? (rootNote + 9) % 12 : rootNote;
    const baseFret = (minorRoot - 4 + 12) % 12;
    const shape = shapeIndex < 0 ? null : shapes[shapeIndex].map(row => row.map(offset => offset + baseFret));
    const shapeFrets = shape ? shape.flat() : [];
    const [start,end] = shape ? [Math.min(...shapeFrets),Math.max(...shapeFrets)] : ranges[position];
    const pcs = new Set(intervals.map(x => (rootNote+x)%12));
    let html = '<thead><tr><th scope="col">String</th>';
    const lastFret = practiceSwitch.checked ? Math.max(12,end) : 12;
    for (let fret=0;fret<=lastFret;fret++) html += `<th scope="col">${fret}</th>`;
    html += '</tr></thead><tbody>';
    for (const [index,[string,midi]] of strings.entries()) {
      html += `<tr><th scope="row">${string}</th>`;
      for (let fret=0;fret<=lastFret;fret++) {
        const pitch = (midi+fret)%12;
        const inSelection = practiceSwitch.checked && (shape ? shape[index].includes(fret) : fret>=start && fret<=end && pcs.has(pitch));
        const marker = inSelection ? `<span class="scale-marker${pitch===rootNote?' scale-marker--root':''}" role="img" aria-label="${noteAt(midi+fret)}${pitch===rootNote?', root':''}">${notes[pitch]}</span>` : '';
        html += `<td>${marker}<span class="scale-note">${notes[pitch]}</span></td>`;
      }
      html += '</tr>';
    }
    html += '</tbody><tfoot aria-hidden="true"><tr><td></td>';
    for (let fret=0;fret<=lastFret;fret++) {
      const count = fret === 12 || fret === 24 ? 2 : [3,5,7,9,15,17,19,21].includes(fret) ? 1 : 0;
      html += `<td>${'<span class="scale-inlay"></span>'.repeat(count)}</td>`;
    }
    fretboard.innerHTML = html + '</tr></tfoot>';
    fretboard.setAttribute('aria-label',`Six-string guitar, frets 0 through ${lastFret}`);
    fretboard.style.minWidth = lastFret > 12 ? `${(lastFret+2)*2.4}rem` : '';
    document.getElementById('scale-root-label').textContent = `${key.value} root`;
    selectedStart = start;
    requestAnimationFrame(revealPosition);
  }
  function shortcuts(target, items, empty) {
    target.replaceChildren();
    if (!items.length) { const p=document.createElement('p'); p.textContent=empty; p.className='practice-empty'; target.appendChild(p); return; }
    items.forEach(item => {
      const button=document.createElement('button'); button.type='button'; button.className='practice-shortcut';
      const strong=document.createElement('strong'); strong.textContent=name(item);
      const detail=document.createElement('span'); detail.textContent=`${prettyPosition(item.position)} · ${item.pattern}`;
      button.append(strong,detail);
      button.addEventListener('click',()=>{key.value=item.key; scale.value=item.scale; pattern.value=item.pattern; position=item.position; update(true);});
      target.appendChild(button);
    });
  }
  function update(addRecent=false) {
    const selection=current(), rootNote=keyValues[selection.key], intervals=scales[selection.scale];
    $('title').textContent=name(selection); $('sequence').textContent=sequence(rootNote,intervals,selection.pattern); board(rootNote,intervals);
    root.querySelectorAll('[data-position]').forEach(button=>{button.hidden=button.dataset.kind==='shape'?!pentatonic(scale.value):button.dataset.kind==='range'?pentatonic(scale.value):false;button.setAttribute('aria-pressed',String(button.dataset.position===position));});
    $('position-help').textContent = pentatonic(scale.value) ? 'Choose one of five movable pentatonic shapes. Major shapes use the corresponding relative minor position.' : 'Choose a fret range to see scale notes.';
    const isSaved=storage.favorites.some(x=>id(x)===id(selection)); $('save').setAttribute('aria-pressed',String(isSaved)); $('save').textContent=isSaved?'★ Saved':'☆ Save';
    if (addRecent) {storage.recent=[selection,...storage.recent.filter(x=>id(x)!==id(selection))].slice(0,5);persist();}
    shortcuts($('favorites'),storage.favorites,'Save a selection to keep it here.'); shortcuts($('recent'),storage.recent,'Your recent selections will appear here.');
  }
  scale.addEventListener('change',()=>{if (position!=='all') position=pentatonic(scale.value)?'shape-1':'5-8'; update(true);});
  [key,pattern].forEach(el=>el.addEventListener('change',()=>update(true)));
  practiceSwitch.addEventListener('change',()=>{root.hidden=!practiceSwitch.checked;update();});
  window.addEventListener('resize',()=>requestAnimationFrame(revealPosition));
  root.querySelectorAll('[data-position]').forEach(button=>button.addEventListener('click',()=>{position=button.dataset.position;update(true)}));
  $('save').addEventListener('click',()=>{const item=current(); const exists=storage.favorites.some(x=>id(x)===id(item)); storage.favorites=exists?storage.favorites.filter(x=>id(x)!==id(item)):[item,...storage.favorites].slice(0,20);persist();update();});
  update();
}

"""


# Instrument list
INSTRUMENTS = list(INSTRUMENT_RANGES.keys())
AGE_GROUPS  = ["Child (6-12)", "Teen (13-18)", "Adult (18+)"]

EMOJIS = {
    "Guitar": "🎸", "Piano": "🎹", "Voice": "🎤", "Clarinet": "🎼"
}


def _color(key):
    return {
        "green": "#2f6f3e",
        "red":   "#a13030",
        "blue":  "#1d4ed8",
        "gold":  "#9a5b16",
        "muted": "#475569",
    }.get(key, "#f0ede6")


def render_pitch_html(note, frequency, cents, accuracy, consistency, all_notes, theme="dark"):
    from feedback import intonation_label, consistency_label, grade_from_accuracy

    # Theme-specific colors
    bg_main = "#141417" if theme == "dark" else "#fbf7ee"
    bg_card = "#1c1c21" if theme == "dark" else "#f6f1e6"
    bg_chip = "#1c1c21" if theme == "dark" else "#fbf7ee"
    border = "#2a2a32" if theme == "dark" else "#d8cfbb"
    text_main = "#f0ede6" if theme == "dark" else "#1f1a14"
    text_muted = "#6b6b7a" if theme == "dark" else "#5b5247"

    tune_str, direction = intonation_label(cents)
    tune_col = _color("green") if direction == "intune" else (
               _color("red") if direction == "sharp" else _color("blue"))

    needle_pct = 50 + max(-47, min(47, cents * 0.94))

    grade = grade_from_accuracy(accuracy)
    grade_col = _color("green") if accuracy >= 80 else (
                _color("gold") if accuracy >= 65 else _color("red"))

    cons_lbl = consistency_label(consistency)
    cons_col = _color("green") if consistency >= 75 else (
                _color("gold") if consistency >= 55 else _color("red"))

    chips_html = ""
    if all_notes:
        total = sum(c for _, c in all_notes)
        for n, cnt in all_notes:
            pct = cnt / total * 100 if total else 0
            chips_html += (
                f"<span class='chip' style='margin:0.25rem; background:{bg_chip}; border: 1px solid {border}; padding: 4px 8px; border-radius: 4px; color:inherit;'>{n} "
                f"<span class='chip-pct' style='font-weight:600; color:inherit;'>{pct:.0f}%</span></span>"
            )
    else:
        chips_html = f"<p style='margin:0;color:{text_muted};font-size:12px;'>No additional notes detected.</p>"

    return f"""
<div class='result-container' style='font-family:Lato,sans-serif;background:{bg_main};border:1px solid {border};padding:28px;color:{text_main};'>
  <div style='font-family:"JetBrains Mono",monospace;font-size:9px;letter-spacing:3px;
              text-transform:uppercase;color:{text_muted};margin-bottom:18px;'>Pitch Analysis Results</div>
  <div style='display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;'>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;text-align:center;'>
      <div style='font-size:9px;letter-spacing:2px;text-transform:uppercase;color:{text_muted};margin-bottom:8px;font-family:"JetBrains Mono",monospace;'>Dominant Note</div>
      <div style='font-size:32px;font-weight:700;color:{tune_col};font-family:"JetBrains Mono",monospace;'>{note}</div>
      <div style='font-size:10px;color:{text_muted};margin-top:4px;font-family:"JetBrains Mono",monospace;'>Letter Notation</div>
    </div>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;text-align:center;'>
      <div style='font-size:9px;letter-spacing:2px;text-transform:uppercase;color:{text_muted};margin-bottom:8px;font-family:"JetBrains Mono",monospace;'>Frequency</div>
      <div style='font-size:28px;font-weight:700;color:{text_main};font-family:"JetBrains Mono",monospace;'>{frequency:.1f}</div>
      <div style='font-size:10px;color:{text_muted};margin-top:4px;font-family:"JetBrains Mono",monospace;'>Hz</div>
    </div>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;text-align:center;'>
      <div style='font-size:9px;letter-spacing:2px;text-transform:uppercase;color:{text_muted};margin-bottom:8px;font-family:"JetBrains Mono",monospace;'>Intonation</div>
      <div style='font-size:18px;font-weight:700;color:{tune_col};font-family:"JetBrains Mono",monospace;'>{tune_str}</div>
    </div>
  </div>
  <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;margin-bottom:20px;'>
    <div style='display:flex;justify-content:space-between;font-family:"JetBrains Mono",monospace;
                font-size:9px;letter-spacing:2px;color:{text_muted};margin-bottom:12px;'>
      <span>Flat</span><span>In Tune</span><span>Sharp</span>
    </div>
    <div style='position:relative;height:10px;background:{border};border-radius:5px;'>
      <div style='position:absolute;top:-4px;bottom:-4px;left:50%;width:2px;
                  background:rgba(128,128,128,.2);transform:translateX(-50%);'></div>
      <div style='position:absolute;top:-6px;left:{needle_pct:.0f}%;width:4px;height:22px;
                  background:{tune_col};border-radius:2px;transform:translateX(-50%);
                  box-shadow:0 0 8px {tune_col};'></div>
    </div>
  </div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;'>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:14px;display:flex;
                align-items:center;justify-content:space-between;'>
      <span style='font-family:"JetBrains Mono",monospace;font-size:9px;letter-spacing:2px;
                   text-transform:uppercase;color:{text_muted};'>Pitch Accuracy</span>
      <span style='font-family:"JetBrains Mono",monospace;font-size:22px;font-weight:700;
                   color:{grade_col};'>{accuracy:.0f}%</span>
    </div>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:14px;display:flex;
                align-items:center;justify-content:space-between;'>
      <span style='font-family:"JetBrains Mono",monospace;font-size:9px;letter-spacing:2px;
                   text-transform:uppercase;color:{text_muted};'>Consistency</span>
      <span style='font-family:"JetBrains Mono",monospace;font-size:22px;font-weight:700;
                   color:{cons_col};'>{cons_lbl}</span>
    </div>
  </div>
  <div style='font-family:"JetBrains Mono",monospace;font-size:9px;letter-spacing:2px;
              text-transform:uppercase;color:{text_muted};margin-bottom:8px;'>All Notes Detected</div>
  <div style='margin-bottom:4px; display:flex; flex-wrap:wrap;'>{chips_html}</div>
</div>
"""


def render_feedback_html(fb: dict, instrument: str, age_group: str, theme="dark"):
    # Theme-specific colors
    bg_main = "#141417" if theme == "dark" else "#fbf7ee"
    bg_card = "#1c1c21" if theme == "dark" else "#f6f1e6"
    border = "#2a2a32" if theme == "dark" else "#d8cfbb"
    text_main = "#f0ede6" if theme == "dark" else "#1f1a14"
    text_muted = "#6b6b7a" if theme == "dark" else "#5b5247"
    text_overview = "#ccc9c0" if theme == "dark" else "#5b5247"

    grade_col = _color("green") if fb["accuracy"] >= 80 else (
                _color("gold") if fb["accuracy"] >= 65 else _color("red"))
    cons_col  = _color("green") if fb["consistency"] >= 75 else (
                _color("gold") if fb["consistency"] >= 55 else _color("red"))

    tips_html = ""
    for tip in fb["tips"]:
        col = _color(tip["color"])
        tips_html += (
            f"<li style='display:flex;gap:0.75rem;align-items:flex-start;"
            f"padding:0.9rem 0;border-top:1px solid {border};'>"
            f"<span style='display:inline-flex;align-items:center;justify-content:center;"
            f"min-width:2rem;height:2rem;border-radius:999px;color:{col};font-weight:800;'>"
            f"{tip['icon']}</span>"
            f"<span class='feedback-tip-text' style='color:{text_main};font-size:14px;line-height:1.65;'>{tip['text']}</span></li>"
        )

    emoji = {"Guitar": "🎸", "Piano": "🎹", "Voice": "🎤", "Clarinet": "🎼"}.get(instrument, "🎵")

    return f"""
<div class='result-container' style='font-family:Lato,sans-serif;background:{bg_main};border:1px solid {border};padding:28px;color:{text_main};'>
  <div style='font-family:"JetBrains Mono",monospace;font-size:9px;letter-spacing:3px;
              text-transform:uppercase;color:{text_muted};margin-bottom:18px;'>
    Performance Feedback - {emoji} {instrument} - {age_group}
  </div>
  <div style='display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;'>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;text-align:center;'>
      <div style='font-size:34px;font-weight:700;color:{grade_col};font-family:"JetBrains Mono",monospace;'>{fb["accuracy"]:.0f}%</div>
      <div style='font-size:9px;letter-spacing:2px;text-transform:uppercase;color:{text_muted};margin-top:4px;font-family:"JetBrains Mono",monospace;'>Pitch Accuracy</div>
    </div>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;text-align:center;'>
      <div style='font-size:34px;font-weight:700;color:{_color("blue")};font-family:"JetBrains Mono",monospace;'>{fb["grade"]}</div>
      <div style='font-size:9px;letter-spacing:2px;text-transform:uppercase;color:{text_muted};margin-top:4px;font-family:"JetBrains Mono",monospace;'>Intonation Grade</div>
    </div>
    <div class='result-card' style='background:{bg_card};border:1px solid {border};padding:16px;text-align:center;'>
      <div style='font-size:26px;font-weight:700;color:{cons_col};font-family:"JetBrains Mono",monospace;'>{fb["cons_label"]}</div>
      <div style='font-size:9px;letter-spacing:2px;text-transform:uppercase;color:{text_muted};margin-top:4px;font-family:"JetBrains Mono",monospace;'>Consistency</div>
    </div>
  </div>
  <div class='result-card overview-box' style='background:{bg_card};border:1px solid {border};border-left:3px solid #c8a96e;
              padding:20px;margin-bottom:20px;'>
    <p style='font-size:14px;line-height:1.8;color:{text_overview};margin:0;'>{fb["overview"]}</p>
  </div>
  {tips_html}
</div>
"""


def analyze(audio_path, instrument, age_group, theme_state):
    theme = "dark" if theme_state == "Dark" else "light"
    bg_err = "#141417" if theme == "dark" else "#fbf7ee"
    text_err = "#6b6b7a" if theme == "dark" else "#5b5247"
    border = "#2a2a32" if theme == "dark" else "#d8cfbb"

    if audio_path is None:
        empty = (
            f"<div class='result-container' style='background:{bg_err};border:1px solid {border};padding:40px;"
            f"text-align:center;color:{text_err};font-family:JetBrains Mono,monospace;"
            f"font-size:11px;letter-spacing:2px;'>No audio provided.</div>"
        )
        return empty, empty, None

    freq, note, cents, accuracy, consistency, all_notes, error, pitch_timeline = \
        detect_pitch_and_note(audio_path, instrument)

    if error or note is None:
        msg = error or "No clear pitch detected. Play a single sustained note clearly."
        err_html = (
            f"<div class='result-container' style='background:{bg_err};border:1px solid #d9534f;padding:20px;"
            f"font-family:JetBrains Mono,monospace;font-size:12px;color:#d9534f;"
            f"letter-spacing:1px;'>{msg}</div>"
        )
        return err_html, err_html, None

    pitch_html = render_pitch_html(note, freq, cents, accuracy, consistency, all_notes, theme)
    fb_dict    = generate_feedback(instrument, note, freq, cents,
                                   accuracy, consistency, age_group, all_notes)
    pitch_graph = create_pitch_graph(pitch_timeline)
    fb_html    = render_feedback_html(fb_dict, instrument, age_group, theme)

    return pitch_html, fb_html, pitch_graph


def toggle_theme(current_theme):
    new_theme = "Light" if current_theme == "Dark" else "Dark"
    return new_theme


def render_fretboard():
    # Open-string MIDI notes, from high e to low E.
    strings = (
        ("e", 64), ("B", 59), ("G", 55),
        ("D", 50), ("A", 45), ("E", 40),
    )
    frets = range(13)
    inlay_counts = {3: 1, 5: 1, 7: 1, 9: 1, 12: 2}
    inlay = "<span class='scale-inlay'></span>"
    fret_headers = "".join(f"<th scope='col'>{fret}</th>" for fret in frets)
    note_names = [note.replace("#", "♯") for note in NOTE_NAMES]
    string_rows = []
    for string, open_midi in strings:
        fret_cells = []
        for fret in frets:
            note = note_names[(open_midi + fret) % len(note_names)]
            fret_cells.append(f"<td><span class='scale-note'>{note}</span></td>")
        string_rows.append(f"<tr><th scope='row'>{string}</th>{''.join(fret_cells)}</tr>")

    inlay_cells = "".join(
        f"<td>{inlay * inlay_counts.get(fret, 0)}</td>" for fret in frets
    )

    return f"""
        <section class="scale-panel" aria-labelledby="scale-title">
            <header class="scale-header">
                <div>
                    <h2 id="scale-title">Guitar fretboard</h2>
                    <p class="scale-tuning">Standard tuning · A4 = 440 Hz</p>
                </div>
                <div class="scale-controls">
                    <label class="scale-toggle">
                        <input id="scale-notes-switch" type="checkbox" role="switch" aria-controls="scale-fretboard">
                        Show notes
                    </label>
                    <label class="scale-toggle">
                        <input id="scale-practice-switch" type="checkbox" role="switch" aria-controls="practice-library scale-fretboard scale-legend">
                        Practice scales
                    </label>
                </div>
            </header>
            <div class="scale-scroll" role="region" aria-label="Guitar fretboard" tabindex="0">
                <table id="scale-fretboard" class="scale-fretboard" aria-label="Six-string guitar, frets 0 through 12">
                    <thead><tr><th scope="col">String</th>{fret_headers}</tr></thead>
                    <tbody>{''.join(string_rows)}</tbody>
                    <tfoot aria-hidden="true"><tr><td></td>{inlay_cells}</tr></tfoot>
                </table>
            </div>
            <ul id="scale-legend" class="scale-legend" aria-label="Fretboard legend">
                <li><span class="scale-marker scale-marker--root" aria-hidden="true"></span><span id="scale-root-label">A root</span></li>
                <li><span class="scale-marker" aria-hidden="true"></span>Scale note</li>
            </ul>
            <p class="scale-hint">Fret 0 is the open string. The thinnest string, high e, is at the top.</p>
            {PRACTICE_LIBRARY_HTML}
        </section>
    """


def build_demo():

    with gr.Blocks(title="Audiophile — Pitch Detection", elem_id="main-container") as demo:
        theme_state = gr.State("Dark")

        # Hero
        gr.HTML("""
            <section class="container hero center">
                <h1 style="margin-top: 1.5rem; font-size: 5vw">
                    <span class="sans">Audiophile</span>,<br />
                    <em id="comma">for the love of Music</em>
                </h1>
                <p id="hero-subtitle">Submit or record a single recording and receive feedback.</p>
            </section>
        """)

        with gr.Tabs(overflow_behavior="wrap") as tabs:

            # Tab 1 - Input
            with gr.Tab("Instruments and Audio", elem_classes="recital-tabs", id=0):

                with gr.Row(equal_height=False):

                    # LEFT: Instructions
                    with gr.Column(scale=1):
                        gr.HTML("""
                            <aside style="padding-top: 2rem;">
                                <div class="eyebrow" id="secondary">Instructions</div>
                                <h2 id="left" class="serif" style="margin-top: 0.75rem">For your submission</h2>
                                <hr class="rule" />
                                <ol class="steps">
                                    <li class="step">
                                        <div class="step-num">1</div>
                                        <div><div class="step-title">Select your instrument and age group</div></div>
                                    </li>
                                    <li class="step">
                                        <div class="step-num">2</div>
                                        <div><div class="step-title">Click the mic to record, or upload an audio file</div></div>
                                    </li>
                                    <li class="step">
                                        <div class="step-num">3</div>
                                        <div><div class="step-title">Play a note or short phrase (2-5 seconds works well)</div></div>
                                    </li>
                                    <li class="step">
                                        <div class="step-num">4</div>
                                        <div><div class="step-title">Click Analyze to run pitch detection</div></div>
                                    </li>
                                    <li class="step">
                                        <div class="step-num">5</div>
                                        <div><div class="step-title">Results will appear in the Pitches and Feedback tab</div></div>
                                    </li>
                                </ol>
                                <div class="paper note">
                                    <div class="eyebrow">A note on privacy</div>
                                    <p>Your recording is sent to the app for analysis. If AI feedback is enabled, the pitch measurements, instrument, and age group are sent to Groq; the recording itself is not sent to Groq.</p>
                                </div>
                            </aside>
                        """)

                    # RIGHT: Controls
                    with gr.Column(scale=1):

                        with gr.Row():
                            instrument = gr.Dropdown(
                                choices=INSTRUMENTS,
                                value="Guitar",
                                label="Instrument",
                                interactive=True,
                                elem_classes="recital-dropdown",
                            )
                            age_group = gr.Dropdown(
                                choices=AGE_GROUPS,
                                value="Adult (18+)",
                                label="Age Group",
                                interactive=True,
                                elem_classes="recital-dropdown",
                            )

                        audio_input = gr.Audio(
                            sources=["microphone", "upload"],
                            type="filepath",
                            label="Record or upload .wav / .mp3",
                            format="wav",
                        )

                        analyze_btn = gr.Button("Analyze Performance", variant="primary")

            # Tab 2 - Feedback
            with gr.Tab("Pitches and Feedback", elem_classes="recital-tabs", id=1):

                gr.HTML(
                    "<div class='sec-label step-header' style='margin-top:16px;padding:0 0 2px;'>Step 03</div>"
                    "<div class='sec-title step-header' style='padding:0 0 12px;'>Pitch Detection</div>"
                )

                pitch_out = gr.HTML(
                    value=(
                        "<div class='result-container' style='background:var(--ink);border:1px solid var(--border);padding:40px;"
                        "text-align:center;color:var(--ink-soft);font-family:JetBrains Mono,monospace;"
                        "font-size:11px;letter-spacing:2px;'>"
                        "Record or upload audio, then click Analyze.</div>"
                    )
                )

                gr.HTML(
                    "<div class='sec-label step-header' style='margin-top:24px;padding:0 0 2px;'>Step 04</div>"
                    "<div class='sec-title step-header' style='padding:0 0 12px;'>Feedback</div>"
                )

                feedback_out = gr.HTML(
                    value=(
                        "<div class='result-container' style='background:var(--ink);border:1px solid var(--border);padding:40px;"
                        "text-align:center;color:var(--ink-soft);font-family:JetBrains Mono,monospace;"
                        "font-size:11px;letter-spacing:2px;'>"
                        "Feedback will appear here after analysis.</div>"
                    )
                )
                graph_out = gr.Plot(label="Pitch Graph")

            with gr.Tab("Scale", elem_classes="recital-tabs", id=2) as scale_tab:
                gr.HTML(render_fretboard(), apply_default_css=False)
        
        # Theme Toggle Button
        with gr.Row():
            theme_btn = gr.Button("Toggle Theme", variant="secondary", size="sm")

        # Logic
        demo.load(fn=None, js=PRACTICE_LIBRARY_JS)
        scale_tab.select(fn=None, js=PRACTICE_LIBRARY_JS)
        analyze_btn.click(
            fn=analyze,
            inputs=[audio_input, instrument, age_group, theme_state],
            outputs=[pitch_out, feedback_out, graph_out],
        ).then(
            fn=lambda: gr.Tabs(selected=1),
            outputs=tabs,
            queue=False,
            api_visibility="private",
        )

        theme_btn.click(
            fn=toggle_theme,
            inputs=[theme_state],
            outputs=[theme_state]
        ).then(
            fn=None,
            js="""
            () => {
                const body = document.body;
                body.classList.toggle('light');
                
                const isLight = body.classList.contains('light');
                const bgMain = isLight ? "#fbf7ee" : "#141417";
                const bgCard = isLight ? "#f6f1e6" : "#1c1c21";
                const bgChip = isLight ? "#fbf7ee" : "#1c1c21";
                const border = isLight ? "#d8cfbb" : "#2a2a32";
                const textMain = isLight ? "#1f1a14" : "#f0ede6";
                const textTaupe = "#5b5246";

                document.querySelectorAll('.result-container').forEach(el => {
                    el.style.backgroundColor = bgMain;
                    el.style.borderColor = border;
                    el.style.color = textMain;
                });
                document.querySelectorAll('.result-card').forEach(el => {
                    el.style.backgroundColor = bgCard;
                    el.style.borderColor = border;
                });
                document.querySelectorAll('.chip').forEach(el => {
                    el.style.backgroundColor = bgChip;
                    el.style.borderColor = border;
                });
                
                // AI Feedback and Tips text color update
                document.querySelectorAll('.overview-box p, .feedback-tip-text').forEach(el => {
                    el.style.color = isLight ? textTaupe : textMain;
                });
            }
            """
        )

    return demo


if __name__ == "__main__":
    app = build_demo()
    app.launch(css_paths="styles.css")
