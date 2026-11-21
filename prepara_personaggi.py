"""Crea prompt_personaggi.txt a partire dalle schede in personaggi/.

Ogni personaggio è una cartella personaggi/<Nome>/ con dentro scheda.txt
(vedi personaggi/_modello/scheda.txt). Lo stile comune sta in personaggi/stile.txt.
Lo script scrive una riga per immagine nel formato usato da genera.py:

    Nome/fase | prompt in inglese | LARGHEZZAxALTEZZA [| seed=N] [| foto]

Fasi (in automatico in base a cosa c'è nella cartella del personaggio):
  senza riferimento.png  ->  concept       (proposte da cui scegliere il personaggio)
  con   riferimento.png  ->  turnaround    (fronte, 3/4, lato, retro in un'immagine)
                             espressioni   (6 emozioni in una griglia)
                             pose          (una immagine per ogni posa della scheda)
                             varianti      (img2img dal riferimento, stesso personaggio)
  sempre, se i personaggi sono almeno 2:  gruppo  (tutti insieme, per le proporzioni)

Uso:
    python prepara_personaggi.py
    python prepara_personaggi.py --solo Tina
    python prepara_personaggi.py --fasi turnaround,pose
"""

import argparse
import re
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
PERSONAGGI = CARTELLA / 'personaggi'
USCITA = CARTELLA / 'prompt_personaggi.txt'

FASI = ('concept', 'turnaround', 'espressioni', 'pose', 'varianti', 'gruppo')
FASI_PRIMA = ('concept',)
FASI_DOPO = ('turnaround', 'espressioni', 'pose', 'varianti')
RIFERIMENTI = ('riferimento.png', 'riferimento.jpg', 'riferimento.jpeg', 'riferimento.webp')

# Dimensioni per fase (multipli di 16, adatte a Z-Image Turbo su T4)
DIMENSIONI = {
    'concept': '1024x1024',
    'turnaround': '1536x768',
    'espressioni': '1248x832',
    'pose': '1024x1024',
    'varianti': '1024x1024',
    'gruppo': '1536x864',
}


def leggi_testo(file):
    """Righe non vuote e non commentate, unite da uno spazio."""
    righe = file.read_text(encoding='utf-8').splitlines()
    return ' '.join(r.strip() for r in righe if r.strip() and not r.strip().startswith('#'))


def leggi_scheda(file):
    """'chiave: valore' per riga -> dizionario. Righe con # ignorate."""
    scheda = {}
    for riga in file.read_text(encoding='utf-8').splitlines():
        riga = riga.strip()
        if not riga or riga.startswith('#') or ':' not in riga:
            continue
        chiave, valore = riga.split(':', 1)
        scheda[chiave.strip().lower()] = valore.strip()
    return scheda


def chi_e(scheda):
    """Descrizione completa e sempre identica del personaggio (inglese)."""
    testo = scheda.get('descrizione', '')
    if scheda.get('abiti'):
        testo += f", wearing {scheda['abiti']}"
    if scheda.get('segni'):
        testo += f", with {scheda['segni']}"
    return testo


def slug(testo, lunghezza=40):
    return re.sub(r'[^a-zA-Z0-9]+', '_', testo).strip('_').lower()[:lunghezza] or 'posa'


def riferimento(cartella):
    for nome in RIFERIMENTI:
        if (cartella / nome).is_file():
            return cartella / nome
    return None


def righe_personaggio(nome, scheda, stile, fasi, foto):
    p = chi_e(scheda)
    seed = scheda.get('seed', '')
    seed = f' | seed={seed}' if seed.isdigit() else ''
    righe = []

    if 'concept' in fasi:
        righe.append(
            f'{nome}/1_concept | Character design of {p}. Full body, standing, front view, '
            f'friendly pose, centered, plain white background. {stile} | {DIMENSIONI["concept"]}')
    if 'turnaround' in fasi:
        righe.append(
            f'{nome}/2_turnaround | Character turnaround model sheet of one single character: '
            f'{p}. The same character drawn four times side by side in a row, full body, same '
            f'size and same proportions: front view, three-quarter view, side view, back view. '
            f'Plain white background. {stile} | {DIMENSIONI["turnaround"]}{seed}')
    if 'espressioni' in fasi:
        righe.append(
            f'{nome}/3_espressioni | Expression sheet of one single character: {p}. Six '
            f'head-and-shoulders portraits of the same character in a 3 by 2 grid showing '
            f'different emotions: happy, sad, surprised, angry, scared, laughing. Plain white '
            f'background. {stile} | {DIMENSIONI["espressioni"]}{seed}')
    if 'pose' in fasi:
        for posa in [x.strip() for x in scheda.get('pose', '').split(';') if x.strip()]:
            righe.append(
                f'{nome}/4_posa_{slug(posa)} | {p}, {posa}. Full body, centered, plain white '
                f'background. {stile} | {DIMENSIONI["pose"]}{seed}')
    if 'varianti' in fasi and foto:
        righe.append(
            f'{nome}/5_variante | Character design of {p}. Full body, standing, front view, '
            f'friendly pose, centered, plain white background. {stile} | '
            f'{DIMENSIONI["varianti"]} | {foto.as_posix()}')
    return righe


def main():
    a = argparse.ArgumentParser(description='Crea prompt_personaggi.txt dalle schede.')
    a.add_argument('--solo', help='solo questi personaggi, separati da virgola (es. Tina,Lumo)')
    a.add_argument('--fasi', help=f'forza queste fasi, separate da virgola: {", ".join(FASI)}')
    args = a.parse_args()

    stile = leggi_testo(PERSONAGGI / 'stile.txt')
    if not stile:
        sys.exit('personaggi/stile.txt è vuoto.')
    fasi_forzate = None
    if args.fasi:
        fasi_forzate = {f.strip().lower() for f in args.fasi.split(',') if f.strip()}
        sconosciute = fasi_forzate - set(FASI)
        if sconosciute:
            sys.exit(f'Fasi sconosciute: {", ".join(sorted(sconosciute))}. Valide: {", ".join(FASI)}')
    solo = {s.strip().lower() for s in args.solo.split(',')} if args.solo else None

    personaggi = []
    for cartella in sorted(PERSONAGGI.iterdir()):
        if not cartella.is_dir() or cartella.name.startswith('_'):
            continue
        if not (cartella / 'scheda.txt').is_file():
            print(f'  {cartella.name}: manca scheda.txt, salto')
            continue
        scheda = leggi_scheda(cartella / 'scheda.txt')
        if not scheda.get('descrizione'):
            print(f'  {cartella.name}: manca il campo "descrizione", salto')
            continue
        personaggi.append((cartella.name, scheda, riferimento(cartella)))
    if not personaggi:
        sys.exit('Nessun personaggio in personaggi/ (copiate personaggi/_modello).')

    righe = []
    for nome, scheda, foto in personaggi:
        if solo and nome.lower() not in solo:
            continue
        fasi = fasi_forzate or set(FASI_DOPO if foto else FASI_PRIMA)
        nuove = righe_personaggio(nome, scheda, stile, fasi, foto)
        stato = f'riferimento: {foto.name}' if foto else 'nessun riferimento ancora'
        print(f'  {nome:<15} {len(nuove):>2} immagini  ({stato})')
        righe += nuove

    gruppo = 'gruppo' in fasi_forzate if fasi_forzate else not solo
    if gruppo and len(personaggi) >= 2:
        descrizioni = '; '.join(
            f'{chi_e(s)} ({s["taglia"]})' if s.get('taglia') else chi_e(s)
            for _, s, _ in personaggi)
        righe.append(
            f'Gruppo/insieme | Character lineup of {len(personaggi)} different characters '
            f'standing side by side from left to right, full body, front view, showing their '
            f'relative heights: {descrizioni}. Plain white background. {stile} | '
            f'{DIMENSIONI["gruppo"]}')
        print(f'  {"Gruppo":<15}  1 immagine')

    intestazione = ['# Generato da prepara_personaggi.py: non modificatelo a mano, rilanciate lo script.',
                    '# Formato: Personaggio/fase | prompt | LxA [| seed=N] [| foto di riferimento]']
    USCITA.write_text('\n'.join(intestazione + righe) + '\n', encoding='utf-8')
    print(f'\nScritte {len(righe)} righe in {USCITA.name}')


if __name__ == '__main__':
    main()
